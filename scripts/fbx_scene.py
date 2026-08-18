#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 语义层：对象 / 连接 / 骨架（与 ASCII/二进制无关）。"""
from fbx_geom import geometry_stats
from fbx_types import FbxNode, object_display_name

ObjKey = int | str

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
    ASCII 7.x 节点（Model:/Geometry: 等）ID 是第一个属性。"""
    if node.name == "O":
        for prop in reversed(node.properties):
            if isinstance(prop, int):
                return prop
        return None
    for prop in node.properties:
        if isinstance(prop, int):
            return prop
    return None


def _obj_key(node: FbxNode) -> ObjKey | None:
    """7.x 用整数 ID；FBX 6.1 无 ID，用第一段字符串（如 Model::DummyMesh）。"""
    oid = _obj_id(node)
    if oid is not None:
        return oid
    if node.properties and isinstance(node.properties[0], str):
        return node.properties[0]
    return None


def collect_objects(root: FbxNode) -> dict[ObjKey, FbxNode]:
    """Objects 分区下的对象按 ID 或 6.1 名称索引。"""
    objs: dict[ObjKey, FbxNode] = {}
    objects = _objects_node(root)
    if objects is None:
        return objs
    for child in objects.children:
        key = _obj_key(child)
        if key is not None:
            objs[key] = child
    return objs


def build_connections(root: FbxNode) -> list[tuple[str, ObjKey, ObjKey, str]]:
    """Connections：7.x 的 C + 整数端点；6.1 的 Connect + 名称端点。"""
    conns: list[tuple[str, ObjKey, ObjKey, str]] = []
    for c in root.children:
        if c.name != "Connections":
            continue
        for cc in c.children:
            if cc.name not in ("C", "Connect") or len(cc.properties) < 3:
                continue
            kind = cc.properties[0]
            child, parent = cc.properties[1], cc.properties[2]
            prop = cc.properties[3] if len(cc.properties) > 3 and \
                isinstance(cc.properties[3], str) else ""
            conns.append((kind, child, parent, prop))
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


def _bone_hierarchy(root: FbxNode) -> tuple[
        dict[ObjKey, FbxNode], dict[ObjKey, ObjKey],
        dict[ObjKey, list[ObjKey]], dict[ObjKey, bool]]:
    """Model-only 骨骼父子图。OO(Bone→Deformer) 不参与层级。"""
    objs = collect_objects(root)
    parent_of: dict[ObjKey, ObjKey] = {}
    children_of: dict[ObjKey, list[ObjKey]] = {}
    for kind, child, parent, _ in build_connections(root):
        if kind != "OO" or child not in objs or parent not in objs:
            continue
        if _obj_kind(objs[child]) != "Model" or _obj_kind(objs[parent]) != "Model":
            continue
        parent_of[child] = parent
        children_of.setdefault(parent, []).append(child)

    bone_tokens = {"Skeleton", "LimbNode", "Limb", "Root", "RootNode"}

    def _attr_is_bone(node: FbxNode) -> bool:
        for c in node.children:
            if c.name in ("AttributeType", "TypeFlags", "Type") and c.properties:
                val = c.properties[0]
                if isinstance(val, str) and val in bone_tokens:
                    return True
        return any(isinstance(p, str) and p in bone_tokens for p in node.properties)

    attr_bone_ids = {
        oid for oid, node in objs.items()
        if _obj_kind(node) == "NodeAttribute" and _attr_is_bone(node)
    }
    model_linked_bone_attr: set[ObjKey] = set()
    for kind, child, parent, _ in build_connections(root):
        if kind != "OO":
            continue
        if child in attr_bone_ids and parent in objs and _obj_kind(objs[parent]) == "Model":
            model_linked_bone_attr.add(parent)
        if parent in attr_bone_ids and child in objs and _obj_kind(objs[child]) == "Model":
            model_linked_bone_attr.add(child)

    is_bone: dict[ObjKey, bool] = {}
    for oid, node in objs.items():
        if _obj_kind(node) != "Model":
            is_bone[oid] = False
            continue
        is_bone[oid] = _attr_is_bone(node) or oid in model_linked_bone_attr
    return objs, parent_of, children_of, is_bone


def _bone_roots(parent_of: dict[ObjKey, ObjKey], is_bone: dict[ObjKey, bool]) -> list[ObjKey]:
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
            if _obj_kind(n) != "Model":
                continue
            strs = [p for p in n.properties if isinstance(p, str)]
            subtype = strs[-1] if strs else "?"
            model_types[subtype] = model_types.get(subtype, 0) + 1
        print("未找到骨架（Model 中无 LimbNode/Limb/Skeleton/Root）。")
        if model_types:
            print("Model 类型统计: " + ", ".join(f"{k}×{v}" for k, v in sorted(model_types.items())))
        return 0

    def _name(oid: ObjKey) -> str:
        return object_display_name(objs[oid])

    def _walk(oid: ObjKey, depth: int, seen: set) -> None:
        if oid in seen:
            return
        seen.add(oid)
        print("  " * depth + _name(oid))
        for child in children_of.get(oid, []):
            if is_bone.get(child):
                _walk(child, depth + 1, seen)

    print(f"骨骼: {bone_count}  根: {len(roots)}")
    seen: set = set()
    for rid in roots:
        _walk(rid, 0, seen)
    return bone_count


def header_version(root: FbxNode) -> int | None:
    for c in root.children:
        if c.name != "FBXHeaderExtension":
            continue
        for cc in c.children:
            if cc.name == "FBXVersion" and cc.properties:
                try:
                    return int(cc.properties[0])
                except (TypeError, ValueError):
                    return None
    return None


def global_settings(root: FbxNode) -> dict:
    """GlobalSettings 单位与轴。7.x 用 Properties70/P；6.1 用 Properties60/Property。"""
    out: dict = {}
    nodes: list[FbxNode] = []
    _find_all(root, "GlobalSettings", nodes)
    keys = ("UnitScaleFactor", "UpAxis", "UpAxisSign", "FrontAxis")
    for node in nodes:
        for p in node.children:
            if p.name not in ("Properties70", "Properties60"):
                continue
            for entry in p.children:
                if entry.name not in ("P", "Property") or not entry.properties:
                    continue
                key = entry.properties[0]
                if key not in keys:
                    continue
                vals = [x for x in entry.properties[1:] if isinstance(x, (int, float))]
                if vals:
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
    return {
        "objects": kinds,
        **geo,
        "settings": global_settings(root),
        "fbx_version": header_version(root),
    }
