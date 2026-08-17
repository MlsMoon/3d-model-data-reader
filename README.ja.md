# 3d-model-data-reader

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

OBJ / FBX の内部データを読み、Unity が読めるバイナリ FBX を書くための [Agent Skill](https://agentskills.io/specification) です。

このリポジトリ自体が skill フォルダです。ディレクトリ名、GitHub リポジトリ名、`SKILL.md` の `name` はすべて `3d-model-data-reader` のままにしてください。

## これは何か

OBJ のインデックスを 0-based として読んだり、FBX バイナリの record ヘッダを 13 バイトだと決めつけたりすると、メッシュが壊れます。形式の要点、標準ライブラリだけの読み取りスクリプト、Unity が読めるバイナリ FBX の書き出しを、インストール可能な 1 フォルダにまとめています。

特定のゲームプロジェクトには依存しません。リポジトリのルートが skill のルートです。

## できること

| 用途 | ツール |
|------|------|
| OBJ の頂点 / UV / 法線 / 面 / オブジェクト / グループ | `scripts/obj_reader.py`（Python 3.9+、標準ライブラリのみ） |
| FBX ASCII / バイナリ：オブジェクト、接続、階層、スケルトン、AABB | `scripts/fbx_reader.py`（Python 3.9+、標準ライブラリのみ） |
| Model 名でサブメッシュを分割（任意で中心を原点へ） | `scripts/extract_submeshes.py`（`numpy` が必要） |
| Unity / FBX SDK が読めるバイナリ FBX を書く | `scripts/encode_bin.py`（Blender 出力コア、`numpy` が必要） |
| ブーリアンやサンプリングなど深い幾何 | `references/trimesh-fallback.md` |

デフォルトは人間向けサマリ。`--json` で UTF-8 の構造化出力。失敗時は終了コード非 0、理由は stderr。

サンプル：`assets/sample_cube.obj`、`assets/sample_cube.fbx`。

## インストール

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

## 実行環境

- 読み取り：Python 3.9+（標準ライブラリのみ）
- 書き出し / 分割：加えて `numpy`（`pip install numpy`）

## クイックスタート

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

## ライセンス

GPL-2.0-or-later。`LICENSE` と `NOTICE` を参照してください。

`scripts/encode_bin.py`、`scripts/data_types.py`、`scripts/fbx_utils_threading.py` は Blender / assimp の出力スタック由来で、元の SPDX ヘッダを残しています。残りのファイルも同じライセンスです。
