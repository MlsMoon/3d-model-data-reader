#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 二进制解析与布局探测（纯标准库）。

record 头：<7500 为 13 字节，>=7500 为 25 字节。
end_offset 一律按文件绝对偏移解析。
锚点：FBXHeaderVersion ∈ {1003,1004}，FBXVersion = 文件头版本号。
"""
import struct
import zlib
from pathlib import Path

from fbx_types import FBX_MAGIC, FbxNode

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
#   13 = <7500 经典：end(4) + num(4) + plen(4) + nlen(1)
#   17 = 前带 4 字节 CRC 的经典头（少见）
#   25 = >=7500：end(8 拆成 end4+rsvd4 的兼容读法见下) / 实测 7.7 为
#        end(4)+rsvd(4)+num(4)+rsvd(4)+plen(4)+rsvd(4)+nlen(1)
# Blender encode_bin / Autodesk：end_offset 一律是**文件绝对偏移**（不是相对）。
# 抽样实测：7400 命中 (27,13)；7700 命中 (27,25)。
_CANDIDATE_HEADERS = (13, 17, 25)

# FBXHeaderVersion：7.7 常见 1004；7.4 及更早资产常见 1003（抽样实测）。
_HEADER_VERSION_OK = {1003, 1004}

def _try_layout(data: bytes, start: int, header_size: int, version: int) -> FbxNode | None:
    """用指定布局尝试解析根节点。锚点断言失败或解析异常返回 None（换下一候选）。"""
    try:
        node, _ = _read_record(data, start, header_size, version)
    except (ValueError, struct.error, IndexError, OverflowError):
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
    ok_header = (
        fbv is not None
        and fbv.properties
        and isinstance(fbv.properties[0], int)
        and fbv.properties[0] in _HEADER_VERSION_OK
    )
    return node if (ok_version and ok_header) else None


def probe_layout(data: bytes, version: int) -> tuple[int, int]:
    """探测 (root_start, header_size)。全失败抛 RuntimeError。"""
    for start in (27, 31):
        for header_size in _CANDIDATE_HEADERS:
            node = _try_layout(data, start, header_size, version)
            if node is not None:
                return start, header_size
    raise RuntimeError(
        f"无法确定二进制布局（版本 {version}）：锚点断言（FBXHeaderVersion in "
        f"{sorted(_HEADER_VERSION_OK)}, FBXVersion={version}）未命中任何候选布局。"
        f"详见 references/fbx-binary-format.md §7")


def parse_binary(path: str | Path) -> FbxNode:
    """解析二进制 FBX，返回根节点（子节点 = 全部顶层分区）。自动做布局探测。"""
    data = Path(path).read_bytes()
    if data[:23] != FBX_MAGIC:
        raise ValueError("不是二进制 FBX（magic 不符）")
    version = struct.unpack_from("<I", data, 23)[0]
    start, header_size = probe_layout(data, version)
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
    if header_size == 13:          # <7500：end(绝对) + num + plen + nlen1
        end_off, num_props, prop_len = struct.unpack_from("<III", data, offset)
        name_len = data[offset + 12]
        end = end_off if end_off > 0 else len(data)
    elif header_size == 17:        # 经典头前带 4 字节 CRC；end 仍为绝对偏移
        end_off, num_props, prop_len = struct.unpack_from("<III", data, offset + 4)
        name_len = data[offset + 16]
        end = end_off if end_off > 0 else len(data)
    else:                          # 25 字节头（实测 7.7）：end(绝对) + rsvd + num + rsvd + plen + rsvd + nlen1
        end_off, _, num_props, _, prop_len, _ = struct.unpack_from("<IIIIII", data, offset)
        name_len = data[offset + 24]
        end = end_off              # 下一 record 的绝对文件偏移
    # null record：全零 -> 流结束
    if end_off == 0 and num_props == 0 and prop_len == 0 and name_len == 0:
        return None, offset
    # 绝对 end 必须落在当前 offset 之后，否则布局候选错误
    if end_off != 0 and end <= offset:
        raise ValueError(f"record end_offset={end_off} 不大于当前 offset={offset}")
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

_probe_layout = probe_layout
