# 3d-model-data-reader

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

这是一份 [Agent Skill](https://agentskills.io/specification)，用来教 AI 读取 OBJ / FBX 内部数据，并写出 Unity 能导入的二进制 FBX。

本仓库**就是** skill 目录。目录名、GitHub 仓库名、`SKILL.md` 的 `name` 必须都是 `3d-model-data-reader`。

## 这是什么

AI 读模型时很容易把 OBJ 索引当成 0-based，或按旧文档把 FBX 二进制 record 头当成 13 字节。本仓库把格式要点、零依赖读取脚本，以及 Unity 能导入的二进制 FBX 写入能力打成一个可安装目录。

不绑定任何游戏工程。仓库根目录就是 skill 根目录。

## 能做什么

| 需求 | 工具 |
|------|------|
| 读 OBJ 顶点 / UV / 法线 / 面 / 对象 / 组 | `scripts/obj_reader.py`（Python 3.9+，仅标准库） |
| 读 FBX ASCII / 二进制：对象、连接、层级、骨架、包围盒 | `scripts/fbx_reader.py`（Python 3.9+，仅标准库） |
| 按 Model 名拆子网格，可选重定中心 | `scripts/extract_submeshes.py`（需要 `numpy`） |
| 写出 Unity / FBX SDK 能导入的二进制 FBX | `scripts/encode_bin.py`（Blender 导出核心，需要 `numpy`） |
| 布尔、采样等深度几何 | `references/trimesh-fallback.md` |

脚本默认打印人类可读摘要；`--json` 输出 UTF-8 结构化结果。失败时退出码非 0，原因写在 stderr。

自带样例：`assets/sample_cube.obj`、`assets/sample_cube.fbx`。

## 安装

克隆到所用 Agent 的 skills 目录，**文件夹名必须是** `3d-model-data-reader`：

```bash
# Claude Code
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.claude/skills/3d-model-data-reader

# Codex / 其他 Agents
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.agents/skills/3d-model-data-reader

# Grok
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.grok/skills/3d-model-data-reader
```

装好后让 Agent 检查某个 OBJ/FBX，或执行 `/3d-model-data-reader`。

给 Agent 的指令在 `SKILL.md`，格式细节在 `references/`。

## 环境

- 只读：Python 3.9+，标准库即可
- 写入 / 拆网格：额外安装 `numpy`（`pip install numpy`）

## 快速试用

```bash
python scripts/obj_reader.py assets/sample_cube.obj
python scripts/obj_reader.py assets/sample_cube.obj --json
python scripts/fbx_reader.py assets/sample_cube.fbx --summary
python scripts/fbx_reader.py assets/sample_cube.fbx --tree 5
python scripts/fbx_reader.py assets/sample_cube.fbx --skeleton

python scripts/extract_submeshes.py input.fbx \
  --models 名称A,名称B --output-dir out --prefix part_ --center
```

不要手写 ASCII 或二进制 FBX。Unity 通常会报 `File is corrupted` 或导入空模型。写入一律走 `encode_bin`。

## 许可

GPL-2.0-or-later，见 `LICENSE` 与 `NOTICE`。

`scripts/encode_bin.py`、`scripts/data_types.py`、`scripts/fbx_utils_threading.py` 来自 Blender / assimp 导出栈，保留原 SPDX 头。其余文件同样按 GPL-2.0-or-later 分发。
