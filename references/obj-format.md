# OBJ 格式参考

OBJ 是 Wavefront 推出的纯文本 3D 模型格式，一行一条语句，`#` 开头为注释。无固定单位与轴约定（若有单位信息通常写在 `#` 注释里，如 `# This file uses centimeters`）。

## 1. 语句速查表

| 语句 | 参数 | 示例 | 说明 |
|------|------|------|------|
| `v` | `x y z [w]` | `v 0.5 -1.0 2.0` | 顶点坐标（可选第 4 分量 w，一般忽略） |
| `vt` | `u v [w]` | `vt 0.5 0.25` | 纹理坐标（w 一般忽略；v 轴朝下是常见约定） |
| `vn` | `x y z` | `vn 0 1 0` | 顶点法线（需已归一化） |
| `f` | 顶点索引列表 | `f 1 2 3` | 面。每个元素是 `v` / `v/vt` / `v//vn` / `v/vt/vn` 之一 |
| `o` | 名称 | `o Cube` | 对象（object）标记，后续面归属该对象 |
| `g` | 名称列表 | `g face front` | 组（group）标记，一行可多个组名 |
| `usemtl` | 材质名 | `usemtl Red` | 切换当前材质，后续面使用该材质 |
| `mtllib` | 文件名 | `mtllib model.mtl` | 引用外部材质库（MTL 文件） |
| `s` | `1`/`off`/整数 | `s 1` | 平滑组：`off` 关闭、数字为组号（`1` 常用） |
| `l` | 索引列表 | `l 1 2 3` | 线（polyline），一般忽略 |
| `p` | 索引 | `p 5` | 点，一般忽略 |

## 2. 索引语义（关键坑）

- **1-based**：`f 1 2 3` 引用第 1/2/3 条 `v`。
- **负数**：`-1` 表示当前表中**最后一条**，`-2` 倒数第二条，以此类推。
- **每个面元素独立引用三张表**：`f v/vt/vn` 中的三个数字分别查 `v`、`vt`、`vn` 表，互不共享索引空间。

### 2.1 把 1-based/负数索引转成 0-based

```python
def resolve_index(idx: int, count: int) -> int | None:
    """OBJ 索引(1-based, 负数=从尾部数) -> 0-based；越界返回 None"""
    if idx > 0:
        out = idx - 1
    elif idx < 0:
        out = count + idx   # -1 -> count-1
    else:
        return None         # 0 是非法索引
    return out if 0 <= out < count else None
```

### 2.2 顶点缓冲重映射

OBJ 的面索引是 `(v, vt, vn)` 三元组，渲染时需要展开成"唯一顶点 + index buffer"：

```python
def remap_to_vertex_buffer(obj, triangulate=True):
    """把 (v,vt,vn) 三元组去重为唯一顶点列表，返回 positions/normals/uvs + index_buffer"""
    remap = {}                     # (v,vt,vn) -> 新顶点序号
    positions, normals, uvs = [], [], []
    index_buffer = []
    for face in obj.faces:
        corners = list(zip(face.vertex_indices, face.uv_indices or [], face.normal_indices or []))
        if len(corners) == 3 or not triangulate:
            corner_groups = [corners]
        else:                      # n-gon 三角化（扇形）
            corner_groups = [[corners[0], corners[i], corners[i + 1]] for i in range(1, len(corners) - 1)]
        for corners_3 in corner_groups:
            for v, vt, vn in corners_3:
                key = (v, vt, vn)
                if key not in remap:
                    remap[key] = len(positions)
                    positions.append(obj.vertices[v])
                    if vt is not None: uvs.append(obj.uvs[vt])
                    if vn is not None: normals.append(obj.normals[vn])
                index_buffer.append(remap[key])
    return positions, normals, uvs, index_buffer
```

> 注：UV/法线缺失时（`f v//vn`、`f v`）索引列表与顶点列表长度不一致，消费方需自行处理（补 0 或按需复制）。

## 3. 面（`f`）的四种写法

| 写法 | 含义 | 示例 |
|------|------|------|
| `f v` | 只有顶点 | `f 1 2 3` |
| `f v/vt` | 顶点 + UV | `f 1/1 2/2 3/3` |
| `f v//vn` | 顶点 + 法线 | `f 1//1 2//2 3//3` |
| `f v/vt/vn` | 顶点 + UV + 法线 | `f 1/1/1 2/2/2 3/3/3` |

**n-gon（>3 顶点的多边形）**：OBJ 允许任意多顶点面，渲染前需三角化（见 2.2 的扇形算法）。三角形顺序遵循右手定则。

## 4. 对象与组

- `o` 与 `g` 都只影响"归属记录"，不产生任何几何变换。
- 常见组织习惯：一个文件一个 `o` 或多个 `g`；组可嵌套命名（`g A/B/C` 表示层级路径，非强制）。
- `usemtl` 之后的 `f` 使用该材质；材质列表在引用的 `.mtl` 文件里（本 skill 不解析 MTL）。

## 5. 解析容错要求

- 行首/行中多余空白、制表符：按空白切分即可。
- 行尾 `\` 续行：真实文件少见，解析器可先按续行合并。
- `f` 中元素可带额外空白（`f 1 / 2` 这类不规范写法）：按 `/` 切分后剔除空串。
- 未知语句（如 `vp`、`surf`）：跳过并记入 warnings，不中断。
- 大文件：不要一次性全量打印顶点，默认输出统计信息，`--vertices N` 限量查看。

## 6. 包围盒

```python
def compute_bounds(verts):
    mins = [min(v[i] for v in verts) for i in range(3)]
    maxs = [max(v[i] for v in verts) for i in range(3)]
    return tuple(mins), tuple(maxs)
```

> 注意：包围盒只对 `v` 计算，不含任何变换（OBJ 无变换概念）。
