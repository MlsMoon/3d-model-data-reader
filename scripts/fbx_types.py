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
    """FBX 名称常为 `Name\\x00\\x01Class` 双段；展示时只取 Name。"""
    if not isinstance(raw, str):
        return str(raw)
    if "\x00" in raw:
        return raw.split("\x00", 1)[0]
    return raw
