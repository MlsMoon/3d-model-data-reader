#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 几何：数组展平、网格节点、LayerElement 摘要。"""
from fbx_types import FbxNode, object_display_name


def prop_array(node: FbxNode) -> list | None:
    """取节点上的数值数组。兼容 *N { a: ... } 单数组属性，以及 6.1 折行多属性。"""
    if not node.properties:
        return None
    first = node.properties[0]
    if isinstance(first, list):
        return first
    if all(isinstance(x, (int, float)) for x in node.properties):
        return list(node.properties)
    return None


def _has_mesh_data(node: FbxNode) -> bool:
    return any(c.name == "Vertices" for c in node.children)


def iter_mesh_nodes(root: FbxNode) -> list[FbxNode]:
    """独立 Geometry，或 FBX 6.1 把网格写在 Mesh Model 上。"""
    found: list[FbxNode] = []

    def walk(node: FbxNode) -> None:
        kind = node.name if node.name != "O" else (
            str(node.properties[0]) if node.properties else "?"
        )
        if kind == "Geometry" or (kind == "Model" and _has_mesh_data(node)):
            if _has_mesh_data(node):
                found.append(node)
        for c in node.children:
            walk(c)

    walk(root)
    return found


def geometry_stats(root: FbxNode) -> dict:
    """汇总网格顶点/面统计与整体包围盒。"""
    geoms = iter_mesh_nodes(root)
    total_verts, total_faces = 0, 0
    bounds: list[tuple] = []
    for g in geoms:
        verts = None
        pvi = None
        for c in g.children:
            if c.name == "Vertices":
                verts = prop_array(c)
            elif c.name == "PolygonVertexIndex":
                pvi = prop_array(c)
        if verts:
            total_verts += len(verts) // 3
            for i in range(0, len(verts) - 2, 3):
                bounds.append(tuple(verts[i: i + 3]))
        if pvi:
            total_faces += sum(1 for x in pvi if x < 0)
    bmin = bmax = None
    if bounds:
        bmin = tuple(min(b[i] for b in bounds) for i in range(3))
        bmax = tuple(max(b[i] for b in bounds) for i in range(3))
    return {"geometry_count": len(geoms), "vertices": total_verts,
            "faces": total_faces, "bounds_min": bmin, "bounds_max": bmax}


_LAYER_META = {
    "MappingInformationType", "ReferenceInformationType", "Version", "Name",
}


def describe_layer(node: FbxNode) -> str:
    """LayerElement* 摘要：子节点数组长度 + Mapping/Reference，而不是 version 属性。"""
    mapping = ref = ""
    parts: list[str] = []
    for c in node.children:
        if c.name == "MappingInformationType" and c.properties:
            mapping = str(c.properties[0])
        elif c.name == "ReferenceInformationType" and c.properties:
            ref = str(c.properties[0])
        elif c.name in _LAYER_META:
            continue
        else:
            arr = prop_array(c)
            if arr is not None:
                parts.append(f"{c.name} len={len(arr)}")
    extra = ", ".join(parts) or (
        f"idx={node.properties[0]}" if node.properties else ""
    )
    bits = [node.name + (f": {extra}" if extra else "")]
    if mapping:
        bits.append(f"map={mapping}")
    if ref:
        bits.append(f"ref={ref}")
    return " ".join(bits)


def print_geometry(node: FbxNode, key: object) -> None:
    print(f"对象 {key}: {object_display_name(node)}")
    for c in node.children:
        if c.name in ("Vertices", "PolygonVertexIndex"):
            arr = prop_array(c)
            if arr is None:
                continue
            extra = f", 顶点 {len(arr) // 3}" if c.name == "Vertices" else (
                f", 面 {sum(1 for x in arr if x < 0)}"
            )
            print(f"  {c.name}: 数组 len={len(arr)}{extra}")
        elif c.name.startswith("LayerElement"):
            print(f"  {describe_layer(c)}")


def find_object(objs: dict, key: str):
    """按 ID、完整名或短名查找对象。"""
    if key in objs:
        return key, objs[key]
    try:
        ik = int(key)
    except ValueError:
        ik = None
    if ik is not None and ik in objs:
        return ik, objs[ik]
    aliases = {key, f"Model::{key}", f"Geometry::{key}"}
    for oid, node in objs.items():
        names = {str(oid), object_display_name(node)}
        if node.properties and isinstance(node.properties[0], str):
            names.add(node.properties[0])
        if names & aliases or key in names:
            return oid, node
    return None, None
