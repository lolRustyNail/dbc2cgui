"""Converter script loader and executor."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


class ConverterManager:
    def __init__(self):
        self._scripts: dict[str, dict] = {}

    def load_script(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Script not found: {file_path}")

        module_name = f"converter_{path.stem}_{id(path)}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, "convert"):
            del sys.modules[module_name]
            raise AttributeError(
                "Script must define a 'convert' function.\n\n"
                "Expected signature:\n"
                "  def convert(canvas_data: dict, output_dir: str) -> None"
            )

        self._scripts[str(path)] = {
            "name": path.stem,
            "path": str(path),
            "module": module,
        }
        return path.stem

    def run_converter(self, script_path: str, canvas_data: dict, output_dir: str) -> None:
        if script_path not in self._scripts:
            raise ValueError(f"Script not loaded: {script_path}")

        info = self._scripts[script_path]
        convert_func = info["module"].convert
        convert_func(canvas_data, output_dir)

    def get_scripts(self) -> list[dict]:
        return [{"name": v["name"], "path": v["path"]} for v in self._scripts.values()]

    def remove_script(self, script_path: str) -> None:
        info = self._scripts.pop(script_path, None)
        if info:
            module_name = info["module"].__name__
            sys.modules.pop(module_name, None)
