"""Background worker for converter script execution."""

from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal


class ConvertWorker(QThread):
    progress = Signal(int, int, str)
    finished = Signal(bool, str, str)

    def __init__(self, canvas_data: dict, output_dir: str, converter_manager, script_path: str, parent=None):
        super().__init__(parent)
        self._canvas_data = canvas_data
        self._output_dir = output_dir
        self._converter_manager = converter_manager
        self._script_path = script_path
        self._is_cancelled = False

    def cancel(self) -> None:
        self._is_cancelled = True

    def run(self) -> None:
        try:
            messages = self._canvas_data.get("messages", [])
            custom_nodes = self._canvas_data.get("custom_nodes", [])
            total = len(messages) + len(custom_nodes)

            if total == 0:
                self.finished.emit(True, self._output_dir, "")
                return

            self.progress.emit(0, total, "Starting conversion...")

            self._converter_manager.run_converter(
                self._script_path,
                self._canvas_data,
                self._output_dir,
            )

            self.finished.emit(True, self._output_dir, "")
        except Exception:
            tb = traceback.format_exc()
            self.finished.emit(False, self._output_dir, tb)
