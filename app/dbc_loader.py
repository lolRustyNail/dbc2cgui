from __future__ import annotations

from pathlib import Path

from app.models import DbcDocument, DbcMessage, DbcNodeMessages, DbcSignal


def load_dbc_document(file_path: str) -> DbcDocument:
    try:
        import cantools
    except ImportError as exc:
        raise RuntimeError("Missing dependency: cantools") from exc

    database = cantools.database.load_file(file_path)
    node_names = _collect_node_names(database)
    node_messages: list[DbcNodeMessages] = []

    for node_name in node_names:
        tx_messages: list[DbcMessage] = []
        rx_messages: list[DbcMessage] = []

        for message in database.messages:
            if node_name in (message.senders or []):
                tx_messages.append(
                    DbcMessage(
                        name=message.name,
                        frame_id=message.frame_id,
                        senders=list(message.senders or []),
                        signals=[
                            DbcSignal(
                                name=signal.name,
                                start_bit=signal.start,
                                length=signal.length,
                                byte_order=getattr(signal, "byte_order", "big_endian"),
                                receivers=list(signal.receivers or []),
                            )
                            for signal in message.signals
                        ],
                    )
                )

            rx_signals = [
                DbcSignal(
                    name=signal.name,
                    start_bit=signal.start,
                    length=signal.length,
                    byte_order=getattr(signal, "byte_order", "big_endian"),
                    receivers=list(signal.receivers or []),
                )
                for signal in message.signals
                if node_name in (signal.receivers or [])
            ]
            if rx_signals:
                rx_messages.append(
                    DbcMessage(
                        name=message.name,
                        frame_id=message.frame_id,
                        senders=list(message.senders or []),
                        signals=rx_signals,
                    )
                )

        node_messages.append(
            DbcNodeMessages(
                name=node_name,
                tx_messages=sorted(tx_messages, key=lambda item: item.name.lower()),
                rx_messages=sorted(rx_messages, key=lambda item: item.name.lower()),
            )
        )

    return DbcDocument(file_path=str(Path(file_path)), nodes=node_messages)


def _collect_node_names(database) -> list[str]:
    names = {node.name for node in getattr(database, "nodes", [])}

    for message in database.messages:
        names.update(message.senders or [])
        for signal in message.signals:
            names.update(signal.receivers or [])

    if not names:
        names.add("Unassigned")

    return sorted(names, key=str.lower)
