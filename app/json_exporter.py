from __future__ import annotations

import json
from pathlib import Path


def export_canvas_json(file_path: str, dbc_file: str | None, nodes: list[dict]) -> None:
    payload = {
        "dbc_file": dbc_file,
        "nodes": nodes,
    }
    Path(file_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_canvas_json(file_path: str) -> dict:
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Canvas JSON root must be an object.")

    nodes = payload.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("Canvas JSON field 'nodes' must be a list.")

    normalized_nodes = []
    for index, node in enumerate(nodes, start=1):
        normalized_nodes.append(_normalize_node(node, index))

    dbc_file = payload.get("dbc_file")
    if dbc_file is not None and not isinstance(dbc_file, str):
        raise ValueError("Canvas JSON field 'dbc_file' must be a string or null.")

    return {
        "dbc_file": dbc_file,
        "nodes": normalized_nodes,
    }


def _normalize_node(node: object, index: int) -> dict:
    if not isinstance(node, dict):
        raise ValueError(f"Node #{index} must be an object.")

    meta = node.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError(f"Node #{index} field 'meta' must be an object.")

    required_fields = ["node", "message", "signal", "direction"]
    normalized = {}
    for field_name in required_fields:
        value = node.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Node #{index} field '{field_name}' must be a non-empty string.")
        normalized[field_name] = value

    normalized["id"] = str(node.get("id") or "")
    normalized["x"] = float(node.get("x", 0))
    normalized["y"] = float(node.get("y", 0))
    normalized["frame_id"] = int(meta.get("frame_id", node.get("frame_id", 0)))
    normalized["start_bit"] = int(meta.get("start_bit", node.get("start_bit", 0)))
    normalized["length"] = int(meta.get("length", node.get("length", 0)))
    condition = node.get("condition")
    if condition is not None:
        normalized["condition"] = _normalize_condition(condition, index)
    return normalized


def _normalize_condition(condition: object, index: int) -> dict:
    if not isinstance(condition, dict):
        raise ValueError(f"Node #{index} field 'condition' must be an object.")

    required_fields = [
        "source_node",
        "source_message",
        "source_signal",
        "operator",
        "value",
    ]
    normalized = {}
    for field_name in required_fields:
        value = condition.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Node #{index} condition field '{field_name}' must be a non-empty string.")
        normalized[field_name] = value
    return normalized
