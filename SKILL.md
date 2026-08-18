---
name: 3d-model-data-reader
description: >
  Read and inspect OBJ/FBX mesh data (vertices, normals, UVs, faces,
  node tree, transforms, skeleton). Parse OBJ, FBX ASCII, and FBX
  binary (incl. 25-byte record header / zlib arrays) with stdlib-only
  Python; write Unity-importable binary FBX via Blender encode_bin.
  Use when inspecting 3D model internals, extracting geometry stats,
  splitting submeshes, or debugging FBX import without a DCC.
  适用于读取 OBJ/FBX 顶点与层级、核对网格/骨架、拆子网格、排查 Unity 导入。
license: GPL-2.0-or-later
compatibility: Requires Python 3.9+. FBX write path requires numpy.
metadata:
  author: MlsMoon
  version: "1.1"
---

# 3D 模型数据读取（OBJ / FBX）

> 通用 Agent Skill：读取 FBX/OBJ 的顶点数据与层级结构，并附带零依赖
> Python 脚本。不绑定任何游戏项目。

## 1. 概述与使用流程

| 需求 | 手段 | 输出 |
|------|------|------|
| 小文件、只看结构 | 直接读文件 + 本 skill 的格式速查 | 人工对照 |
| 大文件、要统计/提取 | `scripts/obj_reader.py` / `scripts/fbx_reader.py` | 人类可读摘要（默认）或 `--json` |
| 深度几何（UV 展开/网格运算） | `references/trimesh-fallback.md` | trimesh 对象 |

**脚本统一约定**：`--summary` 摘要（默认）、`--json` 结构化输出（stdout、UTF-8）、失败退出码非 0 且 stderr 给原因、大文件默认只出统计。
**长度**：单个 `.py` 控制在约 250 行内；再长按职责拆文件。`fbx_reader.py` 只做 CLI / re-export，实现见 `fbx_types.py`、`fbx_binary.py`、`fbx_ascii.py`、`fbx_scene.py`。

## 2. OBJ 格式速查

一行一条语句，`#` 注释。无单位/轴约定。索引 **1-based**，**负数 = 从尾部数**（`-1` = 最后一条）。

| 语句 | 参数 | 说明 |
|------|------|------|
| `v` | `x y z` | 顶点坐标 |
| `vt` | `u v` | 纹理坐标 |
| `vn` | `x y z` | 法线 |
| `f` | 索引列表 | 面；元素为 `v` / `v/vt` / `v//vn` / `v/vt/vn` |
| `o` / `g` | 名称 | 对象 / 组标记（无变换含义） |
| `usemtl` / `mtllib` / `s` | 名称 / 文件 / `1`or`off` | 材质切换 / 材质库 / 平滑组 |

**面索引转 0-based**：`resolve = idx - 1 if idx > 0 else count + idx`（越界丢弃该面并记 warning）。n-gon（>3 顶点）渲染前需三角化（扇形）。

## 3. FBX 结构速查

- **判别格式**：文件头 23 字节 = `Kaydara FBX Binary  \x00\x1a\x00` → 二进制；否则看文本是否含 `FBXHeaderExtension`/`FBXVersion` 关键字 → ASCII；都不是 → 非 FBX。
- **版本号**：二进制文件字节 23-26（little-endian uint32），如 7400 = FBX 7.4、7700 = FBX 7.7。
- **record 头**：`<7500` 为 13 字节，`>=7500` 为 25 字节；`end_offset` **一律是文件绝对偏移**（不是相对）。Unity 工程里大量第三方 FBX 仍是 7400。
- **FBXHeaderVersion**：7.4 常见 1003，7.7 常见 1004。锚点必须同时接受二者。
- **两大集合**：`Objects`（对象定义，按 **ID 关联**）+ `Connections`（`C` 节点，四种连接 OO/OP/PO/PP）。
- **节点树**：record 递归嵌套；容器节点（有子节点）与叶子节点（只有属性）不区分语法，`name: 属性...` 结构统一。
- **二进制 record 头（⚠️ 实测 7.7）**：25 字节 = `end(4, 下一 record 绝对偏移) + rsvd(4) + num(4) + rsvd(4) + plen(4) + rsvd(4) + nlen(1)`；旧版本可能 13/17 字节头，`fbx_reader.py` 自动探测。详见 `references/fbx-binary-format.md`。

## 4. 顶点数据读取

### OBJ

```python
# 面元素 (v, vt, vn) 三元组 -> 顶点缓冲重映射（去重）
for face in obj.faces:
    corners = list(zip(face.vertex_indices, face.uv_indices or [], face.normal_indices or []))
    for v, vt, vn in corners:
        key = (v, vt, vn)
        if key not in remap:
            remap[key] = len(positions)
            positions.append(obj.vertices[v])
        index_buffer.append(remap[key])
```

> UV/法线缺失时（`f v`、`f v//vn`）三列表长度不一致，消费方需处理。

### FBX Geometry

- `Vertices`：double 数组，每 3 个 = 1 顶点。
- `PolygonVertexIndex`：int32 数组，**负值 = 面最后一个顶点，按 `~x` 还原**：

