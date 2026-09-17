#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX UV 岛：从 LayerElementUV 还原每面角 UV，再按共享 UV 边合并岛。"""
from fbx_geom import iter_mesh_nodes, prop_array
from fbx_scene import build_connections, collect_objects, _obj_kind
from fbx_types import FbxNode, object_display_name


def _faces_from_pvi(pvi: list) -> list[list[int]]:
    faces, current = [], []
    for x in pvi:
        if x < 0:
            current.append(~x)
            faces.append(current)
            current = []
        else:
            current.append(x)
    return faces


def _uv_pairs(uv: list) -> list[tuple[float, float]]:
    return [(float(uv[i]), float(uv[i + 1])) for i in range(0, len(uv) - 1, 2)]


def _layer_uv(mesh: FbxNode) -> tuple[str, str, str, list, list | None] | None:
    """返回 (name, mapping, ref, uv_pairs, uv_index_or_None)。"""
    layer = next((c for c in mesh.children if c.name.startswith("LayerElementUV")), None)
    if layer is None:
        return None
    name = mapping = ref = ""
    raw_uv = raw_idx = None
    for c in layer.children:
        if c.name == "Name" and c.properties:
            name = str(c.properties[0])
        elif c.name == "MappingInformationType" and c.properties:
            mapping = str(c.properties[0])
        elif c.name == "ReferenceInformationType" and c.properties:
            ref = str(c.properties[0])
        elif c.name == "UV":
            raw_uv = prop_array(c)
        elif c.name == "UVIndex":
            raw_idx = prop_array(c)
    if not raw_uv:
        return None
    return name or "UV", mapping, ref, _uv_pairs(raw_uv), raw_idx


def _face_uvs(
    faces: list[list[int]],
    mapping: str,
    ref: str,
    uvs: list[tuple[float, float]],
    uv_index: list | None,
) -> list[list[tuple[float, float]]]:
    """每个面一组角 UV。不支持的 Mapping 返回空。"""
    if mapping == "ByPolygonVertex" and ref == "IndexToDirect" and uv_index:
        out, cursor = [], 0
        for face in faces:
            n = len(face)
            ids = [int(uv_index[cursor + i]) for i in range(n)]
            out.append([uvs[i] for i in ids if 0 <= i < len(uvs)])
            cursor += n
        return out
    if mapping == "ByPolygonVertex" and ref == "Direct":
        out, cursor = [], 0
        for face in faces:
            n = len(face)
            out.append(uvs[cursor: cursor + n])
            cursor += n
        return out
    if mapping == "ByVertice" and ref == "Direct":
        return [[uvs[v] for v in face if 0 <= v < len(uvs)] for face in faces]
    if mapping == "ByVertice" and ref == "IndexToDirect" and uv_index:
        return [
            [uvs[int(uv_index[v])] for v in face
             if 0 <= v < len(uv_index) and 0 <= int(uv_index[v]) < len(uvs)]
            for face in faces
        ]
    return []


def _uv_key(uv: tuple[float, float], eps: float = 1e-5) -> tuple[int, int]:
    return (round(uv[0] / eps), round(uv[1] / eps))


def _islands(face_uvs: list[list[tuple[float, float]]]) -> list[list[int]]:
    """共享一条 UV 边的面合成一岛。"""
    n = len(face_uvs)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    edge_faces: dict[tuple[tuple[int, int], tuple[int, int]], list[int]] = {}
    for fi, corners in enumerate(face_uvs):
        keys = [_uv_key(uv) for uv in corners]
        m = len(keys)
        for i in range(m):
            a, b = keys[i], keys[(i + 1) % m]
            if a == b:
                continue
            edge = (a, b) if a < b else (b, a)
            bucket = edge_faces.setdefault(edge, [])
            for other in bucket:
                union(fi, other)
            bucket.append(fi)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _aabb(face_uvs: list[list[tuple[float, float]]], face_ids: list[int]):
    pts = [uv for fi in face_ids for uv in face_uvs[fi]]
    if not pts:
        return None
    us = [p[0] for p in pts]
    vs = [p[1] for p in pts]
    return min(us), min(vs), max(us), max(vs)


