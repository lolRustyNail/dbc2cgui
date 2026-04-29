from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

SCHEMA_VERSION = 2


def export_canvas_json(
    file_path: str,
    dbc_file: str | None,
    nodes: list[dict],
    links: list[dict] | None = None,
) -> None:
    """Export the canvas state as a self-contained JSON document.

    Nodes sharing the same message are grouped under that message, and every
    signal entry carries the full set of DBC attributes (byte order, factor,
    offset, unit, choices, receivers, comment, etc.) when a DBC file is
    available, so that downstream code generation can consume the JSON alone
    without re-reading the original .dbc file.
    """
    messages, custom_nodes = _build_messages_and_custom_from_canvas(dbc_file, nodes)
    payload = {
        "version": SCHEMA_VERSION,
        "dbc_file": dbc_file,
        "messages": messages,
    }
    if custom_nodes:
        payload["custom_nodes"] = custom_nodes
    if links:
        payload["links"] = links
    Path(file_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def load_canvas_json(file_path: str) -> dict:
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Canvas JSON root must be an object.")

    dbc_file = payload.get("dbc_file")
    if dbc_file is not None and not isinstance(dbc_file, str):
        raise ValueError("Canvas JSON field 'dbc_file' must be a string or null.")

    # Accept both the new message-grouped schema (v2+) and the legacy flat
    # "nodes" schema (v1) so older canvas files keep working.
    if "messages" in payload:
        nodes = _flatten_messages(payload.get("messages", []))
    else:
        raw_nodes = payload.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise ValueError("Canvas JSON field 'nodes' must be a list.")
        nodes = [_normalize_node(node, idx) for idx, node in enumerate(raw_nodes, start=1)]

    custom_nodes = payload.get("custom_nodes", [])
    links = payload.get("links", [])

    return {
        "dbc_file": dbc_file,
        "nodes": nodes,
        "custom_nodes": custom_nodes,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def _build_messages_from_canvas(dbc_file: str | None, canvas_nodes: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for node in canvas_nodes:
        message_name = node.get("message", "")
        if not message_name:
            continue
        if message_name not in groups:
            order.append(message_name)
            groups[message_name] = []
        groups[message_name].append(node)

    dbc_messages = _load_dbc_messages(dbc_file)

    messages: list[dict] = []
    for name in order:
        canvas_items = groups[name]
        db_message = dbc_messages.get(name)

        if db_message is not None:
            message_entry = _message_attrs_from_dbc(db_message)
            db_signals = {s.name: s for s in db_message.signals}
        else:
            first = canvas_items[0]
            frame_id = int(first.get("meta", {}).get("frame_id", first.get("frame_id", 0)))
            message_entry = {
                "name": name,
                "frame_id": frame_id,
                "frame_id_hex": f"0x{frame_id:X}",
            }
            db_signals = {}

        signals_out: list[dict] = []
        for node in canvas_items:
            signal_name = node.get("signal", "")
            db_signal = db_signals.get(signal_name)
            if db_signal is not None:
                signal_entry = _signal_attrs_from_dbc(db_signal)
            else:
                meta = node.get("meta", {})
                signal_entry = {
                    "name": signal_name,
                    "start_bit": int(meta.get("start_bit", node.get("start_bit", 0))),
                    "length": int(meta.get("length", node.get("length", 0))),
                }
            signal_entry["canvas"] = _canvas_info_for_node(node, dbc_messages)
            signals_out.append(signal_entry)

        message_entry["signals"] = signals_out
        messages.append(message_entry)

    return messages


def _build_messages_and_custom_from_canvas(dbc_file: str | None, canvas_nodes: list[dict]) -> tuple[list[dict], list[dict]]:
    messages = _build_messages_from_canvas(dbc_file, canvas_nodes)
    custom_nodes = []
    for node in canvas_nodes:
        if node.get("type") == "custom":
            custom_nodes.append(node)
    return messages, custom_nodes


def _load_dbc_messages(dbc_file: str | None) -> dict:
    if not dbc_file:
        return {}
    path = Path(dbc_file)
    if not path.exists():
        return {}
    try:
        import cantools  # local import to avoid hard dependency at module import time
    except ImportError:
        return {}
    try:
        database = cantools.database.load_file(str(path))
    except Exception:
        return {}
    return {message.name: message for message in getattr(database, "messages", [])}


def _message_attrs_from_dbc(message) -> dict:
    signal_groups = getattr(message, "signal_groups", None)
    if signal_groups:
        signal_groups = [
            {"name": sg.name, "repetitions": getattr(sg, "repetitions", None),
             "signal_names": list(getattr(sg, "signal_names", []))}
            for sg in signal_groups
        ]
    else:
        signal_groups = []

    data: dict = {
        "name": message.name,
        "frame_id": int(message.frame_id),
        "frame_id_hex": f"0x{int(message.frame_id):X}",
        "length": _safe_int(getattr(message, "length", None)),
        "is_extended_frame": bool(getattr(message, "is_extended_frame", False)),
        "is_fd": bool(getattr(message, "is_fd", False)),
        "is_multiplexed": bool(getattr(message, "is_multiplexed", False)),
        "is_container": bool(getattr(message, "is_container", False)),
        "bus_name": getattr(message, "bus_name", None),
        "protocol": getattr(message, "protocol", None),
        "header_byte_order": getattr(message, "header_byte_order", None),
        "header_id": getattr(message, "header_id", None),
        "senders": [str(s) for s in (getattr(message, "senders", None) or [])],
        "receivers": sorted(str(r) for r in (getattr(message, "receivers", None) or [])),
        "cycle_time_ms": _safe_int(getattr(message, "cycle_time", None)),
        "send_type": getattr(message, "send_type", None),
        "signal_groups": signal_groups,
        "unused_bit_pattern": _safe_int(getattr(message, "unused_bit_pattern", None)),
        "comment": getattr(message, "comment", None),
        "comments": _normalize_comments(getattr(message, "comments", None)),
    }
    return data


def _signal_attrs_from_dbc(signal) -> dict:
    choices = getattr(signal, "choices", None) or None
    if choices:
        choices = {str(k): str(v) for k, v in choices.items()}

    mux_ids = getattr(signal, "multiplexer_ids", None)
    if mux_ids is not None:
        mux_ids = list(mux_ids)

    conversion = getattr(signal, "conversion", None)
    conversion_info = None
    if conversion is not None:
        conversion_info = {
            "type": type(conversion).__name__,
            "scale": _to_number(getattr(conversion, "scale", None)),
            "offset": _to_number(getattr(conversion, "offset", None)),
            "is_float": bool(getattr(conversion, "is_float", False)),
        }

    start_bit_msb = int(getattr(signal, "start", 0))
    byte_order = getattr(signal, "byte_order", "big_endian")
    sig_length = int(getattr(signal, "length", 0))

    data: dict = {
        "name": signal.name,
        "start_bit": start_bit_msb,
        "start_bit_lsb": _msb_to_lsb(start_bit_msb, sig_length, byte_order),
        "length": sig_length,
        "byte_order": byte_order,
        "is_signed": bool(getattr(signal, "is_signed", False)),
        "is_float": bool(getattr(signal, "is_float", False)),
        "factor": _to_number(getattr(signal, "scale", 1)),
        "offset": _to_number(getattr(signal, "offset", 0)),
        "minimum": _to_number(getattr(signal, "minimum", None)),
        "maximum": _to_number(getattr(signal, "maximum", None)),
        "unit": getattr(signal, "unit", None),
        "initial": _to_number(getattr(signal, "initial", None)),
        "raw_initial": _to_number(getattr(signal, "raw_initial", None)),
        "invalid": _to_number(getattr(signal, "invalid", None)),
        "raw_invalid": _to_number(getattr(signal, "raw_invalid", None)),
        "receivers": [str(r) for r in (getattr(signal, "receivers", None) or [])],
        "is_multiplexer": bool(getattr(signal, "is_multiplexer", False)),
        "multiplexer_ids": mux_ids,
        "multiplexer_signal": getattr(signal, "multiplexer_signal", None),
        "mux_indicator": getattr(signal, "mux_indicator", None),
        "spn": _safe_int(getattr(signal, "spn", None)),
        "choices": choices,
        "conversion": conversion_info,
        "comment": getattr(signal, "comment", None),
        "comments": _normalize_comments(getattr(signal, "comments", None)),
    }
    return data


def _canvas_info_for_node(node: dict, dbc_messages: dict) -> dict:
    info: dict = {
        "id": str(node.get("id", "") or ""),
        "node": node.get("node", ""),
        "direction": node.get("direction", ""),
        "x": float(node.get("x", 0)),
        "y": float(node.get("y", 0)),
    }
    condition = node.get("condition")
    if condition:
        info["condition"] = _enrich_condition(condition, dbc_messages)
    return info


def _enrich_condition(condition: dict, dbc_messages: dict) -> dict:
    """Enrich a condition dict with full DBC attributes of the source signal."""
    result = dict(condition)

    source_message_name = condition.get("source_message", "")
    source_signal_name = condition.get("source_signal", "")

    db_message = dbc_messages.get(source_message_name)
    if db_message is not None:
        # Add source message info
        result["source_frame_id"] = int(db_message.frame_id)
        result["source_frame_id_hex"] = f"0x{int(db_message.frame_id):X}"
        result["source_message_length"] = _safe_int(getattr(db_message, "length", None))
        result["source_is_extended_frame"] = bool(getattr(db_message, "is_extended_frame", False))
        result["source_is_fd"] = bool(getattr(db_message, "is_fd", False))
        result["source_senders"] = [str(s) for s in (getattr(db_message, "senders", None) or [])]
        result["source_cycle_time_ms"] = _safe_int(getattr(db_message, "cycle_time", None))
        result["source_send_type"] = getattr(db_message, "send_type", None)
        result["source_comment"] = getattr(db_message, "comment", None)

        # Add full source signal info
        db_signal = None
        for sig in db_message.signals:
            if sig.name == source_signal_name:
                db_signal = sig
                break

        if db_signal is not None:
            result["source_signal_info"] = _signal_attrs_from_dbc(db_signal)
        else:
            result["source_signal_info"] = {
                "name": source_signal_name,
                "start_bit": int(condition.get("start_bit", 0)),
                "length": int(condition.get("length", 0)),
            }
    else:
        # No DBC data available; include whatever we have from the condition
        result["source_signal_info"] = {
            "name": source_signal_name,
            "start_bit": int(condition.get("start_bit", 0)),
            "length": int(condition.get("length", 0)),
        }

    return result


def _msb_to_lsb(start_bit_msb: int, length: int, byte_order: str) -> int:
    """Convert DBC MSB start bit to LSB start bit for Motorola (big-endian) signals.

    In the DBC format, the start_bit for Motorola signals is the MSB position.
    CANdb++ and most code generators display/expect the LSB position.
    For Intel (little-endian) signals, start_bit is already the LSB.
    """
    if byte_order != "big_endian" or length <= 0:
        return start_bit_msb

    s_byte = start_bit_msb // 8
    s_bit = start_bit_msb % 8
    bits_in_first_byte = s_bit + 1

    if length <= bits_in_first_byte:
        # Signal fits within one byte
        return start_bit_msb - length + 1

    remaining = length - bits_in_first_byte
    full_bytes = remaining // 8
    last_bits = remaining % 8

    if last_bits == 0:
        # LSB is bit 0 of the last full byte
        lsb_byte = s_byte + 1 + full_bytes - 1
        return lsb_byte * 8
    else:
        lsb_byte = s_byte + 1 + full_bytes
        return lsb_byte * 8 + (8 - last_bits)


def _to_number(value):
    if isinstance(value, Decimal):
        try:
            return float(value)
        except (TypeError, ValueError):
            return str(value)
    return value


def _normalize_comments(comments):
    """Convert cantools comments dict to a plain dict with string keys.

    cantools uses None as the key for the default comment; we map it
    to the empty string so the JSON output is not confusing.
    """
    if comments is None:
        return None
    if isinstance(comments, dict):
        out = {}
        for k, v in comments.items():
            key = "" if k is None else str(k)
            out[key] = str(v)
        return out
    return str(comments)


def _safe_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _json_default(value):
    if isinstance(value, Decimal):
        return float(value)
    # Handle cantools named-value objects (NamedSignalValue, etc.)
    if hasattr(value, "__str__"):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# Load helpers (schema v2 → flat nodes expected by the canvas)
# ---------------------------------------------------------------------------

def _flatten_messages(messages: list) -> list[dict]:
    if not isinstance(messages, list):
        raise ValueError("Canvas JSON field 'messages' must be a list.")

    flat: list[dict] = []
    for msg_idx, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            raise ValueError(f"Message #{msg_idx} must be an object.")
        msg_name = message.get("name")
        if not isinstance(msg_name, str) or not msg_name:
            raise ValueError(f"Message #{msg_idx} field 'name' must be a non-empty string.")
        frame_id = int(message.get("frame_id", 0))
        signals = message.get("signals", [])
        if not isinstance(signals, list):
            raise ValueError(f"Message '{msg_name}' field 'signals' must be a list.")

        for sig_idx, signal in enumerate(signals, start=1):
            if not isinstance(signal, dict):
                raise ValueError(f"Signal #{sig_idx} of '{msg_name}' must be an object.")
            signal_name = signal.get("name")
            if not isinstance(signal_name, str) or not signal_name:
                raise ValueError(
                    f"Signal #{sig_idx} of '{msg_name}' field 'name' must be a non-empty string."
                )
            canvas = signal.get("canvas") or {}
            if not isinstance(canvas, dict):
                raise ValueError(
                    f"Signal '{signal_name}' of '{msg_name}' field 'canvas' must be an object."
                )

            node: dict = {
                "id": str(canvas.get("id") or ""),
                "node": canvas.get("node", ""),
                "direction": canvas.get("direction", "rx"),
                "message": msg_name,
                "frame_id": frame_id,
                "signal": signal_name,
                "start_bit": int(signal.get("start_bit", 0)),
                "length": int(signal.get("length", 0)),
                "x": float(canvas.get("x", 0)),
                "y": float(canvas.get("y", 0)),
            }
            condition = canvas.get("condition")
            if condition is not None:
                node["condition"] = _normalize_condition(condition, sig_idx)
            flat.append(node)
    return flat


def _normalize_node(node: object, index: int) -> dict:
    """Legacy v1 flat-node normalizer (kept for backward compatibility)."""
    if not isinstance(node, dict):
        raise ValueError(f"Node #{index} must be an object.")

    meta = node.get("meta", {})
    if not isinstance(meta, dict):
        raise ValueError(f"Node #{index} field 'meta' must be an object.")

    required_fields = ["node", "message", "signal", "direction"]
    normalized: dict = {}
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
        raise ValueError(f"Condition #{index} must be an object.")

    required_fields = [
        "source_node",
        "source_message",
        "source_signal",
        "operator",
        "value",
    ]
    normalized: dict = {}
    for field_name in required_fields:
        value = condition.get(field_name)
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"Condition #{index} field '{field_name}' must be a non-empty string."
            )
        normalized[field_name] = value
    shown = condition.get("shown")
    if shown is not None:
        normalized["shown"] = bool(shown)
    source_x = condition.get("source_x")
    if source_x is not None:
        normalized["source_x"] = float(source_x)
    source_y = condition.get("source_y")
    if source_y is not None:
        normalized["source_y"] = float(source_y)
    return normalized


# ---------------------------------------------------------------------------
# Custom nodes distribution file support
# ---------------------------------------------------------------------------

CUSTOM_NODES_SCHEMA_VERSION = 1


def export_custom_nodes_json(file_path: str, custom_nodes: list[dict]) -> None:
    """Export custom mapping nodes to a standalone distribution file."""
    payload = {
        "version": CUSTOM_NODES_SCHEMA_VERSION,
        "custom_nodes": custom_nodes,
    }
    Path(file_path).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def load_custom_nodes_json(file_path: str) -> list[dict]:
    """Load custom mapping nodes from a distribution file."""
    payload = json.loads(Path(file_path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Custom nodes file root must be an object.")
    version = payload.get("version", 1)
    if not isinstance(version, int) or version < 1:
        raise ValueError(f"Unsupported custom nodes file version: {version}")
    custom_nodes = payload.get("custom_nodes", [])
    if not isinstance(custom_nodes, list):
        raise ValueError("Custom nodes file field 'custom_nodes' must be a list.")
    return custom_nodes


def custom_node_to_canvas_dict(node: dict) -> dict:
    """Convert a custom node from distribution/JSON format to canvas payload."""
    mapping_table = node.get("mapping_table", [])
    return {
        "id": node.get("id", ""),
        "type": "custom",
        "node": "CUSTOM",
        "direction": "custom",
        "message": "",
        "frame_id": 0,
        "signal": node.get("name", ""),
        "start_bit": 0,
        "length": 0,
        "byte_order": "big_endian",
        "target_variable": node.get("target_variable", ""),
        "description": node.get("description", ""),
        "source_message": node.get("source_message", ""),
        "source_signal": node.get("source_signal", ""),
        "mapping_table": [{"dbc_value": m.get("dbc_value", ""), "radar_value": m.get("radar_value", "")} for m in mapping_table],
    }


def canvas_dict_to_custom_node(node: dict) -> dict:
    """Convert a canvas custom node dict to distribution/JSON format."""
    mapping_table = node.get("mapping_table", [])
    return {
        "id": node.get("id", ""),
        "name": node.get("signal", ""),
        "target_variable": node.get("target_variable", ""),
        "description": node.get("description", ""),
        "source_message": node.get("source_message", ""),
        "source_signal": node.get("source_signal", ""),
        "mapping_table": [{"dbc_value": m.get("dbc_value", ""), "radar_value": m.get("radar_value", "")} for m in mapping_table],
    }
