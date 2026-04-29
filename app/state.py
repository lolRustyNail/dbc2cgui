from __future__ import annotations

from dataclasses import dataclass

from app.models import DbcDocument


@dataclass(slots=True)
class AppState:
    current_document: DbcDocument | None = None
    current_canvas_file: str | None = None
    has_unsaved_changes: bool = False
