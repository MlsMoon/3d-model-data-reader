#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 语义层：对象 / 连接 / 几何 / 骨架（与 ASCII/二进制无关）。"""
from fbx_types import FbxNode, fbx_display_name

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


def _bone_hierarchy(root: FbxNode) -> tuple[
        dict[int, FbxNode], dict[int, int], dict[int, list[int]], dict[int, bool]]:
    """Model-only 骨骼父子图。OO(Bone→Deformer) 不参与层级。"""
    objs = collect_objects(root)
    parent_of: dict[int, int] = {}
    children_of: dict[int, list[int]] = {}
    for kind, child, parent, _ in build_connections(root):
        if kind != "OO" or child not in objs or parent not in objs:
            continue
        if objs[child].name != "Model" or objs[parent].name != "Model":
            continue
        parent_of[child] = parent
        children_of.setdefault(parent, []).append(child)

    bone_tokens = {"Skeleton", "LimbNode", "Root", "RootNode"}

    def _attr_is_bone(node: FbxNode) -> bool:
        for c in node.children:
            if c.name in ("AttributeType", "TypeFlags", "Type") and c.properties:
                val = c.properties[0]
                if isinstance(val, str) and val in bone_tokens:
                    return True
        return any(isinstance(p, str) and p in bone_tokens for p in node.properties)

    attr_bone_ids = {
        oid for oid, node in objs.items()
        if node.name == "NodeAttribute" and _attr_is_bone(node)
    }
    model_linked_bone_attr: set[int] = set()
    for kind, child, parent, _ in build_connections(root):
        if kind != "OO":
            continue
        if child in attr_bone_ids and parent in objs and objs[parent].name == "Model":
            model_linked_bone_attr.add(parent)
        if parent in attr_bone_ids and child in objs and objs[child].name == "Model":
            model_linked_bone_attr.add(child)

    is_bone: dict[int, bool] = {}
    for oid, node in objs.items():
        if node.name != "Model":
            is_bone[oid] = False
            continue
        by_prop = any(isinstance(prop, str) and prop in bone_tokens for prop in node.properties)
        is_bone[oid] = by_prop or oid in model_linked_bone_attr
    return objs, parent_of, children_of, is_bone


def _bone_roots(parent_of: dict[int, int], is_bone: dict[int, bool]) -> list[int]:
    return [
        oid for oid, bone in is_bone.items()
        if bone and (oid not in parent_of or not is_bone.get(parent_of.get(oid)))
    ]


def skeleton_chains(root: FbxNode) -> list[list[FbxNode]]:
    """每条根骨骼沿第一子节点向下的链（摘要用）。完整树请看 print_skeleton_tree。"""
    objs, parent_of, children_of, is_bone = _bone_hierarchy(root)
    chains: list[list[FbxNode]] = []
    for oid in _bone_roots(parent_of, is_bone):
        chain = []
        cur = oid
        while cur in objs and is_bone.get(cur):
            chain.append(objs[cur])
            nexts = [c for c in children_of.get(cur, []) if is_bone.get(c)]
            cur = nexts[0] if nexts else -1
        if len(chain) > 1:
            chains.append(chain)
    return chains


def print_skeleton_tree(root: FbxNode) -> int:
    """打印骨骼森林。返回骨骼节点数。"""
    objs, parent_of, children_of, is_bone = _bone_hierarchy(root)
    roots = _bone_roots(parent_of, is_bone)
    bone_count = sum(1 for v in is_bone.values() if v)
    if bone_count == 0:
        model_types: dict[str, int] = {}
        for n in objs.values():
            if n.name == "Model" and len(n.properties) >= 3 and isinstance(n.properties[2], str):
                model_types[n.properties[2]] = model_types.get(n.properties[2], 0) + 1
        print("未找到骨架（Model 中无 LimbNode/Skeleton/Root）。")
        if model_types:
            print("Model 类型统计: " + ", ".join(f"{k}×{v}" for k, v in sorted(model_types.items())))
        return 0

    def _name(oid: int) -> str:
        n = objs[oid]
        return fbx_display_name(n.properties[1] if len(n.properties) > 1 else n.name)

    def _walk(oid: int, depth: int, seen: set[int]) -> None:
        if oid in seen:
            return
        seen.add(oid)
        print("  " * depth + _name(oid))
        for child in children_of.get(oid, []):
            if is_bone.get(child):
                _walk(child, depth + 1, seen)

    print(f"骨骼: {bone_count}  根: {len(roots)}")
    seen: set[int] = set()
    for rid in roots:
        _walk(rid, 0, seen)
    return bone_count


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
