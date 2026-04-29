from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class MappingEntry:
    dbc_value: str
    radar_value: str


@dataclass(slots=True)
class CustomNode:
    id: str
    name: str
    target_variable: str
    description: str = ""
    source_message: str = ""
    source_signal: str = ""
    mapping_table: list[MappingEntry] = field(default_factory=list)


@dataclass(slots=True)
class DbcSignal:
    name: str
    start_bit: int
    length: int
    byte_order: str = "big_endian"
    receivers: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DbcMessage:
    name: str
    frame_id: int
    signals: list[DbcSignal] = field(default_factory=list)
    senders: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DbcNodeMessages:
    name: str
    tx_messages: list[DbcMessage] = field(default_factory=list)
    rx_messages: list[DbcMessage] = field(default_factory=list)


@dataclass(slots=True)
class DbcDocument:
    file_path: str
    nodes: list[DbcNodeMessages] = field(default_factory=list)
