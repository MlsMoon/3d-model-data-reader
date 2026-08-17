# FBX 二进制格式参考

> ⚠️ **本文档的"实测锚点"与"布局探测"结论基于本项目真实文件（`Assets/Arts/TempAssets/Mesh/MH_Grass01.fbx`，FBX 7.7）验证，`fbx_reader.py` 的 `_probe_layout` 已实测通过。** 公开文档描述的头部布局与实测存在出入（见 §2 的 25 字节头），读取旧版本（7.4 及以下）文件时需做布局探测（见 §7）。

## 1. 文件头（Header）

| 偏移 | 长度 | 内容 |
|------|------|------|
| 0 | 23 | magic：`Kaydara FBX Binary  \x00\x1a\x00`（注意中间是两个空格，`\x1a` 是 DOS EOF 标记） |
| 23 | 4 | 版本号，little-endian uint32（实测 `MH_Grass01.fbx` = `0x1E14` = 7700，即 FBX 7.7） |
| 27 | — | **root record 头从此处直接开始**（`fbx_reader.py` 布局探测确认，无额外 padding；`d7 0a 00 00` 是 root record 的 end offset = 2775，非 padding） |

版本速查：6100=FBX 6.1、6200=6.2、7000=7.0、7100=7.1、7400=7.4、7500=7.5、7700=7.7。

**版本号读取代码**：

```python
def read_version(path: Path) -> int | None:
    with open(path, "rb") as fp:
        head = fp.read(27)
    if head[:23] != FBX_MAGIC:
        return None
    return struct.unpack_from("<I", head, 23)[0]
```

## 2. Record 结构（实测 FBX 7.7：25 字节头）

**⚠️ 关键实测发现**：FBX 7.7 的 record 头是 **25 字节**，不是公开文档常见的 13 字节，且 `end offset` 语义为**下一 record 的绝对文件偏移**（从文件头 0 算起），不是相对偏移：

```
[4 字节 end offset]      ← 下一 record 的绝对文件偏移（实测：root=2775、FBXHeaderVersion=116、FBXVersion=156）
[4 字节 rsvd]            ← 恒为 0（实测）
[4 字节 num properties]
[4 字节 rsvd]            ← 恒为 0（实测）
[4 字节 property list length]
[4 字节 rsvd]            ← 恒为 0（实测）
[1 字节 name length]
[name 字节串]             ← 节点名（不含结尾 \0）
[属性列表...]             ← 依次排列
[子 record...]           ← 直到 end offset 边界（绝对偏移）
```

- 文件以 **25 字节全零 null record** 结尾（end=0、num=0、propListLen=0、nameLen=0）。
- **实测锚点验证**（MH_Grass01.fbx）：root nameLen @51 = 18（name `FBXHeaderExtension` @52-69）；`FBXHeaderVersion` record 头 @70-94（end=116、num=1、plen=5、nameLen=16）、属性 `I`=1004 @112-115；`FBXVersion` record 头 @116-140（end=156）、属性 `I`=7700 @152-155。
- **未发现独立 CRC 字段**（7100+ CRC 的说法在此版本不成立；rsvd 字段恒 0，语义未知）。
- 旧版本（13/17 字节头、end 为相对偏移）仍由 `_probe_layout` 候选支持。

## 3. 属性类型（1 字节 type code 前缀）

| code | 类型 | 字节数 |
|------|------|--------|
| `Y` | int16 | 2 |
| `C` | bool | 1 |
| `I` | int32 | 4 |
| `F` | float32 | 4 |
| `D` | float64 | 8 |
| `L` | int64 | 8 |
| `R` | raw bytes | 4 字节长度 + 数据 |
| `S` | string | 4 字节长度 + UTF-8 数据 ★（长度是否含结尾 `\0` 需核实） |
| `f` | float32 数组 | 见下 |
| `d` | float64 数组 | 见下 |
| `l` | int64 数组 | 见下 |
| `i` | int32 数组 | 见下 |
| `b` | bool 数组 | 见下 |
| `c` | 原始字节数组 | 见下 |

**数组布局**：`[4 字节元素数][4 字节 encoding][4 字节压缩后数据长度][数据]`
- `encoding = 0`：原始数据（小端、按元素类型）。
- `encoding = 1`：压缩数据。**⚠️ 实测（7.7）数据带标准 zlib 头（首字节 `78`）**，与公开文档"raw DEFLATE"不符；稳妥做法两种都兼容：

```python
import zlib
def decompress_array(data: bytes) -> bytes:
    try:
        return zlib.decompress(data)       # 标准 zlib 头（实测 7.7 文件）
    except zlib.error:
        return zlib.decompress(data, -15)  # raw DEFLATE（经典 FBX 规范）
```

## 4. 端序

**FBX 二进制始终 little-endian**。常见解析错误不是端序，而是"4 字节计数 + 1 字节 type code"混排导致的字段错位，以及大文件/大数组的元素数可能用 int64。

## 5. 语义层（对象与连接）

解析出 record 树后，重点看三个顶层分区：

### 5.1 `Objects`（对象定义）
每个 `O` 节点是一个对象，属性为：

```
[类型字符串(如 "Model"/"Geometry"/"Material"/"AnimationStack")]
[名称字符串]            ← 含 \x00\x01 分隔符（模型名 + 类名拼接），需 split("\x00\x01")
[属性 flag]             ← 通常为 0
...自定义属性...
```

