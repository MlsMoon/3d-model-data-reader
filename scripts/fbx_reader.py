#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 模型读取器入口（纯标准库，零依赖）。

实现拆在同目录：fbx_types / fbx_binary / fbx_ascii / fbx_scene。
本文件只保留格式检测、对外 re-export 与 CLI。
对外 import 保持不变：parse_binary / collect_objects / build_connections。

用法：
  python fbx_reader.py <file.fbx> [--summary|--json|--tree [N]|--objects|--geometry ID|--skeleton|--info]
"""
import argparse
import json
import sys
from pathlib import Path

from fbx_ascii import parse_ascii
from fbx_binary import parse_binary, probe_layout, read_version
from fbx_scene import (  # noqa: F401  # re-export for extract_submeshes
    build_connections,
    collect_objects,
    print_skeleton_tree,
    print_tree,
    skeleton_chains,
    summarize,
    _obj_kind,
)
from fbx_types import FBX_MAGIC, FbxNode, fbx_display_name

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
            if fmt == "binary" and version is not None:
                data = Path(path).read_bytes()
                start, header_size = probe_layout(data, version)
                print(f"布局: root_start={start}, header_size={header_size}")
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
            print(f"{oid}  {_obj_kind(node)}  {fbx_display_name(name)[:60]}")
        return 0
    if args.skeleton:
        print_skeleton_tree(root)
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
    chains = skeleton_chains(root)
    if chains:
        print(f"骨架链: {len(chains)} 条（沿每棵树第一子节点；完整树用 --skeleton）")
        for i, chain in enumerate(chains[:5]):
            print("  " + " -> ".join(
                fbx_display_name(n.properties[1] if len(n.properties) > 1 else n.name)
                for n in chain))
        if len(chains) > 5:
            print(f"  ... 另有 {len(chains) - 5} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
