# 3d-model-data-reader

[English](#english) · [简体中文](#简体中文) · [日本語](#日本語)

An [Agent Skill](https://agentskills.io/specification) that teaches AI agents how to read OBJ / FBX internals and write Unity-importable binary FBX.

This repository **is** the skill folder. The directory name, GitHub repo name, and `SKILL.md` `name` field must all stay `3d-model-data-reader`.

---

## English

### What this is

Agents often guess OBJ indices or FBX binary headers and get the mesh wrong. This skill packages the format rules plus two stdlib Python readers and a Blender-compatible binary writer, so an agent can inspect a model without opening Unity, Blender, or another DCC.

It is not tied to any game project.

### What you get

| Need | Tool |
|------|------|
| OBJ vertices, UVs, normals, faces, objects, groups | `scripts/obj_reader.py` (Python 3.9+, stdlib only) |
| FBX ASCII / binary: objects, connections, hierarchy, skeleton, bbox | `scripts/fbx_reader.py` (Python 3.9+, stdlib only) |
| Split named models out of one FBX, optional recenter | `scripts/extract_submeshes.py` (needs `numpy`) |
| Write FBX that Unity / FBX SDK will actually import | `scripts/encode_bin.py` (Blender export core, needs `numpy`) |
| Deeper mesh ops (boolean, sampling) | `references/trimesh-fallback.md` |

Readers print a human summary by default. Pass `--json` for structured stdout (UTF-8). Failures exit non-zero and explain on stderr.

Sample files: `assets/sample_cube.obj`, `assets/sample_cube.fbx`.

### Install

Clone into your agent's skills directory. Keep the folder name:

```bash
# Claude Code
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.claude/skills/3d-model-data-reader

# Codex / other Agents
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.agents/skills/3d-model-data-reader

# Grok
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.grok/skills/3d-model-data-reader
```

Then ask the agent to inspect an OBJ/FBX, or run `/3d-model-data-reader`.

Agent instructions: `SKILL.md`. Format notes: `references/`.

### Requirements

- Read path: Python 3.9+, standard library only
- Write / split path: also `numpy` (`pip install numpy`)

### Quick start

```bash
python scripts/obj_reader.py assets/sample_cube.obj
python scripts/obj_reader.py assets/sample_cube.obj --json
python scripts/fbx_reader.py assets/sample_cube.fbx --summary
python scripts/fbx_reader.py assets/sample_cube.fbx --tree 5
python scripts/fbx_reader.py assets/sample_cube.fbx --skeleton

python scripts/extract_submeshes.py input.fbx \
  --models NameA,NameB --output-dir out --prefix part_ --center
```

Do not hand-write FBX ASCII or binary. Unity typically rejects those files. Always go through `encode_bin`.

### License

GPL-2.0-or-later. See `LICENSE` and `NOTICE`.

`scripts/encode_bin.py`, `scripts/data_types.py`, and `scripts/fbx_utils_threading.py` come from the Blender / assimp export stack and keep their SPDX headers. The rest of this repository uses the same license.

---

## 简体中文

### 这是什么

AI 读模型时很容易把 OBJ 索引当成 0-based，或按旧文档把 FBX 二进制 record 头当成 13 字节。本仓库是一份 [Agent Skill](https://agentskills.io/specification)：把格式要点、零依赖读取脚本，以及 Unity 能导入的二进制 FBX 写入能力打成一个可安装目录。

不绑定任何游戏工程。仓库根目录就是 skill 根目录。

### 能做什么

| 需求 | 工具 |
|------|------|
| 读 OBJ 顶点 / UV / 法线 / 面 / 对象 / 组 | `scripts/obj_reader.py`（Python 3.9+，仅标准库） |
| 读 FBX ASCII / 二进制：对象、连接、层级、骨架、包围盒 | `scripts/fbx_reader.py`（Python 3.9+，仅标准库） |
| 按 Model 名拆子网格，可选重定中心 | `scripts/extract_submeshes.py`（需要 `numpy`） |
| 写出 Unity / FBX SDK 能导入的二进制 FBX | `scripts/encode_bin.py`（Blender 导出核心，需要 `numpy`） |
| 布尔、采样等深度几何 | `references/trimesh-fallback.md` |

脚本默认打印人类可读摘要；`--json` 输出 UTF-8 结构化结果。失败时退出码非 0，原因写在 stderr。

自带样例：`assets/sample_cube.obj`、`assets/sample_cube.fbx`。

### 安装

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

### 环境

- 只读：Python 3.9+，标准库即可
- 写入 / 拆网格：额外安装 `numpy`（`pip install numpy`）

### 快速试用

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

### 许可

GPL-2.0-or-later，见 `LICENSE` 与 `NOTICE`。

`scripts/encode_bin.py`、`scripts/data_types.py`、`scripts/fbx_utils_threading.py` 来自 Blender / assimp 导出栈，保留原 SPDX 头。其余文件同样按 GPL-2.0-or-later 分发。

---

## 日本語

### これは何か

OBJ のインデックスを 0-based として読んだり、FBX バイナリの record ヘッダを 13 バイトだと決めつけたりすると、メッシュが壊れます。このリポジトリは [Agent Skill](https://agentskills.io/specification) です。形式の要点、標準ライブラリだけの読み取りスクリプト、Unity が読めるバイナリ FBX の書き出しを、インストール可能な 1 フォルダにまとめています。

特定のゲームプロジェクトには依存しません。リポジトリのルートが skill のルートです。

### できること

| 用途 | ツール |
|------|------|
| OBJ の頂点 / UV / 法線 / 面 / オブジェクト / グループ | `scripts/obj_reader.py`（Python 3.9+、標準ライブラリのみ） |
| FBX ASCII / バイナリ：オブジェクト、接続、階層、スケルトン、AABB | `scripts/fbx_reader.py`（Python 3.9+、標準ライブラリのみ） |
| Model 名でサブメッシュを分割（任意で中心を原点へ） | `scripts/extract_submeshes.py`（`numpy` が必要） |
| Unity / FBX SDK が読めるバイナリ FBX を書く | `scripts/encode_bin.py`（Blender 出力コア、`numpy` が必要） |
| ブーリアンやサンプリングなど深い幾何 | `references/trimesh-fallback.md` |

デフォルトは人間向けサマリ。`--json` で UTF-8 の構造化出力。失敗時は終了コード非 0、理由は stderr。

サンプル：`assets/sample_cube.obj`、`assets/sample_cube.fbx`。

### インストール

エージェントの skills ディレクトリへ clone してください。**フォルダ名は必ず** `3d-model-data-reader`：

```bash
# Claude Code
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.claude/skills/3d-model-data-reader

# Codex / その他の Agents
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.agents/skills/3d-model-data-reader

# Grok
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.grok/skills/3d-model-data-reader
```

インストール後、OBJ/FBX の確認を依頼するか `/3d-model-data-reader` を実行します。

エージェント向け手順は `SKILL.md`、形式の詳細は `references/` です。

### 実行環境

- 読み取り：Python 3.9+（標準ライブラリのみ）
- 書き出し / 分割：加えて `numpy`（`pip install numpy`）

### クイックスタート

```bash
python scripts/obj_reader.py assets/sample_cube.obj
python scripts/obj_reader.py assets/sample_cube.obj --json
python scripts/fbx_reader.py assets/sample_cube.fbx --summary
python scripts/fbx_reader.py assets/sample_cube.fbx --tree 5
python scripts/fbx_reader.py assets/sample_cube.fbx --skeleton

python scripts/extract_submeshes.py input.fbx \
  --models NameA,NameB --output-dir out --prefix part_ --center
```

ASCII / バイナリ FBX を手書きしないでください。Unity は `File is corrupted` や空モデルになりがちです。書き出しは必ず `encode_bin` 経由にします。

### ライセンス

GPL-2.0-or-later。`LICENSE` と `NOTICE` を参照してください。

`scripts/encode_bin.py`、`scripts/data_types.py`、`scripts/fbx_utils_threading.py` は Blender / assimp の出力スタック由来で、元の SPDX ヘッダを残しています。残りのファイルも同じライセンスです。
