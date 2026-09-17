#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rasterize FBX UV shells to a PNG. Pillow is only required for --uv-export."""
from __future__ import annotations

import math
from pathlib import Path

from fbx_geom import iter_mesh_nodes, prop_array
from fbx_scene import collect_objects
from fbx_types import FbxNode, object_display_name
from fbx_uv import _face_uvs, _faces_from_pvi, _layer_uv, geometry_model_names


def iter_face_uvs(root: FbxNode) -> list[tuple[str, list[list[tuple[float, float]]]]]:
    """Return (model_name, per-face corner UVs) for every mesh with UV."""
    objs = collect_objects(root)
    model_of = geometry_model_names(root)
    out: list[tuple[str, list[list[tuple[float, float]]]]] = []
    for mesh in iter_mesh_nodes(root):
        pvi = next((prop_array(child) for child in mesh.children
                    if child.name == "PolygonVertexIndex"), None)
        layer = _layer_uv(mesh)
        if not pvi or layer is None:
            continue
        geo_id = next((oid for oid, node in objs.items() if node is mesh), None)
        name, mapping, ref, uvs, uv_index = layer
        face_uvs = _face_uvs(_faces_from_pvi(pvi), mapping, ref, uvs, uv_index)
        if not face_uvs:
            continue
        model = model_of.get(geo_id, object_display_name(mesh))
        out.append((model, face_uvs))
        del name
    return out


def _shift_face(corners: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Keep a face together and move it into the 0..1 tile."""
    du = math.floor(min(u for u, _v in corners))
    dv = math.floor(min(v for _u, v in corners))
    return [(u - du, v - dv) for u, v in corners]


def _to_px(uv: tuple[float, float], size: int) -> tuple[float, float]:
    u, v = uv
    return (u * size, (1.0 - v) * size)


def rasterize_uv_shells(root: FbxNode, size: int, out: Path, width: int = 2) -> int:
    """Draw white UV-shell outlines on a transparent PNG. Return face count."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise RuntimeError("--uv-export 需要 Pillow：pip install Pillow") from exc
    if size < 8:
        raise ValueError("--uv-size 太小")
    meshes = iter_face_uvs(root)
    if not meshes:
        raise ValueError("没有可栅格化的 UV 面")
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    faces = 0
    stroke = max(1, width)
    for _model, face_uvs in meshes:
        for corners in face_uvs:
            if len(corners) < 2:
                continue
            pts = [_to_px(uv, size) for uv in _shift_face(corners)]
            draw.line(pts + [pts[0]], fill=(255, 255, 255, 255), width=stroke)
            faces += 1
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, format="PNG")
    return faces
