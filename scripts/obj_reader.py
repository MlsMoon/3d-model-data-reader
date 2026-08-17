#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OBJ 模型读取器（纯标准库，零依赖）。

读取 OBJ 文件的顶点/UV/法线/面/对象/组，支持：
  - 索引语义：1-based、负数（-1 = 最后一条）
  - 面四种写法：f v / f v/vt / f v//vn / f v/vt/vn
  - n-gon 三角化（扇形）
  - (v, vt, vn) 三元组 -> 顶点缓冲重映射（去重）
  - 人类可读摘要（默认）或 --json 结构化输出

用法：
  python obj_reader.py <file.obj> [--summary|--json|--vertices N|--faces N|--bounds|--remap]
"""
import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ObjFace:
    """一个面。索引均为已解析的 0-based（越界为 None 时整面被丢弃）。"""
    vertex_indices: list[int]
    uv_indices: list[int] | None = None
    normal_indices: list[int] | None = None
    object_name: str = ""
    group_names: list[str] = field(default_factory=list)
    material_name: str | None = None
    smoothing_group: str | None = None


@dataclass
class ObjData:
    """解析结果。"""
    path: Path
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)
    normals: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[ObjFace] = field(default_factory=list)
    objects: dict[str, list[int]] = field(default_factory=dict)   # 对象名 -> 面索引
    groups: dict[str, list[int]] = field(default_factory=dict)    # 组名 -> 面索引
    materials: set[str] = field(default_factory=set)
    mtllib: str | None = None
    raw_face_count: int = 0        # 含 >3 顶点的多边形数
    warnings: list[str] = field(default_factory=list)  # 未解析行，含行号


def resolve_index(idx: int, count: int) -> int | None:
    """OBJ 索引(1-based, 负数=从尾部数) -> 0-based；越界返回 None。"""
    out = idx - 1 if idx > 0 else count + idx if idx < 0 else -1
    return out if 0 <= out < count else None


def parse_obj(path: str | Path) -> ObjData:
    """逐行解析 OBJ 文件。未知语句记入 warnings，不中断。"""
    p = Path(path)
    data = ObjData(path=p)
    cur_obj, cur_groups, cur_mat, cur_smooth = "", [], None, None

    with open(p, "r", encoding="utf-8", errors="replace") as fp:
        lines = fp.readlines()

    # 合并反斜杠续行
    merged: list[str] = []
    for ln in lines:
        if merged and merged[-1].rstrip().endswith("\\"):
            merged[-1] = merged[-1].rstrip()[:-1] + ln
        else:
            merged.append(ln)

    for lineno, raw in enumerate(merged, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        kw, args = parts[0], parts[1:]

        try:
            if kw == "v":
                data.vertices.append(tuple(float(x) for x in args[:3]))
            elif kw == "vt":
                data.uvs.append(tuple(float(x) for x in args[:2]))
            elif kw == "vn":
                data.normals.append(tuple(float(x) for x in args[:3]))
            elif kw == "o":
                cur_obj = args[0] if args else ""
                data.objects.setdefault(cur_obj, [])
            elif kw == "g":
                cur_groups = list(args)
                for g in cur_groups:
                    data.groups.setdefault(g, [])
            elif kw == "usemtl":
                cur_mat = args[0] if args else None
                if cur_mat:
                    data.materials.add(cur_mat)
            elif kw == "mtllib":
                data.mtllib = args[0] if args else None
            elif kw == "s":
                cur_smooth = args[0] if args else "off"
            elif kw == "f":
                face = _parse_face(args, data, lineno, cur_obj, cur_groups, cur_mat, cur_smooth)
                if face is not None:
                    data.faces.append(face)
                    data.objects.setdefault(cur_obj, []).append(len(data.faces) - 1)
                    for g in cur_groups:
                        data.groups[g].append(len(data.faces) - 1)
                    if len(face.vertex_indices) > 3:
                        data.raw_face_count += 1
            else:
                data.warnings.append(f"L{lineno}: 未识别的语句 '{kw}'")
        except (ValueError, IndexError) as exc:
            data.warnings.append(f"L{lineno}: 解析失败 ({exc}): {line[:60]}")

    return data


def _parse_face(args: list[str], data: ObjData, lineno: int,
                obj: str, groups: list[str], mat: str | None, smooth: str | None) -> ObjFace | None:
    """解析 f 行：每个元素为 v[/vt][/vn] 形式，索引转 0-based。"""
    v_idx, vt_idx, vn_idx = [], [], []
    n_uv, n_nrm = len(data.uvs), len(data.normals)
    for tok in args:
        parts = tok.split("/")
        vi = resolve_index(int(parts[0]), len(data.vertices))
        if vi is None:
            data.warnings.append(f"L{lineno}: 顶点索引越界 '{tok}'")
            return None
        v_idx.append(vi)
        if len(parts) > 1 and parts[1] != "":
            ti = resolve_index(int(parts[1]), n_uv)
            if ti is None:
                data.warnings.append(f"L{lineno}: UV 索引越界 '{tok}'")
                return None
            vt_idx.append(ti)
        if len(parts) > 2 and parts[2] != "":
            ni = resolve_index(int(parts[2]), n_nrm)
            if ni is None:
                data.warnings.append(f"L{lineno}: 法线索引越界 '{tok}'")
                return None
            vn_idx.append(ni)
    return ObjFace(vertex_indices=v_idx,
                   uv_indices=vt_idx or None,
                   normal_indices=vn_idx or None,
                   object_name=obj, group_names=list(groups),
                   material_name=mat, smoothing_group=smooth)


def compute_bounds(verts: list[tuple[float, float, float]]) -> tuple[tuple, tuple]:
    """返回 (min, max) 两个三元组。空输入返回 ((0,0,0),(0,0,0))。"""
    if not verts:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    mins = tuple(min(v[i] for v in verts) for i in range(3))
    maxs = tuple(max(v[i] for v in verts) for i in range(3))
    return mins, maxs


@dataclass
class RemapResult:
    """(v, vt, vn) 三元组去重后的顶点缓冲。"""
    positions: list[tuple[float, float, float]]
    normals: list[tuple[float, float, float]]
    uvs: list[tuple[float, float]]
    index_buffer: list[int]
    stats: dict[str, int]          # 唯一顶点数 / 去重前(面角数) / 面数


def remap_to_vertex_buffer(obj: ObjData, triangulate: bool = True) -> RemapResult:
    """把面的 (v,vt,vn) 三元组去重为唯一顶点 + index buffer（n-gon 扇形三角化）。"""
    remap: dict[tuple, int] = {}
    positions, normals, uvs, index_buffer = [], [], [], []
    for face in obj.faces:
        corners = list(zip(face.vertex_indices,
                           face.uv_indices or [None] * len(face.vertex_indices),
                           face.normal_indices or [None] * len(face.vertex_indices)))
        if len(corners) == 3 or not triangulate:
            groups = [corners]
        else:
            groups = [[corners[0], corners[i], corners[i + 1]]
                      for i in range(1, len(corners) - 1)]
        for tri in groups:
            for v, vt, vn in tri:
                key = (v, vt, vn)
                if key not in remap:
                    remap[key] = len(positions)
                    positions.append(obj.vertices[v])
                    if vt is not None:
                        uvs.append(obj.uvs[vt])
                    if vn is not None:
                        normals.append(obj.normals[vn])
                index_buffer.append(remap[key])
    corner_count = sum(max(len(f.vertex_indices), 3) for f in obj.faces)
    return RemapResult(positions=positions, normals=normals, uvs=uvs,
                       index_buffer=index_buffer,
                       stats={"unique_vertices": len(positions),
                              "corner_count": corner_count,
                              "face_count": len(obj.faces)})


def summarize(obj: ObjData) -> dict:
    """结构化摘要（--json 输出此结构）。"""
    mn, mx = compute_bounds(obj.vertices)
    return {
        "path": str(obj.path),
        "vertices": len(obj.vertices),
        "uvs": len(obj.uvs),
        "normals": len(obj.normals),
        "faces": len(obj.faces),
        "raw_faces_gt_3": obj.raw_face_count,
        "bounds_min": list(mn),
        "bounds_max": list(mx),
        "objects": {k: len(v) for k, v in obj.objects.items()},
        "groups": {k: len(v) for k, v in obj.groups.items()},
        "materials": sorted(obj.materials),
        "mtllib": obj.mtllib,
        "warnings": obj.warnings,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="OBJ 模型读取器（纯标准库）")
    ap.add_argument("file", help="OBJ 文件路径")
    ap.add_argument("--summary", action="store_true", help="输出摘要（默认）")
    ap.add_argument("--json", action="store_true", help="输出结构化 JSON")
    ap.add_argument("--vertices", type=int, metavar="N", help="打印前 N 条顶点")
    ap.add_argument("--faces", type=int, metavar="N", help="打印前 N 个面（0-based 索引）")
    ap.add_argument("--bounds", action="store_true", help="仅输出包围盒")
    ap.add_argument("--remap", action="store_true", help="顶点缓冲重映射统计")
    args = ap.parse_args(argv)

    try:
        obj = parse_obj(args.file)
    except OSError as exc:
        print(f"错误: 无法读取文件: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summarize(obj), ensure_ascii=False, indent=2))
        return 0
    if args.bounds:
        mn, mx = compute_bounds(obj.vertices)
        print(f"min: {mn}\nmax: {mx}")
        return 0
    if args.remap:
        r = remap_to_vertex_buffer(obj)
        print(f"面角总数: {r.stats['corner_count']}  唯一顶点: {r.stats['unique_vertices']}"
              f"  (去重后 {r.stats['unique_vertices'] / max(r.stats['corner_count'], 1):.1%})")
        return 0

    s = summarize(obj)
    if args.vertices is not None:
        for i, v in enumerate(obj.vertices[:args.vertices]):
            print(f"v{i}: {v}")
    elif args.faces is not None:
        for i, f in enumerate(obj.faces[:args.faces]):
            print(f"f{i}: v={f.vertex_indices} vt={f.uv_indices} vn={f.normal_indices} "
                  f"[{f.object_name}/{','.join(f.group_names)}/{f.material_name}]")
    else:
        print(f"文件: {s['path']}")
        print(f"顶点: {s['vertices']}  UV: {s['uvs']}  法线: {s['normals']}  面: {s['faces']}"
              f"  (n-gon: {s['raw_faces_gt_3']})")
        print(f"包围盒: {tuple(s['bounds_min'])} - {tuple(s['bounds_max'])}")
        objs = ", ".join(f"{k}({v}面)" for k, v in s["objects"].items()) or "(无)"
        print(f"对象: {objs}")
        grps = ", ".join(f"{k}({v}面)" for k, v in s["groups"].items()) or "(无)"
        print(f"组: {grps}")
        print(f"材质: {', '.join(s['materials']) or '(无)'}   mtllib: {s['mtllib'] or '(无)'}")
        print(f"警告: {len(s['warnings'])}")
        for w in s["warnings"][:10]:
            print(f"  ! {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

