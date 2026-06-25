#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_local_module():
    script_path = Path(__file__).resolve().parent / "jav_rename_videos.py"
    module_name = "jav_rename_videos_local"
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from: {script_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    module = load_local_module()
    raise SystemExit(module.launch_gui())