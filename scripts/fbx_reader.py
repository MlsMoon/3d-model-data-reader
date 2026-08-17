#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 模型读取器（纯标准库，零依赖）。

支持 FBX ASCII 与 FBX 二进制（结构级解析：record 树 -> 对象/连接/层级）。
二进制 record 头布局因版本而异（13/16/17/20 字节候选 + 7500+ 头部 padding），
解析前自动做"布局探测"（锚点断言：FBXHeaderVersion 属性 = 1004、FBXVersion 属性 = 版本号）。

用法：
  python fbx_reader.py <file.fbx> [--summary|--json|--tree [N]|--objects|--geometry ID|--skeleton|--info]
"""
import argparse
import json
import struct
import sys
import zlib
from dataclasses import dataclass, field
from pathlib import Path

FBX_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"


@dataclass
class FbxNode:
    """FBX 节点（record）。name 为节点名，properties 为已解码属性列表。"""
    name: str
    properties: list = field(default_factory=list)
    children: list["FbxNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 格式检测与版本
# ---------------------------------------------------------------------------

def detect_format(path: str | Path) -> str:
    """返回 'binary' | 'ascii' | 'unknown'。ASCII 用 FBX 关键字启发式判定。"""
    with open(path, "rb") as fp:
        head = fp.read(23)
    if head == FBX_MAGIC:
        return "binary"
    with open(path, "r", encoding="utf-8", errors="replace") as fp:
        sample = fp.read(4096)
    if "FBXHeaderExtension" in sample or "FBXVersion" in sample:
        return "ascii"
    return "unknown"


def read_version(path: str | Path) -> int | None:
    """二进制 FBX 版本号（字节 23-26 LE）；非二进制返回 None。"""
    with open(path, "rb") as fp:
        head = fp.read(27)
    if head[:23] != FBX_MAGIC:
        return None
    return struct.unpack_from("<I", head, 23)[0]


# ---------------------------------------------------------------------------
# 二进制解析（含布局探测）
# ---------------------------------------------------------------------------

# 候选 record 头大小（字节）：
#   13 = 经典：end(4) + num(4) + plen(4) + nlen(1)，end 为相对偏移
#   17 = 前带 4 字节 CRC 的经典头
#   25 = 实测 FBX 7.7：end(4) + rsvd(4) + num(4) + rsvd(4) + plen(4) + rsvd(4) + nlen(1)，
#        end 为下一 record 的绝对文件偏移（见 references/fbx-binary-format.md §7 实测）
_CANDIDATE_HEADERS = (13, 17, 25)


def _try_layout(data: bytes, start: int, header_size: int, version: int) -> FbxNode | None:
    """用指定布局尝试解析根节点。锚点断言失败或解析异常返回 None（换下一候选）。"""
    try:
        node, _ = _read_record(data, start, header_size, version)
    except (ValueError, struct.error, IndexError):
        return None
    if node is None:
        return None

    def find(n: FbxNode, name: str) -> FbxNode | None:
        if n.name == name:
            return n
        for c in n.children:
            found = find(c, name)
            if found:
                return found
        return None

    fbv = find(node, "FBXHeaderVersion")
    fbver = find(node, "FBXVersion")
    ok_version = fbver is not None and fbver.properties and fbver.properties[0] == version
    ok_header = fbv is not None and fbv.properties and fbv.properties[0] == 1004
    return node if (ok_version and ok_header) else None


def _probe_layout(data: bytes, version: int) -> tuple[int, int]:
    """探测 (root_start, header_size)。全失败抛 RuntimeError。"""
    for start in (27, 31):
        for header_size in _CANDIDATE_HEADERS:
            node = _try_layout(data, start, header_size, version)
            if node is not None:
                return start, header_size
    raise RuntimeError(
        f"无法确定二进制布局（版本 {version}）：锚点断言（FBXHeaderVersion=1004, "
        f"FBXVersion={version}）未命中任何候选布局。详见 references/fbx-binary-format.md §7")


def parse_binary(path: str | Path) -> FbxNode:
    """解析二进制 FBX，返回根节点（子节点 = 全部顶层分区）。自动做布局探测。"""
    data = Path(path).read_bytes()
    if data[:23] != FBX_MAGIC:
        raise ValueError("不是二进制 FBX（magic 不符）")
    version = struct.unpack_from("<I", data, 23)[0]
    start, header_size = _probe_layout(data, version)
    root = FbxNode(name="__root__")
    pos = start
    while pos < len(data):
        node, pos = _read_record(data, pos, header_size, version)
        if node is None:
            break
        root.children.append(node)
    if not root.children:
        raise RuntimeError("解析根节点失败")
    return root


# 单值属性类型：code -> (fmt, 字节数)
_SCALAR_TYPES = {"Y": ("<h", 2), "C": ("<b", 1), "I": ("<i", 4),
                 "F": ("<f", 4), "D": ("<d", 8), "L": ("<q", 8)}


def _read_record(data: bytes, offset: int, header_size: int,
                 version: int) -> tuple[FbxNode | None, int]:
    """读取一个 record 及其子节点。返回 (节点或 None, 下一偏移)。"""
    if offset + header_size > len(data):
        return None, len(data)
    if header_size == 13:          # 经典头：end(相对) + num + plen + nlen1
        end_off, num_props, prop_len = struct.unpack_from("<III", data, offset)
        name_len = data[offset + 12]
        end = offset + end_off if end_off > 0 else len(data)
    elif header_size == 17:        # 经典头前带 4 字节 CRC
        end_off, num_props, prop_len = struct.unpack_from("<III", data, offset + 4)
        name_len = data[offset + 16]
        end = offset + end_off if end_off > 0 else len(data)
    else:                          # 25 字节头（实测 7.7）：end(绝对) + rsvd + num + rsvd + plen + rsvd + nlen1
        end_off, _, num_props, _, prop_len, _ = struct.unpack_from("<IIIIII", data, offset)
        name_len = data[offset + 24]
        end = end_off              # 下一 record 的绝对文件偏移
    # null record：全零 -> 流结束
    if end_off == 0 and num_props == 0 and prop_len == 0 and name_len == 0:
        return None, offset
    name = data[offset + header_size: offset + header_size + name_len]
    name = name.rstrip(b"\x00").decode("utf-8", errors="replace")
    body = offset + header_size + name_len

    node = FbxNode(name=name)
    for _ in range(num_props):
        if body + 1 > len(data):
            break
        value, body = _parse_property(data, body)
        node.properties.append(value)

    # 子节点：从属性区末尾到 end 边界
    while body < end:
        child, body = _read_record(data, body, header_size, version)
        if child is None:
            break
        node.children.append(child)
    return node, end


def _parse_property(data: bytes, offset: int) -> tuple[object, int]:
    """读一个属性。返回 (值, 下一偏移)。数组按元素类型展开为 Python list。"""
    code = chr(data[offset])
    pos = offset + 1
    if code in _SCALAR_TYPES:
        fmt, size = _SCALAR_TYPES[code]
        return struct.unpack_from(fmt, data, pos)[0], pos + size
    if code == "S":
        length = struct.unpack_from("<I", data, pos)[0]
        raw = data[pos + 4: pos + 4 + length].rstrip(b"\x00")
        return raw.decode("utf-8", errors="replace"), pos + 4 + length
    if code == "R":
        length = struct.unpack_from("<I", data, pos)[0]
        return data[pos + 4: pos + 4 + length], pos + 4 + length
    if code in "fdlibc":
        return _read_array(data, pos, code)
    raise ValueError(f"未知属性类型 '{code}' @ {offset}")


def _read_array(data: bytes, offset: int, code: str) -> tuple[list, int]:
    """数组：[元素数][encoding][压缩后长度][数据]；encoding=1 时 raw DEFLATE 解压。"""
    count, encoding, comp_len = struct.unpack_from("<III", data, offset)
    pos = offset + 12
    raw = data[pos: pos + comp_len]
    if encoding == 1:
        raw = _decompress(raw)
    pos += comp_len

    if code == "c":
        return list(raw), pos
    if code == "b":
        return list(raw[:count]), pos
    fmt = {"f": "<f", "d": "<d", "l": "<q", "i": "<i"}[code]
    size = struct.calcsize(fmt)
    values = [struct.unpack_from(fmt, raw, i * size)[0] for i in range(count)]
    return values, pos


def _decompress(raw: bytes) -> bytes:
    """FBX 数组压缩数据解压：先试标准 zlib 头（实测 7.7 导出文件），
    失败再试 raw DEFLATE（经典 FBX 规范）。"""
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return zlib.decompress(raw, -15)


# ---------------------------------------------------------------------------
# ASCII 解析（行级）
# ---------------------------------------------------------------------------

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


_TYPE_RE = __import__("re").compile(r"^([a-zA-Z])\s*:\s*(.+)$")


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


_NODE_RE = __import__("re").compile(r"^([^:{}]+):\s*(.*)$")


# ---------------------------------------------------------------------------
# 语义层（与格式无关：对象 / 连接 / 层级 / 几何 / 骨架）
# ---------------------------------------------------------------------------

def _find_all(node: FbxNode, name: str, out: list[FbxNode]) -> None:
    if node.name == name:
        out.append(node)
    for c in node.children:
        _find_all(c, name, out)


def _objects_node(root: FbxNode) -> FbxNode | None:
    for c in root.children:
        if c.name == "Objects":
            return c
    return None


def _obj_id(node: FbxNode) -> int | None:
    """对象 ID：二进制 O 节点属性为 [类型, 名称, 标志...]（取最后一个 int）；
    ASCII 节点（Model:/Geometry: 等）ID 是第一个属性。"""
    if node.name == "O":
        for prop in reversed(node.properties):
            if isinstance(prop, int):
                return prop
        return None
    for prop in node.properties:
        if isinstance(prop, int):
            return prop
    return None


def collect_objects(root: FbxNode) -> dict[int, FbxNode]:
    """Objects 分区下的对象节点按 ID 索引。
    兼容二进制（节点名 O）与 ASCII（节点名为 Model/Geometry/...）。"""
    objs: dict[int, FbxNode] = {}
    objects = _objects_node(root)
    if objects is None:
        return objs
    for child in objects.children:
        oid = _obj_id(child)
        if oid is not None:
            objs[oid] = child
    return objs


def build_connections(root: FbxNode) -> list[tuple[str, int, int, str]]:
    """Connections 分区的 C 节点 -> [(kind, child, parent, prop)]。"""
    conns: list[tuple[str, int, int, str]] = []
    for c in root.children:
        if c.name != "Connections":
            continue
        for cc in c.children:
            if cc.name != "C" or len(cc.properties) < 3:
                continue
            kind = cc.properties[0]
            child, parent = cc.properties[1], cc.properties[2]
            prop = cc.properties[3] if len(cc.properties) > 3 and \
                isinstance(cc.properties[3], str) else ""
            conns.append((kind, int(child), int(parent), prop))
    return conns


def build_model_tree(root: FbxNode) -> list[FbxNode]:
    """按 OO 连接排出 Model 树（返回根节点列表；父 ID=0 或未连接者为根）。"""
    objs = collect_objects(root)
    parent_of: dict[int, int] = {}
    for kind, child, parent, _ in build_connections(root):
        if kind == "OO" and child in objs and parent in objs:
            parent_of[child] = parent
    roots = [n for oid, n in objs.items() if oid not in parent_of]
    return roots


def geometry_stats(root: FbxNode) -> dict:
    """汇总 Geometry 的顶点/面统计与整体包围盒。"""
    geoms: list[FbxNode] = []
    _find_all(root, "Geometry", geoms)
    total_verts, total_faces = 0, 0
    bounds = []
    for g in geoms:
        for c in g.children:
            if c.name == "Vertices" and c.properties:
                v = c.properties[0]
                if isinstance(v, list) and v:
                    total_verts += len(v) // 3
                    for i in range(0, len(v) - 2, 3):
                        bounds.append(tuple(v[i: i + 3]))
        pvi = None
        for c in g.children:
            if c.name == "PolygonVertexIndex" and c.properties and \
                    isinstance(c.properties[0], list):
                pvi = c.properties[0]
        if pvi:
            total_faces += sum(1 for x in pvi if x < 0)
    bmin, bmax = (None, None)
    if bounds:
        bmin = tuple(min(b[i] for b in bounds) for i in range(3))
        bmax = tuple(max(b[i] for b in bounds) for i in range(3))
    return {"geometry_count": len(geoms), "vertices": total_verts,
            "faces": total_faces, "bounds_min": bmin, "bounds_max": bmax}


def skeleton_chains(root: FbxNode) -> list[list[FbxNode]]:
    """找 Model 中 Skeleton/LimbNode 属性节点的父子链（基于 OO 连接，从链头向下）。"""
    objs = collect_objects(root)
    parent_of: dict[int, int] = {}
    children_of: dict[int, list[int]] = {}
    for kind, child, parent, _ in build_connections(root):
        if kind == "OO" and child in objs and parent in objs:
            parent_of[child] = parent
            children_of.setdefault(parent, []).append(child)
    is_bone = {oid: any(
        (isinstance(prop, str) and prop in ("Skeleton", "LimbNode", "RootNode"))
        for prop in node.properties) for oid, node in objs.items()}
    chains: list[list[FbxNode]] = []
    for oid, node in objs.items():
        # 链头：是骨骼，且父节点不是骨骼
        if is_bone.get(oid) and (oid not in parent_of or not is_bone.get(parent_of.get(oid))):
            chain = []
            cur = oid
            while cur in objs and is_bone.get(cur):
                chain.append(objs[cur])
                nexts = [c for c in children_of.get(cur, []) if is_bone.get(c)]
                cur = nexts[0] if nexts else -1
            if len(chain) > 1:
                chains.append(chain)
    return chains


def global_settings(root: FbxNode) -> dict:
    """GlobalSettings 中单位与轴信息。"""
    out: dict = {}
    for c in root.children:
        if c.name != "GlobalSettings":
            continue
        for p in c.children:
            if p.name != "Properties70":
                continue
            for entry in p.children:
                if entry.name != "P" or not entry.properties:
                    continue
                key = entry.properties[0]
                if key in ("UnitScaleFactor", "UpAxis", "UpAxisSign", "FrontAxis"):
                    vals = [x for x in entry.properties[4:] if not isinstance(x, str)]
                    out[key] = vals[0] if len(vals) == 1 else vals
    return out


def print_tree(node: FbxNode, depth: int = 0, max_depth: int = 8) -> None:
    if depth > max_depth:
        return
    if node.name == "__root__":
        for c in node.children:
            print_tree(c, depth, max_depth)
        return
    props = ", ".join(str(p)[:40] for p in node.properties[:4])
    print("  " * depth + f"{node.name}" + (f": {props}" if props else ""))
    for c in node.children:
        print_tree(c, depth + 1, max_depth)


def _obj_kind(node: FbxNode) -> str:
    """对象类型：ASCII 用节点名（Model/Geometry/...），二进制 O 节点用第一个属性。"""
    if node.name != "O":
        return node.name
    return str(node.properties[0]) if node.properties else "?"


def summarize(root: FbxNode) -> dict:
    """结构化摘要（--json 输出此结构）。"""
    objs = collect_objects(root)
    kinds: dict[str, int] = {}
    for node in objs.values():
        kinds[_obj_kind(node)] = kinds.get(_obj_kind(node), 0) + 1
    geo = geometry_stats(root)
    return {"objects": kinds, **geo, "settings": global_settings(root)}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="FBX 模型读取器（纯标准库，ASCII + 二进制）")
    ap.add_argument("file", help="FBX 文件路径")
    ap.add_argument("--summary", action="store_true", help="输出摘要（默认）")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--tree", type=int, nargs="?", const=8, metavar="N", help="打印节点树（前 N 层）")
    ap.add_argument("--objects", action="store_true", help="列出全部对象 ID/类型/名称")
    ap.add_argument("--geometry", type=int, metavar="ID", help="打印指定 Geometry 摘要")
    ap.add_argument("--skeleton", action="store_true", help="打印骨架链")
    ap.add_argument("--info", action="store_true", help="仅打印头部信息（格式/版本）")
    args = ap.parse_args(argv)

    path = Path(args.file)
    try:
        fmt = detect_format(path)
        version = read_version(path)
        if args.info:
            print(f"格式: {fmt}")
            print(f"版本: {version if version is not None else '—（非二进制）'}")
            return 0
        if fmt == "unknown":
            print(f"错误: 不是可识别的 FBX 文件（非二进制 magic，且不含 FBX 关键字）: {path}",
                  file=sys.stderr)
            return 1
        root = parse_binary(path) if fmt == "binary" else parse_ascii(path)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summarize(root), ensure_ascii=False, indent=2))
        return 0
    if args.tree is not None:
        print_tree(root, max_depth=args.tree)
        return 0
    if args.objects:
        for oid, node in sorted(collect_objects(root).items()):
            name = node.properties[1] if len(node.properties) > 1 else "?"
            print(f"{oid}  {_obj_kind(node)}  {str(name)[:60]}")
        return 0
    if args.skeleton:
        for i, chain in enumerate(skeleton_chains(root)):
            print(f"骨架链 {i}: " + " -> ".join(
                (n.properties[1] if len(n.properties) > 1 else n.name) for n in chain))
        return 0
    if args.geometry is not None:
        objs = collect_objects(root)
        g = objs.get(args.geometry)
        if g is None:
            print(f"错误: 没有 ID {args.geometry} 的对象", file=sys.stderr)
            return 1
        print(f"对象 {args.geometry}: {g.properties[1] if len(g.properties) > 1 else '?'}")
        for c in g.children:
            if c.name in ("Vertices", "PolygonVertexIndex", "LayerElementNormal",
                          "LayerElementUV", "LayerElementMaterial") and c.properties:
                v = c.properties[0]
                print(f"  {c.name}: {'数组 len=' + str(len(v)) if isinstance(v, list) else v}")
        return 0

    s = summarize(root)
    fmt = detect_format(path)
    version = read_version(path)
    print(f"文件: {path}")
    print(f"格式: {fmt}" + (f" (版本 {version})" if version else ""))
    kinds = ", ".join(f"{k}×{v}" for k, v in sorted(s["objects"].items())) or "(无)"
    print(f"对象: {kinds}")
    print(f"几何: {s['geometry_count']} 个网格, 顶点 {s['vertices']}, 面 {s['faces']}")
    if s["bounds_min"]:
        print(f"包围盒: {tuple(s['bounds_min'])} - {tuple(s['bounds_max'])}")
    st = s["settings"]
    if st:
        print("设置: " + ", ".join(f"{k}={v}" for k, v in st.items()))
    for i, chain in enumerate(skeleton_chains(root)):
        print(f"骨架链 {i}: " + " -> ".join(
            (n.properties[1] if len(n.properties) > 1 else n.name) for n in chain))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
