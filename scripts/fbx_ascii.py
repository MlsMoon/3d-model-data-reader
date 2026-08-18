#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX ASCII 行级解析（纯标准库）。"""
import re
from pathlib import Path

from fbx_types import FbxNode

def _strip_comment(line: str) -> str:
    """去除 `;` 注释（引号内保留）。"""
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif ch == ";":
            break
        else:
            out.append(ch)
    return "".join(out)


def _parse_elem(tok: str):
    """单个属性元素：字符串 -> str；类型标记/裸数字 -> int/float；否则原文。"""
    tok = tok.strip()
    if not tok:
        return None
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    m = _TYPE_RE.match(tok)
    if m and m.group(1).upper() in "YCIFDLRS":
        tok = m.group(2)
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        return tok


_TYPE_RE = re.compile(r"^([a-zA-Z])\s*:\s*(.+)$")


def _parse_values_block(buf: str) -> list:
    """解析一个（可能跨行的）属性值块。返回属性值列表；
    数组块（*N { a: ... }）整体作为**单个**数组属性值返回。"""
    s = " ".join(buf.split())
    # 数组块：*N { a: ... } 或 *N { a: 类型: ... } -> 单个数组属性
    if s.startswith("*"):
        inner = s[s.find("{") + 1: s.rfind("}")] if "{" in s else ""
        inner = inner.strip()
        if inner.startswith("a:"):
            inner = inner[2:].strip()
            am = _TYPE_RE.match(inner)
            if am:
                inner = am.group(2)
        elems = _split_values(inner)
        return [[_parse_elem(e) for e in elems if _parse_elem(e) is not None]]
    return [_parse_elem(e) for e in _split_values(s) if _parse_elem(e) is not None]


def _split_values(s: str) -> list[str]:
    """引号感知的逗号拆分（保留字符串内的逗号）。"""
    out, cur, in_str, esc = [], [], False, False
    for ch in s:
        if in_str:
            cur.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            cur.append(ch)
        elif ch == ",":
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or s.endswith(","):
        out.append("".join(cur).strip())
    return [c for c in out if c]


def _find_brace(line: str, ch: str) -> int:
    """引号感知地找第一个括号字符（跳过字符串内的）。"""
    in_str, esc = False, False
    for i, c in enumerate(line):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == ch:
            return i
    return -1


def _expand_inline_blocks(text: str) -> list[str]:
    """把单行闭合块 'Name: 值 { body }' 展开为多行（引号感知、嵌套平衡）。
    数组块（*N { a: ... }）与跨行未闭合块原样保留。"""
    out = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        first = _find_brace(line, "{")
        if first < 0:
            out.append(line)
            continue
        before = line[:first].strip()
        if before.startswith("*"):
            out.append(line)          # 数组块整体保留
            continue
        depth, in_str, esc, last = 0, False, False, -1
        for i in range(first, len(line)):
            ch = line[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    last = i
                    break
        if last < 0:
            out.append(line)          # 未闭合，交给主循环处理
            continue
        out.append(line[:first + 1])
        out.extend(_expand_inline_blocks(line[first + 1:last]))
        out.append("}")
        tail = line[last + 1:].strip()
        if tail:
            out.append(tail)
    return out


def parse_ascii(path: str | Path) -> FbxNode:
    """解析 FBX ASCII 文件，返回根节点（子节点为顶层分区）。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    root = FbxNode(name="__root__")
    stack = [root]
    pending = None            # 跨行数组缓冲（(key, buf)）

    for raw in _expand_inline_blocks(text):
        if pending is not None:
            key, buf = pending
            buf += "\n" + raw
            if buf.count("{") <= buf.count("}"):
                node = FbxNode(name=key, properties=_parse_values_block(buf))
                stack[-1].children.append(node)
                pending = None
            else:
                pending = (key, buf)   # 累积行写回，等闭合
            continue
        line = _strip_comment(raw).strip()
        if not line:
            continue
        if line == "}":
            if len(stack) > 1:
                stack.pop()
            continue
        m = _NODE_RE.match(line)
        if not m:
            # FBX 6.1：Vertices / PVI / Normals / UV 常折行，续行无 `Key:`
            if stack[-1].children and _looks_like_values(line):
                extra = _parse_values_block(line)
                stack[-1].children[-1].properties.extend(extra)
            continue
        key, rest = m.group(1).strip(), (m.group(2) or "").strip()
        if rest.startswith("*") and rest.count("{") > rest.count("}"):
            pending = (key, rest)   # 数组跨行，等闭合
            continue
        has_block = rest.startswith("{") or rest.rstrip().endswith("{")
        values_text = rest
        if has_block:
            values_text = rest.lstrip("{").rstrip("{").strip()
        node = FbxNode(name=key,
                       properties=_parse_values_block(values_text) if values_text else [])
        stack[-1].children.append(node)
        if has_block:
            stack.append(node)
    return root


_NODE_RE = re.compile(r"^([^:{}]+):\s*(.*)$")


def _looks_like_values(line: str) -> bool:
    s = line.lstrip()
    return bool(s) and (s[0] in '+-."\'' or s[0].isdigit())


def read_ascii_version(path: str | Path) -> int | None:
    """从文件头附近读 FBXVersion；找不到返回 None。"""
    text = Path(path).read_text(encoding="utf-8", errors="replace")[:4096]
    m = re.search(r"FBXVersion:\s*(\d+)", text)
    return int(m.group(1)) if m else None
