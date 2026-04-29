from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QMenu,
    QStyle,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QTreeWidget,
    QTreeWidgetItem,
)

from app.models import CustomNode, DbcDocument, DbcMessage, DbcNodeMessages, DbcSignal


class TreeFilterHighlightDelegate(QStyledItemDelegate):
    def __init__(self, tree_widget: "DbcTreeWidget"):
        super().__init__(tree_widget)
        self._tree_widget = tree_widget

    def paint(self, painter, option, index) -> None:
        paint_option = QStyleOptionViewItem(option)
        self.initStyleOption(paint_option, index)

        filter_text = self._tree_widget.filter_text
        text = paint_option.text
        match_start = text.lower().find(filter_text) if filter_text else -1
        if match_start < 0:
            super().paint(painter, option, index)
            return

        style = paint_option.widget.style() if paint_option.widget is not None else self._tree_widget.style()
        paint_option.text = ""
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, paint_option, painter, paint_option.widget)

        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText,
            paint_option,
            paint_option.widget,
        )
        if not text_rect.isValid():
            text_rect = paint_option.rect.adjusted(4, 0, -4, 0)

        prefix = text[:match_start]
        matched = text[match_start:match_start + len(filter_text)]
        suffix = text[match_start + len(filter_text):]
        metrics = paint_option.fontMetrics
        baseline = text_rect.y() + (text_rect.height() + metrics.ascent() - metrics.descent()) // 2
        prefix_width = metrics.horizontalAdvance(prefix)
        match_width = metrics.horizontalAdvance(matched)
        current_x = text_rect.x()

        painter.save()
        painter.setClipRect(text_rect)
        painter.setFont(paint_option.font)

        text_color_role = (
            QPalette.ColorRole.HighlightedText
            if paint_option.state & QStyle.StateFlag.State_Selected
            else QPalette.ColorRole.Text
        )
        text_color = paint_option.palette.color(text_color_role)

        painter.setPen(text_color)
        painter.drawText(current_x, baseline, prefix)
        current_x += prefix_width

        highlight_color = QColor("#fde68a")
        if paint_option.state & QStyle.StateFlag.State_Selected:
            highlight_color = QColor("#60a5fa")
        highlight_color.setAlpha(170)
        painter.fillRect(current_x, text_rect.y() + 2, match_width, text_rect.height() - 4, highlight_color)

        painter.setPen(QColor("#0f172a") if not paint_option.state & QStyle.StateFlag.State_Selected else QColor("#eff6ff"))
        painter.drawText(current_x, baseline, matched)
        current_x += match_width

        painter.setPen(text_color)
        painter.drawText(current_x, baseline, suffix)
        painter.restore()


