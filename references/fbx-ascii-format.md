# FBX ASCII 格式参考

FBX 的 ASCII 变体是二进制格式的人类可读等价物，结构与二进制一一对应（record → 节点，属性 → 属性）。导出为 ASCII 的文件一般体积大但易读，适合理解结构与手工构造测试夹具。

## 1. 词法

| 记号 | 说明 | 示例 |
|------|------|------|
| `;` | 行注释（到行尾） | `; FBX 7.3.0 project file` |
| `{ }` | 节点体边界（可嵌套） | `Objects: { ... }` |
| `*N` | 数组头，后跟元素列表 | `*4 { a: 1,2,3,4 }` |
| `,` | 属性分隔符 | `a: 1, 2, 3` |
| `"..."` | 字符串（UTF-8） | `a: "Model"` |
| `\n` | 元素数组内可换行续写 | |

## 2. 语法骨架

```
; FBX 7.3.0 project file
FBXHeaderExtension:  {
    FBXHeaderVersion: 1003
    FBXVersion: 7300
    Creator: "FBX SDK/FBX Plugins version 2020.0"
    ...
}
GlobalSettings:  {
    Version: 1000
    Properties70:  {
        P: "UpAxis", "int", "Integer", "",1
        P: "UnitScaleFactor", "double", "Number", "",1
    }
}
Definitions:  { ... }
Objects:  {
    Model: 396171613196160, "Model::RootNode", "Null" {
        Version: 232
        Properties70:  { ... }
    }
    ...
}
Connections:  {
    C: "OO", 396171613196160, 0
    ...
}
```

顶层分区：`FBXHeaderExtension` / `GlobalSettings` / `Documents` / `Definitions` / `Objects` / `Connections` / `Takes`（旧版动画）。解析器只需按 `名字: { }` 递归即可，不必硬编码分区名。

## 3. 属性类型标记

ASCII 中属性名后跟类型标记（`a: 值` 之外，类型可出现在 `*N { a: ... }` 里）：

| 标记 | 类型 | 示例 |
|------|------|------|
| `Y` | int16 | `a: Y: 100` |
| `C` | bool | `a: C: 1` |
| `I` | int32 | `a: I: 1004` |
| `F` | float32 | `a: F: 1.5` |
| `D` | float64 | `a: D: 0.01` |
| `L` | int64 | `a: L: 396171613196160` |
| `R` | raw bytes | `a: R: ...` |
| `S` | string | `a: S: "Model"` |
| 小写 | 数组 | `a: *8 { a: d: 0,1,2,... }` |

无标记时按值推断（整数 → I，带小数 → D，引号 → S）。

## 4. `O` 节点（对象定义）

```
Model: 396171613196160, "Model::RootNode", "Null" { ... }
```

- 第一参数：**对象 ID（int64）**
- 第二参数：`"类名::对象名"` 或 `"对象名"`，二进制里用 `\x00\x01` 分隔，ASCII 里是 `::`（也可能没有前缀）
- 第三参数：子类型（`Null`、`Mesh`、`Skeleton`、`LimbNode`、`Material`、`Texture`、`AnimationStack` 等）

## 5. `C` 节点（连接关系）

```
C: "OO", 子ID, 父ID
C: "OP", 对象ID, 属性ID, "属性名"
C: "PO", 属性ID, 对象ID, "属性名"
C: "PP", 属性1ID, 属性2ID, "名1", "名2"
```

- `OO`（Object-Object）：场景树父子关系；父 ID = 0 表示根节点。
- `OP`：对象 → 属性连接，如 `Geometry` 挂到 `Model` 的 `"Mesh"` 槽位。
- `PO` / `PP`：属性级连接（动画通道、材质属性等）。

## 6. 常用对象与关键属性