```python
faces, current = [], []
for x in pvi:
    if x < 0:
        current.append(~x)     # ~(-1) = 0, ~(-4) = 3
        faces.append(current)
        current = []
    else:
        current.append(x)
```

- 法线/UV 在 `LayerElementNormal` / `LayerElementUV`：`MappingInformationType`（`ByVertice`/`ByPolygonVertex`/`ByPolygon`/`AllSame`）+ `ReferenceInformationType`（`Direct`/`IndexToDirect`）决定如何把数组贴到顶点上。
- **单位与轴**：FBX `GlobalSettings.UnitScaleFactor` 默认 1 = 1 cm（Unity 按 0.01 折算米）；原始 FBX 多为 Y-up，Unity 导入后 Z-up 左手系，读取时不要默认世界朝向。

## 5. 层级结构读取

- **OBJ**：只有 `o`/`g` 归属记录，无节点变换。
- **FBX 场景树**：`Connections` 的 `OO` 连接 = 父子关系（`C: "OO", 子ID, 父ID`；父 ID = 0 是根）。`Model` 是场景节点，`Null` = 空组节点，`Skeleton`/`LimbNode` = 骨骼。
- **变换**：`Lcl Translation / Rotation / Scaling`（欧拉角、度）。⚠️ 蒙皮绑定矩阵会组合 `PreRotation`/`PostRotation`，**最终矩阵 ≠ 三件套直接相乘**，做绑定矩阵计算时务必带上 Pre/Post（具体分解顺序以实际数据为准）。
- **骨架**：`Pose`/`BindPose` 的 `PoseNode`（`Node` = Model ID、`Matrix` = 4x4 行主序绑定矩阵，按节点顺序排列）。
- **骨骼判定**：不要只扫 Model 属性。很多角色 FBX 的骨骼写在 `NodeAttribute.TypeFlags/AttributeType`（`LimbNode`/`Skeleton`），再经 `OO` 挂到 Model。
- **名称**：二进制对象名常为 `Name\x00\x01Class`，展示时只取 `\x00` 前一段。

## 6. 使用示例

```bash
# OBJ 摘要（顶点/面/包围盒/对象/组/材质）
python scripts/obj_reader.py model.obj

# OBJ 结构化输出（供继续分析）
python scripts/obj_reader.py model.obj --json

# OBJ 顶点缓冲重映射统计（去重后唯一顶点数）
python scripts/obj_reader.py model.obj --remap

# FBX 摘要（格式/版本/对象统计/几何/包围盒/骨架链/GlobalSettings）
python scripts/fbx_reader.py model.fbx --summary

# FBX 节点树（前 N 层）与骨骼森林（忽略 Bone→Deformer 的 OO）
python scripts/fbx_reader.py model.fbx --tree 5
python scripts/fbx_reader.py model.fbx --skeleton

# FBX 指定对象清单与单 Geometry 详情
python scripts/fbx_reader.py model.fbx --objects
python scripts/fbx_reader.py model.fbx --geometry <ID>
```

输出解读示例（`fbx_reader.py model.fbx --summary`）：

```
格式: binary (版本 7700)          ← 自动检测 + 布局探测
对象: Geometry×2, Material×1, Model×2
几何: 2 个网格, 顶点 70000, 面 140000
包围盒: (-595.0, 547.8, -592.4) - (583.3, 681.0, 593.5)
设置: UpAxis=1, UnitScaleFactor=1.0
```

自带样例：`assets/sample_cube.obj`、`assets/sample_cube.fbx`。

## 7. 常见陷阱

| ❌ 错误做法 | ✅ 正确做法 |
|-----------|-----------|
| OBJ 索引按 0-based 读 | 先转 0-based：`idx - 1`（正）、`count + idx`（负） |
| `PolygonVertexIndex` 负值当索引 | 负值 = 面结束标记，`~x` 还原 |
| 压缩数组一律 `zlib.decompress(data, -15)` | 先试标准 zlib 头，失败再 `-15` raw（实测 7.7 带 zlib 头） |
| 假定 FBX 是 Y-up/米单位 | 读 `GlobalSettings`：`UnitScaleFactor`（默认 cm）、`UpAxis` |
| 假定 `<7500` 的 `end_offset` 是相对偏移 | Autodesk / Blender encode_bin 一律写**绝对文件偏移**；相对读会让 7400 全失败 |
| 锚点只认 `FBXHeaderVersion=1004` | 7.4 资产常见 1003；接受 `{1003,1004}` |
| 只在 Model 属性里找 `LimbNode` | 还要看 `NodeAttribute.TypeFlags` + `OO` 连接 |
| 用全部 `OO` 当骨骼父节点 | 蒙皮会写 `OO(Bone→Deformer)`，会盖掉 Model 父子；只要 Model↔Model |
| 把编译产物 `.obj` 当 Wavefront | MSVC/COFF `.obj` 含大量 NUL，应直接拒绝 |
| 假定二进制 record 头永远是 13 字节 | `>=7500` 实测 25 字节；`<7500` 才是 13 字节；用布局探测兜底 |
| 直接相乘 `T·R·S` 当最终绑定矩阵 | 蒙皮矩阵含 Pre/PostRotation，需核对 Pose/BindPose |
| 忽略 `--json` | 大文件结构化分析用 `--json` 输出，避免人工数数 |

