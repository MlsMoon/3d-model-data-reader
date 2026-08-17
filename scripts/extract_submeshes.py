#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 FBX 拆出指定子网格（Model 名匹配），可选重定中心，输出独立二进制 FBX。

典型用途：源 FBX 把多个小片烘焙在同一个文件里（位置在顶点、节点单位变换），
需要把每片拆成独立 FBX 并把网格中心平移到原点，便于单独摆放与引用。

用法：
  python extract_submeshes.py <input.fbx> --models 名1,名2,名3,名4 \
      --output-dir <目录> [--prefix 文件前缀] [--center]

--center : 每个子网格顶点整体平移，使 AABB 中心落在原点（默认不平移）。
命名     : 输出 <output-dir>/<prefix><序号>.fbx（二进制 FBX 7700），
           序号与 --models 列表顺序一致。
依赖     : 同目录 fbx_reader.py（解析）+ fbx_bin_export.py（二进制序列化）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fbx_reader import parse_binary, collect_objects, build_connections  # noqa: E402
from fbx_bin_export import write_fbx_binary  # noqa: E402


# ---------------------------------------------------------------------------
# FBX 对象树辅助
# ---------------------------------------------------------------------------

def find_child(node, name):
    """返回第一个名为 name 的子节点；不存在返回 None。"""
    for child in node.children:
        if child.name == name:
            return child
    return None


def child_value(node, name, default=None):
    child = find_child(node, name)
    if child is None or not child.properties:
        return default
    return child.properties[0]


def collect_mesh_geometry(root):
    """返回 {model_name: geometry_node}。

    二进制 FBX 的 O 节点属性为 [ID, 名称+类型, 子类型]：
      - properties[1] = "名称\\x00\\x01类型"（名称在前、类型在后）
      - properties[2] = 子类型（"Mesh"/"Null"）
    Geometry 通过 OO 连接挂在 Model 下（child=Geometry, parent=Model）。
    """
    objects = collect_objects(root)
    connections = build_connections(root)

    model_kind = {}  # model_id -> 子类型（Mesh/Null）
    for oid, node in objects.items():
        if not node.properties:
            continue
        name_type = str(node.properties[1])
        parts = name_type.split("\x00\x01")
        if len(parts) == 2 and parts[1] == "Model":
            subtype = str(node.properties[2]).strip("\x00\x01 ") \
                if len(node.properties) > 2 else ""
            model_kind[oid] = subtype

    # Geometry id -> model 名（OO 连接，child=Geometry, parent=Model）
    geo_to_model = {}
    for conn in connections:
        if conn[0] != "OO":
            continue
        child_id, parent_id = conn[1], conn[2]
        child = objects.get(child_id)
        if child is None or not child.properties:
            continue
        if str(child.properties[1]).split("\x00\x01")[-1:] != ["Geometry"]:
            continue
        parent = objects.get(parent_id)
        if parent is None or parent_id not in model_kind:
            continue
        parent_name = str(parent.properties[1]).split("\x00\x01")[0]
        geo_to_model[child_id] = parent_name

    result = {}
    for geo_id, model_name in geo_to_model.items():
        if model_name:
            result[model_name] = objects[geo_id]
    return result


def extract_geometry(geo):
    """提取 Geometry 的顶点/面/法线/UV，返回 dict（与 fbx_bin_export 输入对称）。

    必须保留各层的 MappingInformationType（ByVertice/ByPolygonVertex）——
    写回时声明与数组长度必须匹配，否则 Unity 法线解析错乱（如
    ByVertice 的 20 顶点份法线声明成 ByPolygonVertex，Unity 读 144 个却只有 60 个）。
    """
    out = {
        "vertices": list(child_value(geo, "Vertices", [])),
        "polygons": list(child_value(geo, "PolygonVertexIndex", [])),
        "normals": [],
        "normal_mapping": None,
        "uv": [],
        "uv_mapping": None,
        "uv_indices": None,
    }
    for layer in geo.children:
        if layer.name == "LayerElementNormal" and layer.properties:
            out["normals"] = list(child_value(layer, "Normals", []) or [])
            out["normal_mapping"] = child_value(layer, "MappingInformationType")
        elif layer.name == "LayerElementUV" and layer.properties:
            out["uv"] = list(child_value(layer, "UV", []) or [])
            out["uv_mapping"] = child_value(layer, "MappingInformationType")
            uv_index = child_value(layer, "UVIndex", None)
            out["uv_indices"] = list(uv_index) if uv_index is not None else None
    return out


def aabb_center(vertices):
    if not vertices:
        return (0.0, 0.0, 0.0)
    xs = vertices[0::3]
    ys = vertices[1::3]
    zs = vertices[2::3]
    return (
        (min(xs) + max(xs)) / 2.0,
        (min(ys) + max(ys)) / 2.0,
        (min(zs) + max(zs)) / 2.0,
    )


def center_vertices(vertices, center):
    """顶点整体平移，使 center 落在原点。"""
    for i in range(0, len(vertices), 3):
        vertices[i] = float(vertices[i]) - center[0]
        vertices[i + 1] = float(vertices[i + 1]) - center[1]
        vertices[i + 2] = float(vertices[i + 2]) - center[2]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main(argv):
    parser = argparse.ArgumentParser(description="从 FBX 拆出子网格并输出独立二进制 FBX")
    parser.add_argument("input", help="源 FBX 路径")
    parser.add_argument("--models", required=True, help="要拆出的 Model 名，逗号分隔")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--prefix", default="piece", help="输出文件前缀")
    parser.add_argument("--center", action="store_true", help="顶点平移到 AABB 中心为原点")
    args = parser.parse_args(argv)

    root = parse_binary(args.input)
    meshes = collect_mesh_geometry(root)
    model_names = [name.strip() for name in args.models.split(",") if name.strip()]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, name in enumerate(model_names):
        if name not in meshes:
            print(f"[SKIP] 未找到 Model: {name}")
            continue
        data = extract_geometry(meshes[name])
        if not data["vertices"]:
            print(f"[SKIP] {name} 无顶点数据")
            continue

        center = (0.0, 0.0, 0.0)
        if args.center:
            center = aabb_center(data["vertices"])
            center_vertices(data["vertices"], center)

        out_path = output_dir / f"{args.prefix}{index}.fbx"
        write_fbx_binary(out_path, name, data)
        print(f"[OK] {name} -> {out_path} (顶点 {len(data['vertices']) // 3}, "
              f"面 {sum(1 for p in data['polygons'] if p < 0)}, "
              f"中心 {center[0]:.6f},{center[1]:.6f},{center[2]:.6f})")


if __name__ == "__main__":
    main(sys.argv[1:])
