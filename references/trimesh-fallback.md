# trimesh 备用方案

`scripts/obj_reader.py` 与 `scripts/fbx_reader.py` 是**默认路径**（纯 Python 标准库，零依赖）。当需要**深度几何**时才升级到 trimesh。

## 1. 何时启用 trimesh

| 场景 | 默认脚本 | trimesh |
|------|----------|---------|
| 顶点/面/包围盒统计、层级结构、骨架链 | ✅ 足够 | — |
| 二进制 FBX 的几何全量提取（法线/UV/纹理坐标完整展开） | ⚠️ 仅结构级 | ✅ 推荐 |
| 网格布尔、切片、采样、水密修复等几何运算 | ❌ | ✅ 推荐 |
| 只读单次查询（目标机器无 Python 环境） | ✅ | — |

## 2. 安装

```bash
pip install trimesh
# 可选：完整格式支持（glTF/PLY 等）
pip install trimesh[all]
```

## 3. 加载与遍历

```python
import trimesh

# 自动按扩展名加载；FBX 依赖内部解析器，OBJ 原生支持
scene = trimesh.load("model.fbx")      # 多对象 -> Scene
mesh  = trimesh.load("model.obj", force="mesh")  # 强制当作单一网格

# 顶点与面
mesh.vertices.shape      # (N, 3)
mesh.faces.shape         # (M, 3)
mesh.vertices.min(axis=0), mesh.vertices.max(axis=0)   # 包围盒

# 法线/UV（若文件含）
mesh.vertex_normals
mesh.visual.uv          # (N, 2) 或 (M*3, 2)

# Scene 层级遍历
for name, geom in scene.graph.nodes_geometry:
    world_transform = scene.graph.get(name)[0]   # 世界变换 4x4
    print(name, geom)

# 场景包含的几何体
for name, mesh in scene.geometry.items():
    print(name, mesh.vertices.shape[0], mesh.faces.shape[0])
```

## 4. 单位与轴（重要）

- trimesh 内部以**米**为单位、Y-up（OpenGL 习惯）。
- `trimesh.load(path, process=True)` 默认会调用 `FixNormals` / `merge_vertices` 等清理：**统计数字可能与原始文件不完全一致**（顶点合并、法线修正）。
- 读取 FBX（cm、Y-up）时，`vertices` 已是原始数据乘 0.01 后按 trimesh 约定处理的结果；若要还原成原始 FBX 数值，除以 `UnitScaleFactor` 对应的 0.01 并核对轴。
- 需要"读什么报什么"时用 `process=False`：

```python
raw = trimesh.load("model.fbx", process=False, force="mesh")
```

## 5. 注意事项（执行时以实际安装版本为准）

- 二进制 FBX 的完整几何读取依赖 trimesh 内置的 FBX 解析器，**不同版本支持度不同**（早期版本对 7.x 二进制支持不完整，可能报错或丢失 UV/法线）。装好后先用一个已知模型冒烟测试。
- 骨骼/动画不属于 trimesh 的能力范围——需要蒙皮矩阵时仍回到本 skill 的 `fbx_reader.py`（Pose/BindPose）或 Unity 导入。
- trimesh 是**备用路径**：AI 默认先跑标准库脚本；只有当标准库脚本不满足（需几何运算/完整 UV 展开）且环境允许 `pip install` 时才使用。
