# 3d-model-data-reader

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)

An [Agent Skill](https://agentskills.io/specification) that teaches AI agents how to read OBJ / FBX internals and write Unity-importable binary FBX.

This repository **is** the skill folder. The directory name, GitHub repo name, and `SKILL.md` `name` field must all stay `3d-model-data-reader`.

## What this is

Agents often guess OBJ indices or FBX binary headers and get the mesh wrong. This skill packages the format rules plus two stdlib Python readers and a Blender-compatible binary writer, so an agent can inspect a model without opening Unity, Blender, or another DCC.

It is not tied to any game project.

## What you get

| Need | Tool |
|------|------|
| OBJ vertices, UVs, normals, faces, objects, groups | `scripts/obj_reader.py` (Python 3.9+, stdlib only) |
| FBX ASCII / binary: objects, connections, hierarchy, skeleton, bbox | `scripts/fbx_reader.py` (Python 3.9+, stdlib only) |
| Split named models out of one FBX, optional recenter | `scripts/extract_submeshes.py` (needs `numpy`) |
| Write FBX that Unity / FBX SDK will actually import | `scripts/encode_bin.py` (Blender export core, needs `numpy`) |
| Deeper mesh ops (boolean, sampling) | `references/trimesh-fallback.md` |

Readers print a human summary by default. Pass `--json` for structured stdout (UTF-8). Failures exit non-zero and explain on stderr.

Sample files: `assets/sample_cube.obj`, `assets/sample_cube.fbx`.

## Install

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

## Requirements

- Read path: Python 3.9+, standard library only
- Write / split path: also `numpy` (`pip install numpy`)

## Quick start

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

## License

GPL-2.0-or-later. See `LICENSE` and `NOTICE`.

`scripts/encode_bin.py`, `scripts/data_types.py`, and `scripts/fbx_utils_threading.py` come from the Blender / assimp export stack and keep their SPDX headers. The rest of this repository uses the same license.
