#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FBX 节点类型与公共常量。"""
from dataclasses import dataclass, field

FBX_MAGIC = b"Kaydara FBX Binary  \x00\x1a\x00"


@dataclass
class FbxNode:
    """FBX 节点（record）。name 为节点名，properties 为已解码属性列表。"""
    name: str
    properties: list = field(default_factory=list)
    children: list["FbxNode"] = field(default_factory=list)

def fbx_display_name(raw: object) -> str:
    """FBX 名称常为 `Name\\x00\\x01Class`；切掉 Class 后再剥残留 `\\x01`。"""
    if not isinstance(raw, str):
        return str(raw)
    if "\x00" in raw:
        raw = raw.split("\x00", 1)[0]
    return raw.lstrip("\x01")


def object_display_name(node: FbxNode) -> str:
    """对象可读名：二进制 `Name\\x00\\x01Class`；ASCII 7.x 为第二参数；6.1 为 `Class::Name`。"""
    props = node.properties
    if node.name == "O":
        return fbx_display_name(props[1] if len(props) > 1 else node.name)
    if props and isinstance(props[0], int) and len(props) > 1:
        raw = fbx_display_name(props[1])
        return raw.split("::", 1)[-1]
    if props and isinstance(props[0], str):
        raw = fbx_display_name(props[0])
        return raw.split("::", 1)[-1]
    return node.name