### 6.1 `Model`（场景节点）
```
Model: 1001, "Model::Root", "Null" {
    Version: 232
    Properties70:  {
        P: "Lcl Translation", "Lcl Translation", "", "A", 1, 2, 3
        P: "Lcl Rotation", "Lcl Rotation", "", "A", 0, 0, 90
        P: "Lcl Scaling", "Lcl Scaling", "", "A", 1, 1, 1
    }
    Shading: T
    Culling: "CullingOff"
}
```
- `Properties70` 里的 `P:` 行：`P: "名称", "类型", "标签", "标志", 值...`
- 变换三件套：`Lcl Translation / Lcl Rotation（欧拉角，度）/ Lcl Scaling`
- 骨骼模型带 `P: "PreRotation"` / `P: "PostRotation"` —— 蒙皮绑定矩阵会组合它们，**读取最终变换时不能只乘三件套**（见 SKILL.md 第 5 章注意点）。

### 6.2 `Geometry`（网格）
```
Geometry: 2001, "Geometry::Cube", "Mesh" {
    Vertices: *24 { a: 0,0,0, 1,0,0, ... }          ; double，每 3 个 = 1 顶点
    PolygonVertexIndex: *36 { a: 0,1,2,-4, 3,4,1,-7, ... }
    GeometryVersion: 124
    LayerElementNormal: 0 { ... }
    LayerElementUV: 0 { ... }
    LayerElementMaterial: 0 { MappingInformationType: "AllSame" ... }
    Layer: 0 { ... }
}
```
- `PolygonVertexIndex` 负值 = 面最后一个顶点，`~x` 还原（与二进制相同）。
- `LayerElementNormal` / `LayerElementUV` 内含：
  - `MappingInformationType`：`ByVertice` / `ByPolygonVertex` / `ByPolygon` / `AllSame`
  - `ReferenceInformationType`：`Direct`（数组与映射一一对应）或 `IndexToDirect`（另有 `NormalsIndex`/`UVIndex` 数组）

### 6.3 `Pose` / `BindPose`
```
Pose: 3001, "Pose::BindPose", "BindPose" {
    Type: "BindPose"
    PoseNode: 0 {
        Node: 1001
        Matrix: *16 { a: 1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1 }
    }
}
```
`PoseNode` 按节点顺序排列，`Node` 指向 Model ID，`Matrix` 是 4x4 行主序绑定矩阵。

## 7. 最小 ASCII FBX 骨架（可作测试夹具模板）

```
; FBX 7.3.0 project file
FBXHeaderExtension:  {
    FBXHeaderVersion: 1003
    FBXVersion: 7300
}
GlobalSettings:  {
    Version: 1000
    Properties70:  {
        P: "UpAxis", "int", "Integer", "",1
        P: "UpAxisSign", "int", "Integer", "",1
        P: "FrontAxis", "int", "Integer", "",2
        P: "UnitScaleFactor", "double", "Number", "",1
    }
}
Definitions:  {
    Version: 100
    Count: 3
    ObjectType: "Model" { Count: 3 }
}
Objects:  {
    Model: 101, "Model::Root", "Null" { Version: 232 }
    Model: 102, "Model::Cube", "Mesh" { Version: 232 }
    Geometry: 201, "Geometry::CubeGeo", "Mesh" {
        Vertices: *24 { a: 0,0,0, 1,0,0, 1,1,0, 0,1,0, 0,0,1, 1,0,1, 1,1,1, 0,1,1 }
        PolygonVertexIndex: *24 { a: 0,1,2,-4, 4,5,6,-8, 0,3,7,-5, 1,0,4,-6, 2,1,5,-7, 3,2,6,-8 }
        GeometryVersion: 124
    }
    Material: 301, "Material::M", "" { Version: 102 }
}
Connections:  {
    C: "OO", 101, 0
    C: "OO", 102, 101
    C: "OP", 201, 102, "Mesh"
    C: "OP", 301, 102, "Material"
}
```

> 注意 `PolygonVertexIndex` 里每组 3 个 + 1 个负值 = 1 个三角形；上例 24 个元素 = 6 个三角形面（立方体 6 面，每面 1 个三角形 —— 简化版，真实立方体每面 2 个三角形）。