class DbcTreeWidget(QTreeWidget):
    MIME_TYPE = "application/x-dbc-signal"
    ROLE_KIND = Qt.ItemDataRole.UserRole
    ROLE_PAYLOAD = Qt.ItemDataRole.UserRole + 1
    signal_activated = Signal(dict)
    message_activated = Signal(list)
    create_custom_node_requested = Signal()
    edit_custom_node_requested = Signal(str)
    delete_custom_node_requested = Signal(str)

    def __init__(self):
        super().__init__()
        self._filter_text = ""
        self.setColumnCount(1)
        self.setHeaderLabel("DBC")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setItemDelegate(TreeFilterHighlightDelegate(self))
        self.itemDoubleClicked.connect(self._handle_item_activation)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self._custom_root = QTreeWidgetItem(["Custom Nodes"])
        self._custom_root.setData(0, self.ROLE_KIND, "custom_root")
        self.addTopLevelItem(self._custom_root)
        self._custom_root.setExpanded(True)

    @property
    def filter_text(self) -> str:
        return self._filter_text

    def load_document(self, document: DbcDocument, custom_nodes: list[CustomNode] | None = None) -> None:
        self.clear()
        root_item = QTreeWidgetItem([Path(document.file_path).name])
        root_item.setData(0, self.ROLE_KIND, "document")
        self.addTopLevelItem(root_item)

        for node in document.nodes:
            root_item.addChild(self._build_node_item(node))

        root_item.setExpanded(True)
        for index in range(root_item.childCount()):
            root_item.child(index).setExpanded(True)

        self._custom_root = QTreeWidgetItem(["Custom Nodes"])
        self._custom_root.setData(0, self.ROLE_KIND, "custom_root")
        self.addTopLevelItem(self._custom_root)
        self._custom_root.setExpanded(True)

        if custom_nodes:
            for cn in custom_nodes:
                self.add_custom_node(cn)

        self.apply_filter(self._filter_text)

    def apply_filter(self, text: str) -> None:
        self._filter_text = text.strip().lower()

        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            self._apply_filter_to_item(item, self._filter_text)

    def _apply_filter_to_item(self, item: QTreeWidgetItem, filter_text: str) -> bool:
        kind = item.data(0, self.ROLE_KIND)
        if kind == "custom_root":
            item.setHidden(False)
            for index in range(item.childCount()):
                child = item.child(index)
                self._apply_filter_to_item(child, filter_text)
            return True

        own_match = not filter_text or filter_text in item.text(0).lower()
        child_match = False

        for index in range(item.childCount()):
            child = item.child(index)
            child_match = self._apply_filter_to_item(child, filter_text) or child_match

        should_show = own_match or child_match
        item.setHidden(not should_show)

        if filter_text and child_match:
            item.setExpanded(True)
        elif not filter_text and kind in {"document", "node"}:
            item.setExpanded(True)

        return should_show

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData:
        for item in items:
            payload = item.data(0, self.ROLE_PAYLOAD)
            if payload:
                mime_data = QMimeData()
                mime_data.setData(self.MIME_TYPE, json.dumps(payload).encode("utf-8"))
                return mime_data
        return QMimeData()

    def supportedDragActions(self) -> Qt.DropAction:
        return Qt.DropAction.CopyAction

    def _context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        menu = QMenu(self)
        if item is None or item.data(0, self.ROLE_KIND) == "custom_root":
            create_action = menu.addAction("New Custom Node")
            chosen = menu.exec(self.viewport().mapToGlobal(pos))
            if chosen == create_action:
                self.create_custom_node_requested.emit()
            return
        if item.data(0, self.ROLE_KIND) == "custom":
            edit_action = menu.addAction("Edit")
            delete_action = menu.addAction("Delete")
            chosen = menu.exec(self.viewport().mapToGlobal(pos))
            payload = item.data(0, self.ROLE_PAYLOAD)
            node_id = payload.get("id", "") if payload else ""
            if chosen == edit_action:
                self.edit_custom_node_requested.emit(node_id)
            elif chosen == delete_action:
                self.delete_custom_node_requested.emit(node_id)

    def add_custom_node(self, node: CustomNode) -> None:
        payload = self._custom_node_to_payload(node)
        item = QTreeWidgetItem([node.name])
        item.setData(0, self.ROLE_KIND, "custom")
        item.setData(0, self.ROLE_PAYLOAD, payload)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        self._custom_root.addChild(item)
        self._custom_root.setExpanded(True)

    def update_custom_node(self, node: CustomNode) -> None:
        for i in range(self._custom_root.childCount()):
            child = self._custom_root.child(i)
            payload = child.data(0, self.ROLE_PAYLOAD)
            if payload and payload.get("id") == node.id:
                child.setText(0, node.name)
                child.setData(0, self.ROLE_PAYLOAD, self._custom_node_to_payload(node))
                break

    def remove_custom_node(self, node_id: str) -> None:
        for i in range(self._custom_root.childCount()):
            child = self._custom_root.child(i)
            payload = child.data(0, self.ROLE_PAYLOAD)
            if payload and payload.get("id") == node_id:
                self._custom_root.removeChild(child)
                break

    def load_custom_nodes(self, nodes: list[CustomNode]) -> None:
        for node in nodes:
            self.add_custom_node(node)

    def _custom_node_to_payload(self, node: CustomNode) -> dict:
        return {
            "id": node.id,
            "type": "custom",
            "node": "CUSTOM",
            "direction": "custom",
            "message": "",
            "frame_id": 0,
            "signal": node.name,
            "start_bit": 0,
            "length": 0,
            "byte_order": "big_endian",
            "target_variable": node.target_variable,
            "description": node.description,
            "source_message": node.source_message,
            "source_signal": node.source_signal,
            "mapping_table": [{"dbc_value": m.dbc_value, "radar_value": m.radar_value} for m in node.mapping_table],
        }

    def _handle_item_activation(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        kind = item.data(0, self.ROLE_KIND)
        if kind == "message":
            payloads = []
            for index in range(item.childCount()):
                payload = item.child(index).data(0, self.ROLE_PAYLOAD)
                if payload:
                    payloads.append(dict(payload))
            if payloads:
                self.message_activated.emit(payloads)
            return

        payload = item.data(0, self.ROLE_PAYLOAD)
        if payload:
            self.signal_activated.emit(dict(payload))

    def _build_node_item(self, node: DbcNodeMessages) -> QTreeWidgetItem:
        node_item = QTreeWidgetItem([node.name])
        node_item.setData(0, self.ROLE_KIND, "node")
        node_item.addChild(self._build_direction_item(node.name, "tx", node.tx_messages))
        node_item.addChild(self._build_direction_item(node.name, "rx", node.rx_messages))
        return node_item

    def _build_direction_item(
        self,
        node_name: str,
        direction: str,
        messages: list[DbcMessage],
    ) -> QTreeWidgetItem:
        label = "Tx Messages" if direction == "tx" else "Rx Messages"
        direction_item = QTreeWidgetItem([f"{label} ({len(messages)})"])
        direction_item.setData(0, self.ROLE_KIND, direction)

        for message in messages:
            direction_item.addChild(self._build_message_item(node_name, direction, message))

        return direction_item

    def _build_message_item(
        self,
        node_name: str,
        direction: str,
        message: DbcMessage,
    ) -> QTreeWidgetItem:
        frame_hex = f"0x{message.frame_id:X}"
        message_item = QTreeWidgetItem([f"{message.name} [{frame_hex}]"])
        message_item.setData(0, self.ROLE_KIND, "message")

        for signal in message.signals:
            message_item.addChild(self._build_signal_item(node_name, direction, message, signal))

        return message_item

    def _build_signal_item(
        self,
        node_name: str,
        direction: str,
        message: DbcMessage,
        signal: DbcSignal,
    ) -> QTreeWidgetItem:
        signal_item = QTreeWidgetItem([signal.name])
        signal_item.setData(0, self.ROLE_KIND, "signal")
        signal_item.setData(
            0,
            self.ROLE_PAYLOAD,
            {
                "node": node_name,
                "direction": direction,
                "message": message.name,
                "frame_id": message.frame_id,
                "signal": signal.name,
                "start_bit": signal.start_bit,
                "length": signal.length,
                "byte_order": signal.byte_order,
            },
        )
        signal_item.setFlags(signal_item.flags() | Qt.ItemFlag.ItemIsDragEnabled)
        return signal_item
