#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基于 Blender 开源 FBX 导出核心（encode_bin.py）的二进制 FBX 导出模块。

结构完全对照 Blender io_scene_fbx/export_fbx_bin.py：
  FBXHeaderExtension（含必须的 SceneInfo）/ FileId / CreationTime / Creator /
  GlobalSettings / Documents / References / Definitions / Objects / Connections / Takes
Geometry 通过 OO 连接挂 Model。写入由 encode_bin.write 完成（25B 头、子节点哨兵、
文件 footer 均已正确处理）。

用法：build_fbx_elem(mesh_name, data) -> FBXElem 根，然后
      encode_bin.write(path, root, 7700)。
data 结构：{vertices, polygons, normals, uv, uv_indices}（与 fbx_reader 输出对称）。
"""
from encode_bin import FBXElem, write as write_fbx

FBX_VERSION = 7700


# ---------------------------------------------------------------------------
# Blender fbx_utils 风格的 elem helper（纯 BElement 操作）
# ---------------------------------------------------------------------------

def elem_empty(parent, name):
    elem = FBXElem(name)
    parent.elems.append(elem)
    return elem


def elem_data_single_int32(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_int32(value)
    return elem


def elem_data_single_int64(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_int64(value)
    return elem


def elem_data_single_float64(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_float64(value)
    return elem


def elem_data_single_string(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_string(value)
    return elem


def elem_data_single_string_unicode(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_string_unicode(value)
    return elem


def elem_data_single_bytes(parent, name, value):
    elem = elem_empty(parent, name)
    elem.add_bytes(value)
    return elem


def elem_data_single_int32_array(parent, name, values):
    elem = elem_empty(parent, name)
    elem.add_int32_array(values)
    return elem


def elem_data_single_float64_array(parent, name, values):
    elem = elem_empty(parent, name)
    elem.add_float64_array(values)
    return elem


def elem_properties(parent):
    return elem_empty(parent, b"Properties70")


def elem_props_set(props, ptype, name, value=None):
    """P 行：name(S) + type(S) + label(S) + flags(S) + value。

    ptype 长度 2（如 Compound/object）表示无值属性。
    """
    p = elem_empty(props, b"P")
    p.add_string(name)
    p.add_string(ptype[0])
    p.add_string(ptype[1])
    p.add_string(b"")
    if len(ptype) == 2:
        return
    if len(ptype) == 3:
        if ptype[2] == "int32":
            p.add_int32(value)
        elif ptype[2] == "int64":
            p.add_int64(value)
        elif ptype[2] == "float64":
            p.add_float64(value)
        elif ptype[2] == "string":
            p.add_string_unicode(value)
    elif len(ptype) > 3:
        for i, sub in enumerate(value):
            if ptype[2 + i] == "float64":
                p.add_float64(sub)


def fbx_name_class(name, cls):
    return name + b"\x00\x01" + cls


# ---------------------------------------------------------------------------
# 顶层段构造（对照 Blender export_fbx_bin.py）
# ---------------------------------------------------------------------------

def build_header_ext(root):
    header_ext = elem_empty(root, b"FBXHeaderExtension")
    elem_data_single_int32(header_ext, b"FBXHeaderVersion", 1004)
    elem_data_single_int32(header_ext, b"FBXVersion", FBX_VERSION)
    elem_data_single_int32(header_ext, b"EncryptionType", 0)

    ts = elem_empty(header_ext, b"CreationTimeStamp")
    elem_data_single_int32(ts, b"Version", 1000)
    elem_data_single_int32(ts, b"Year", 2026)
    elem_data_single_int32(ts, b"Month", 8)
    elem_data_single_int32(ts, b"Day", 3)
    elem_data_single_int32(ts, b"Hour", 12)
    elem_data_single_int32(ts, b"Minute", 0)
    elem_data_single_int32(ts, b"Second", 0)
    elem_data_single_int32(ts, b"Millisecond", 0)

    elem_data_single_string_unicode(
        header_ext, b"Creator", "FBX SDK/FBX Plugins version 2020.3"
    )

    # SceneInfo 对合法 FBX 是必须的
    scene_info = elem_data_single_string(
        header_ext, b"SceneInfo", fbx_name_class(b"GlobalInfo", b"SceneInfo")
    )
    scene_info.add_string(b"UserData")
    elem_data_single_string(scene_info, b"Type", b"UserData")
    elem_data_single_int32(scene_info, b"Version", 100)
    meta = elem_empty(scene_info, b"MetaData")
    elem_data_single_int32(meta, b"Version", 100)
    elem_data_single_string(meta, b"Title", b"")
    elem_data_single_string(meta, b"Subject", b"")
    elem_data_single_string(meta, b"Author", b"")
    elem_data_single_string(meta, b"Keywords", b"")
    elem_data_single_string(meta, b"Revision", b"")
    elem_data_single_string(meta, b"Comment", b"")
    props = elem_properties(scene_info)
    elem_props_set(props, (b"KString", b"Url", "string"), b"DocumentUrl", "")
    elem_props_set(props, (b"KString", b"Url", "string"), b"SrcDocumentUrl", "")
    elem_props_set(props, (b"Compound", b""), b"Original")
    elem_props_set(props, (b"KString", b"", "string"), b"Original|ApplicationVendor", "Blender")
    elem_props_set(props, (b"KString", b"", "string"), b"Original|ApplicationName", "Blender")
    elem_props_set(props, (b"KString", b"", "string"), b"Original|ApplicationVersion", "3.0")
    elem_props_set(props, (b"KString", b"", "string"), b"Original|DateTime_GMT", "01/01/1970 00:00:00.000")
    elem_props_set(props, (b"KString", b"", "string"), b"Original|FileName", "/foobar.fbx")
    return header_ext


def build_global_settings(root):
    settings = elem_empty(root, b"GlobalSettings")
    elem_data_single_int32(settings, b"Version", 1000)
    props = elem_properties(settings)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"UpAxis", 1)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"UpAxisSign", 1)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"FrontAxis", 2)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"FrontAxisSign", 1)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"CoordAxis", 0)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"CoordAxisSign", 1)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"OriginalUpAxis", -1)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"OriginalUpAxisSign", 1)
    elem_props_set(props, (b"double", b"Number", "float64"), b"UnitScaleFactor", 1.0)
    elem_props_set(props, (b"double", b"Number", "float64"), b"OriginalUnitScaleFactor", 1.0)
    elem_props_set(props, (b"ColorRGB", b"Color", "float64", "float64", "float64"),
                   b"AmbientColor", (0.0, 0.0, 0.0))
    elem_props_set(props, (b"KString", b"", "string"), b"DefaultCamera", "Producer Perspective")
    elem_props_set(props, (b"enum", b"", "int32"), b"TimeMode", 5)
    elem_props_set(props, (b"KTime", b"Time", "int64"), b"TimeSpanStart", 0)
    elem_props_set(props, (b"KTime", b"Time", "int64"), b"TimeSpanStop", 46186158000)
    elem_props_set(props, (b"double", b"Number", "float64"), b"CustomFrameRate", 24.0)
    return settings


def build_documents(root):
    docs = elem_empty(root, b"Documents")
    elem_data_single_int32(docs, b"Count", 1)
    doc = elem_data_single_int64(docs, b"Document", 196611)
    doc.add_string_unicode("Scene")
    doc.add_string_unicode("Scene")
    props = elem_properties(doc)
    elem_props_set(props, (b"object", b""), b"SourceObject")
    elem_props_set(props, (b"KString", b"", "string"), b"ActiveAnimStackName", "")
    elem_data_single_int64(doc, b"RootNode", 0)
    elem_empty(root, b"References")
    return docs


def build_definitions(root):
    defs = elem_empty(root, b"Definitions")
    elem_data_single_int32(defs, b"Version", 100)
    elem_data_single_int32(defs, b"Count", 4)
    for obj_type, count in ((b"GlobalSettings", 1), (b"Model", 2),
                            (b"Geometry", 1), (b"Material", 1)):
        t = elem_empty(defs, b"ObjectType")
        t.add_string(obj_type)
        elem_data_single_int32(t, b"Count", count)
    return defs


def build_takes(root):
    takes = elem_empty(root, b"Takes")
    elem_data_single_string(takes, b"Current", b"")
    return takes
# ---------------------------------------------------------------------------
# Objects / Connections 构造
# ---------------------------------------------------------------------------

def build_model(parent, model_id, model_name, subtype):
    """Model：属性 [id(L), name+类型(S), 子类型(S)]，子节点 Version/Properties70/Shading/Culling。"""
    model = elem_empty(parent, b"Model")
    model.add_int64(model_id)
    model.add_string(model_name + b"\x00\x01Model")
    model.add_string(subtype)
    elem_data_single_int32(model, b"Version", 232)
    props = elem_properties(model)
    elem_props_set(props, (b"int", b"Integer", "int32"), b"DefaultAttributeIndex", 0)
    elem_props_set(props, (b"Lcl Translation", b"", "float64", "float64", "float64"),
                   b"Lcl Translation", (0.0, 0.0, 0.0))
    elem_props_set(props, (b"Lcl Rotation", b"", "float64", "float64", "float64"),
                   b"Lcl Rotation", (0.0, 0.0, 0.0))
    elem_props_set(props, (b"Lcl Scaling", b"", "float64", "float64", "float64"),
                   b"Lcl Scaling", (1.0, 1.0, 1.0))
    elem_data_single_string(model, b"Shading", b"T")
    elem_data_single_string(model, b"Culling", b"CullingOff")
    return model


def build_geometry(parent, geo_id, mesh_name, data):
    geo = elem_empty(parent, b"Geometry")
    geo.add_int64(geo_id)
    geo.add_string(b"\x00\x01Geometry")
    geo.add_string(b"Mesh")
    elem_data_single_float64_array(geo, b"Vertices", data["vertices"])
    elem_data_single_int32_array(geo, b"PolygonVertexIndex", data["polygons"])
    elem_data_single_int32(geo, b"GeometryVersion", 124)

    if data.get("normals"):
        normal = elem_empty(geo, b"LayerElementNormal")
        normal.add_int32(0)
        elem_data_single_int32(normal, b"Version", 102)
        elem_data_single_string(normal, b"Name", b"")
        # MappingInformationType 必须与源一致（ByVertice 时数组=顶点数份；
        # 硬编码 ByPolygonVertex 而数据是顶点数份会导致 Unity 法线解析错乱）
        normal_mapping = data.get("normal_mapping") or "ByPolygonVertex"
        elem_data_single_string(
            normal, b"MappingInformationType", normal_mapping.encode("utf-8")
        )
        elem_data_single_string(normal, b"ReferenceInformationType", b"Direct")
        elem_data_single_float64_array(normal, b"Normals", data["normals"])

    if data.get("uv"):
        uv = elem_empty(geo, b"LayerElementUV")
        uv.add_int32(0)
        elem_data_single_int32(uv, b"Version", 101)
        elem_data_single_string(uv, b"Name", b"map1")
        elem_data_single_string(uv, b"MappingInformationType", b"ByPolygonVertex")
        if data.get("uv_indices"):
            elem_data_single_string(uv, b"ReferenceInformationType", b"IndexToDirect")
            elem_data_single_float64_array(uv, b"UV", data["uv"])
            elem_data_single_int32_array(uv, b"UVIndex", data["uv_indices"])
        else:
            elem_data_single_string(uv, b"ReferenceInformationType", b"Direct")
            elem_data_single_float64_array(uv, b"UV", data["uv"])

    mat = elem_empty(geo, b"LayerElementMaterial")
    mat.add_int32(0)
    elem_data_single_int32(mat, b"Version", 101)
    elem_data_single_string(mat, b"Name", b"")
    elem_data_single_string(mat, b"MappingInformationType", b"AllSame")
    elem_data_single_string(mat, b"ReferenceInformationType", b"IndexToDirect")
    elem_data_single_int32_array(mat, b"Materials", [0])

    layer = elem_empty(geo, b"Layer")
    layer.add_int32(0)
    elem_data_single_int32(layer, b"Version", 100)
    for index, ltype in ((0, b"LayerElementNormal"), (1, b"LayerElementMaterial"),
                         (2, b"LayerElementUV")):
        le = elem_empty(layer, b"LayerElement")
        le.add_int32(index)
        elem_data_single_string(le, b"Type", ltype)
        elem_data_single_int32(le, b"TypedIndex", 0)
    return geo


def build_material(parent, mat_id):
    mat = elem_empty(parent, b"Material")
    mat.add_int64(mat_id)
    mat.add_string(b"lambert1\x00\x01Material")
    mat.add_string(b"")
    elem_data_single_int32(mat, b"Version", 102)
    elem_data_single_string(mat, b"ShadingModel", b"phong")
    elem_data_single_int32(mat, b"MultiLayer", 0)
    props = elem_properties(mat)
    elem_props_set(props, (b"KString", b"", "string"), b"ShadingModel", "phong")
    elem_props_set(props, (b"int", b"Integer", "int32"), b"MultiLayer", 0)
    return mat


def build_objects(parent, mesh_name, data):
    objects = elem_empty(parent, b"Objects")
    build_model(objects, 101, b"RootNode", b"Null")
    build_model(objects, 102, mesh_name.encode("utf-8"), b"Mesh")
    build_geometry(objects, 201, mesh_name, data)
    build_material(objects, 301)
    return objects


def build_connections(parent):
    conns = elem_empty(parent, b"Connections")
    for kind, child, par in ((b"OO", 101, 0), (b"OO", 102, 101),
                             (b"OO", 201, 102), (b"OO", 301, 102)):
        c = elem_empty(conns, b"C")
        c.add_string(kind)
        c.add_int64(child)
        c.add_int64(par)
    return conns


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def build_fbx_root(mesh_name, data):
    """构造完整 FBX 根元素（FBXElem）。"""
    root = FBXElem(b"")
    build_header_ext(root)
    # FileId/CreationTime 占位，encode_bin.write 内部 _write_timedate_hack 会替换为固定值
    elem_data_single_bytes(root, b"FileId", b"FooBar")
    elem_data_single_string_unicode(root, b"CreationTime", "1970-01-01 10:00:00:000")
    elem_data_single_string_unicode(root, b"Creator", "Blender (stable FBX IO)")
    build_global_settings(root)
    build_documents(root)
    build_definitions(root)
    build_objects(root, mesh_name, data)
    build_connections(root)
    build_takes(root)
    return root


def write_fbx_binary(path, mesh_name, data, version=FBX_VERSION):
    """输出二进制 FBX（Blender encode_bin 实现，100% 兼容 FBX SDK）。"""
    root = build_fbx_root(mesh_name, data)
    write_fbx(path, root, version)