**对象 ID 是 `O` 节点属性后的 int64 值**——FBX 用 ID 而非对象名关联。

### 5.2 `Connections`（连接关系）
`C` 节点属性：`[child ID (L)][parent ID (L)][可选属性名 (S)]`

四种连接由参数构成区分：
- **OO**（Object-Object）：`C: "OO", childID, parentID` —— 模型树父子关系
- **OP**（Object-Property）：`C: "OP", objID, propID, "PropName"` —— 对象到属性（如 Geometry→Model 的 Mesh 槽位）
- **PO**（Property-Object）：`C: "PO", propID, objID, "PropName"`
- **PP**（Property-Property）：`C: "PP", prop1ID, prop2ID, "name1", "name2"`

### 5.3 常用对象要点

| 对象类型 | 关键数据 | 说明 |
|----------|----------|------|
| `Model` | `Lcl Translation/Rotation/Scaling` | 场景节点；`Skeleton`/`LimbNode` 属性区分骨骼；`Null` = 空组节点 |
| `Geometry` | `Vertices`（`d` 数组，每 3 个 = 1 顶点）、`PolygonVertexIndex`（`i` 数组） | 网格数据本体 |
| `Material` | 颜色等属性 | 材质 |
| `Pose` | `Matrix` 数组（按节点顺序） | 绑定姿态；`BindPose` 用于蒙皮 |

**`PolygonVertexIndex` 负值语义（关键坑）**：负值表示该顶点是**所在面的最后一个顶点**，索引需按 `~x`（按位取反）还原：

```python
def to_face_vertices(pvi):
    """PolygonVertexIndex -> 面列表；负值 = 面结束标记"""
    faces, current = [], []
    for x in pvi:
        if x < 0:
            current.append(~x)      # ~(-1) = 0, ~(-4) = 3
            faces.append(current)
            current = []
        else:
            current.append(x)
    if current:
        faces.append(current)       # 容错：无结束标记的残面
    return faces
```

## 6. GlobalSettings（单位与轴）

`GlobalSettings` 分区内：
- `UnitScaleFactor`：默认 `1` = 1 cm；**Unity 导入默认折算为 0.01 → 米**。
- `UpAxis` / `UpAxisSign` / `FrontAxis` / `CoordAxis`：轴系定义。原始 FBX 多为 Y-up，Unity 导入后是 Z-up 左手系 —— 读取数据时不要默认世界朝向与 Unity 一致。

## 7. 布局探测（已实测通过）

**结论**：`fbx_reader.py` 的 `_probe_layout` 已在本项目真实 7.7 文件上实测通过，命中 `(root_start=27, header_size=25)`。

**探测流程**：对候选 `root_start ∈ {27, 31}` × `header_size ∈ {13, 17, 25}` 的组合逐一套用（13/17 头解析失败会抛异常，`_try_layout` 捕获后返回 None 继续尝试），用**锚点断言**判定：

- 节点树中必须出现 `FBXHeaderVersion`（属性值 = 1004）
- 必须出现 `FBXVersion`（属性值 = §1 读出的版本号）

命中断言的组合即为正确布局。若未来遇到新版本文件全部候选失败，按 §8 核实清单排查字段布局后回填本文件。

**实测锚点（MH_Grass01.fbx，FBX 7.7，25 字节头）**：

| 锚点 | 字节偏移 | 值 |
|------|----------|-----|
| root record 头（end=2775） | 27-50 | — |
| `FBXHeaderExtension` nameLen | 51 | 18 |
| `FBXHeaderExtension` name | 52-69 | — |
| `FBXHeaderVersion` record 头 | 70-94 | end=116、num=1、plen=5、nameLen=16 |
| `FBXHeaderVersion` 属性 `I` | 112-115 | 1004 |
| `FBXVersion` record 头 | 116-140 | end=156 |
| `FBXVersion` 属性 `I` | 152-155 | 7700 |

> 这些偏移是解析器自检的固定断言；换版本的文件会不同，不要硬编码进解析逻辑。

## 8. 核实清单（实测状态）

- [x] 1. 7500+ 头部：**无 padding** —— `d7 0a 00 00`（@27-30）是 root record 的 end offset（=2775），非 padding
- [x] 2. CRC 字段：**7.7 实测无独立 CRC**（rsvd 字段恒 0，语义未知，读后丢弃）
- [x] 3. record 头：**7.7 实测 25 字节**（end4 + rsvd4 + num4 + rsvd4 + plen4 + rsvd4 + nlen1），end = **下一 record 绝对偏移**；13/17 字节经典头保留为候选（end 为相对偏移）
- [x] 4. `S` 字符串与 name：实测**不含结尾 `\0`**（nameLen=18 → name 恰好 18 字节）
- [x] 5. footer 结构：解析到 null record 即停止，不依赖 footer（未深入，够用）
- [ ] 6. 多版本样本回归：仅 7.7（MH_Grass01/MH_House01 等）实测；7.0/7.1/7.4 待测（遇到时走 §7 探测流程并回填）
- [x] 7. 数组压缩：**实测带标准 zlib 头**（`78 01` 开头），兼容 raw DEFLATE 双路径解压