def _texel_box(box: tuple[float, float, float, float], size: int) -> list[int]:
    u0, v0, u1, v1 = box
    # FBX v=0 在底，图像 y=0 在顶。
    x0 = int(max(0, min(size - 1, u0 * size)))
    x1 = int(max(0, min(size - 1, u1 * size)))
    y0 = int(max(0, min(size - 1, (1.0 - v1) * size)))
    y1 = int(max(0, min(size - 1, (1.0 - v0) * size)))
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    return [x0, y0, x1, y1]


def geometry_model_names(root: FbxNode) -> dict[object, str]:
    """OO/OP(Geometry -> Model) 用来给网格挂可读名。"""
    objs = collect_objects(root)
    names: dict[object, str] = {}
    for kind, child, parent, _ in build_connections(root):
        if kind not in ("OO", "OP") or child not in objs or parent not in objs:
            continue
        if _obj_kind(objs[child]) != "Geometry":
            continue
        if _obj_kind(objs[parent]) != "Model":
            continue
        names[child] = object_display_name(objs[parent])
    return names


def collect_uv_islands(root: FbxNode, texture_size: int | None = None) -> dict:
    """汇总每个网格的 UV 岛。texture_size 有值时附带 texel AABB。"""
    objs = collect_objects(root)
    model_of = geometry_model_names(root)
    meshes = []
    for mesh in iter_mesh_nodes(root):
        pvi = next((prop_array(c) for c in mesh.children
                    if c.name == "PolygonVertexIndex"), None)
        layer = _layer_uv(mesh)
        geo_id = next((oid for oid, node in objs.items() if node is mesh), None)
        model = model_of.get(geo_id, object_display_name(mesh))
        if not pvi:
            continue
        if layer is None:
            meshes.append({
                "geometry_id": geo_id,
                "model": model,
                "uv_set": "",
                "mapping": "",
                "reference": "",
                "uv_count": 0,
                "face_count": sum(1 for x in pvi if x < 0),
                "islands": [],
                "island_count": 0,
                "warning": "无 LayerElementUV",
            })
            continue
        name, mapping, ref, uvs, uv_index = layer
        faces = _faces_from_pvi(pvi)
        face_uvs = _face_uvs(faces, mapping, ref, uvs, uv_index)
        entry = {
            "geometry_id": geo_id,
            "model": model,
            "uv_set": name,
            "mapping": mapping,
            "reference": ref,
            "uv_count": len(uvs),
            "face_count": len(faces),
            "islands": [],
        }
        if not face_uvs:
            entry["warning"] = f"未支持的 UV 布局 {mapping}/{ref}"
            meshes.append(entry)
            continue
        islands = _islands(face_uvs)
        packed = []
        for ids in islands:
            box = _aabb(face_uvs, ids)
            if box is None:
                continue
            item = {
                "faces": len(ids),
                "u_min": box[0], "v_min": box[1],
                "u_max": box[2], "v_max": box[3],
            }
            if texture_size:
                item["texel"] = _texel_box(box, texture_size)
            packed.append(item)
        packed.sort(key=lambda x: (-x["faces"], x["u_min"], x["v_min"]))
        entry["islands"] = packed
        entry["island_count"] = len(packed)
        meshes.append(entry)
    return {"texture_size": texture_size, "meshes": meshes}


def print_uv_islands(data: dict) -> None:
    size = data.get("texture_size")
    meshes = data.get("meshes", [])
    if not meshes:
        print("没有网格，或都缺少可解析的 PolygonVertexIndex")
        return
    for mesh in meshes:
        print(f"网格: {mesh.get('model')}  id={mesh.get('geometry_id')}")
        print(f"  UV: {mesh.get('uv_set')}  {mesh.get('mapping')}/{mesh.get('reference')}"
              f"  uv={mesh.get('uv_count')}  面={mesh.get('face_count')}"
              f"  岛={mesh.get('island_count', 0)}")
        if mesh.get("warning"):
            print(f"  ! {mesh['warning']}")
        for i, island in enumerate(mesh.get("islands", [])[:40]):
            line = (f"  岛{i}: 面 {island['faces']}  "
                    f"UV ({island['u_min']:.4f},{island['v_min']:.4f})"
                    f"-({island['u_max']:.4f},{island['v_max']:.4f})")
            if size and island.get("texel"):
                x0, y0, x1, y1 = island["texel"]
                line += f"  texel [{x0},{y0}]-[{x1},{y1}]"
            print(line)
        extra = len(mesh.get("islands", [])) - 40
        if extra > 0:
            print(f"  ... 另有 {extra} 个岛")
