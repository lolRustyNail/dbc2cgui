from __future__ import annotations

from dataclasses import dataclass, field

from app.models import CustomNode, DbcDocument, LinkData


@dataclass(slots=True)
class AppState:
    current_document: DbcDocument | None = None
    current_canvas_file: str | None = None
    has_unsaved_changes: bool = False
    custom_nodes: list[CustomNode] = field(default_factory=list)
    links: list[LinkData] = field(default_factory=list)
