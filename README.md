# 3d-model-data-reader

Agent Skill for reading OBJ / FBX mesh data (vertices, normals, UVs, faces, node tree, skeleton) and writing Unity-importable binary FBX.

This repository **is** the skill folder. Clone it so the directory name stays `3d-model-data-reader`.

## Install

```bash
git clone https://github.com/MlsMoon/3d-model-data-reader.git \
  ~/.claude/skills/3d-model-data-reader
```

The same clone works in `~/.agents/skills/` or `~/.grok/skills/`. After install, ask the agent to inspect an OBJ/FBX or run `/3d-model-data-reader`.

Agent instructions live in `SKILL.md`. Format details are in `references/`.

## Requirements

- Read path: Python 3.9+, standard library only
- Write / split path (`scripts/encode_bin.py`, `scripts/extract_submeshes.py`): also needs `numpy`

```bash
python scripts/obj_reader.py assets/sample_cube.obj
python scripts/fbx_reader.py assets/sample_cube.fbx --summary
```

## License

GPL-2.0-or-later. See `LICENSE` and `NOTICE`.

The FBX writer (`scripts/encode_bin.py`, `scripts/data_types.py`, `scripts/fbx_utils_threading.py`) comes from the Blender / assimp export stack and keeps its original SPDX headers. The rest of this repository is distributed under the same license.