## 8. 检查清单

- [ ] 已确认文件格式（OBJ / FBX ASCII / FBX 二进制）——二进制看头 23 字节 magic
- [ ] 已核对索引基数（OBJ 1-based → 0-based；FBX `~x` 负值语义）
- [ ] 已核对单位与轴（`UnitScaleFactor`、`UpAxis`；OBJ 无约定）
- [ ] 已确认层级根节点与骨架链（`OO` 连接、`Skeleton`/`LimbNode`、`BindPose`）
- [ ] 已跑脚本留存结构化输出（`--json`）供后续分析
- [ ] 深度几何需求已评估 trimesh 备用路径（`references/trimesh-fallback.md`）

## 9. FBX 二进制写入（Blender encode_bin 核心）

skill 内置 **Blender 开源 FBX 导出核心**（`scripts/encode_bin.py` + `data_types.py` +
`fbx_utils_threading.py`，GPL-2.0-or-later，保留 SPDX 头部；与 Blender 官方导出器
同款，FBX SDK 兼容）。**写 FBX 一律用它，禁止手写序列化**。实测手写 ASCII / 二进制
会被 Unity 拒绝（`File is corrupted` 或空模型）；换 `encode_bin` 后可导入。

### 关键文件

| 文件 | 职责 |
|---|---|
| `scripts/encode_bin.py` | 二进制序列化（25B 头、子节点哨兵、footer） |
| `scripts/data_types.py` / `fbx_utils_threading.py` | 类型码 / 线程池（encode_bin 依赖） |
| `scripts/fbx_bin_export.py` | 顶层结构构造（对照 Blender export_fbx_bin.py：header/SceneInfo/GlobalSettings/Documents/Definitions/Objects/Connections/Takes） |
| `scripts/extract_submeshes.py` | 从 FBX 拆指定 Model 的子网格、可选重定中心、输出独立 FBX |

依赖：Python 3.9+、numpy（encode_bin 顶层 import）。

### 用法

```bash
python scripts/extract_submeshes.py <input.fbx> --models 名1,名2,... \
    --output-dir <dir> --prefix xxx --center
```

### 二进制格式关键点（对照 Blender 源码 + 真实 FBX 实测确认）

| 项 | 规则 |
|---|---|
| record 头（7500+） | 25 字节：`<3Q`（end_offset 为**文件绝对偏移** / num_props / prop_length）+ 1B nlen |
| nlen | 纯名字长度，**不含 null**；name 区后无 null 字节 |
| S 字符串 | length **不含 null**，数据后无终止符 |
| 数组 | encoding=1（zlib 压缩），与 FBX SDK 导出一致 |
| 哨兵 | 每个有子节点的 record 的子节点列表后必须写 25B 全 0 |
| footer | FootID(16B) + 4B 0 + 16 对齐 padding + version(4B) + 120B 0 + 16B magic |
| 顶层段 | HeaderExtension / FileId / CreationTime / Creator / GlobalSettings / Documents / References / Definitions / Objects / Connections / Takes |
| SceneInfo | FBXHeaderExtension 内**必须**（缺它 Unity 报 corrupted） |
| Geometry↔Model | `OO` 连接（`OP` 是属性级连接，FBX SDK 不认） |
| 段级 Version/Count | 是**子节点**不是属性（GlobalSettings/Documents/Definitions） |

### 常见错误现象与根因

| 现象 | 根因 |
|---|---|
| Unity `File is corrupted` | 缺子节点哨兵 / 缺 footer / nlen 含 null / 段级属性错位 |
| Unity 空模型（ASCII FBX） | ASCII 与 FBX SDK 解析存在兼容性差异，**一律用二进制** |
| `Unexpected empty content`（meta） | externalObjects 块缩进错误（2/2/6/4 空格），`materials:` 必须 2 空格 |
| `missing nested Prefabs` | 删资产重建丢 guid → 引用悬空；覆盖保存（SaveAsPrefabAsset）保留 guid |

### Unity meta 材质映射（externalObjects）

FBX 导入后把 `lambert1` 映射到工程材质（与源 FBX meta 完全一致的格式，缩进敏感）：

```yaml
  externalObjects:
  - first:
      type: UnityEngine:Material
      assembly: UnityEngine.CoreModule
      name: lambert1
    second: {fileID: 2100000, guid: <材质guid>, type: 2}
  materials:
    materialImportMode: 2
```

### 陷阱

- fbx_reader 布局探测宽容（小数值下 rsvd=0 碰巧可解析），**能解析 ≠ FBX SDK 能导入**
- `FBXHeaderVersion` 写入用 1004；读取必须同时接受 1003（7.4）与 1004（7.7）
- 拆网格重定中心：顶点整体平移 `-= AABB center`，UV/法线/面索引原样保留（验证：数量 + 抽样值对比源文件）
