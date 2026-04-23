from __future__ import annotations

import uuid

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSceneMouseEvent,
    QGraphicsTextItem,
    QMessageBox,
    QStyleOptionGraphicsItem,
    QWidget,
)


class SignalNodeItem(QGraphicsRectItem):
    GRID_SIZE = 24
    WIDTH = 240
    HEIGHT = 162

    def __init__(self, signal_data: dict):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.signal_data = dict(signal_data)
        self.node_id = signal_data.get("id") or uuid.uuid4().hex
        self._title_item: QGraphicsTextItem | None = None
        self._detail_item: QGraphicsTextItem | None = None
        self._condition_item: QGraphicsTextItem | None = None
        self._hint_item: QGraphicsTextItem | None = None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self._build_text()
        self.setToolTip(self._dialog_text())

    def _build_text(self) -> None:
        title_item = QGraphicsTextItem(self.signal_data["signal"], self)
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_item.setFont(title_font)
        title_item.setDefaultTextColor(QColor("#0f172a"))
        title_item.setTextWidth(self.WIDTH - 96)
        title_item.setPos(14, 10)
        self._title_item = title_item

        detail_lines = [
            f"Message: {self.signal_data['message']}",
            f"Node: {self.signal_data['node']}",
            f"Start Bit: {self._display_start_bit()}  Length: {self.signal_data['length']}",
        ]
        detail_item = QGraphicsTextItem("\n".join(detail_lines), self)
        detail_item.setDefaultTextColor(QColor("#334155"))
        detail_item.setTextWidth(self.WIDTH - 28)
        detail_item.setPos(14, 46)
        self._detail_item = detail_item

        condition_item = QGraphicsTextItem(self._condition_summary(), self)
        condition_font = QFont()
        condition_font.setPointSize(8)
        condition_item.setFont(condition_font)
        condition_item.setDefaultTextColor(QColor("#475569"))
        condition_item.setTextWidth(self.WIDTH - 28)
        condition_item.setPos(14, 100)
        self._condition_item = condition_item

        hint_item = QGraphicsTextItem("Double-click for details", self)
        hint_font = QFont()
        hint_font.setPointSize(8)
        hint_item.setFont(hint_font)
        hint_item.setDefaultTextColor(QColor("#64748b"))
        hint_item.setPos(14, 140)
        self._hint_item = hint_item

    @staticmethod
    def _msb_to_lsb(start_bit_msb: int, length: int, byte_order: str) -> int:
        if byte_order != "big_endian" or length <= 0:
            return start_bit_msb
        s_byte = start_bit_msb // 8
        s_bit = start_bit_msb % 8
        bits_in_first_byte = s_bit + 1
        if length <= bits_in_first_byte:
            return start_bit_msb - length + 1
        remaining = length - bits_in_first_byte
        full_bytes = remaining // 8
        last_bits = remaining % 8
        if last_bits == 0:
            lsb_byte = s_byte + 1 + full_bytes - 1
            return lsb_byte * 8
        else:
            lsb_byte = s_byte + 1 + full_bytes
            return lsb_byte * 8 + (8 - last_bits)

    def _display_start_bit(self) -> str:
        start = self.signal_data.get("start_bit", 0)
        length = self.signal_data.get("length", 0)
        byte_order = self.signal_data.get("byte_order", "big_endian")
        lsb = self._msb_to_lsb(start, length, byte_order)
        order_label = "BE" if byte_order == "big_endian" else "LE"
        return f"{lsb} ({order_label})"

    def _condition_summary(self) -> str:
        if self.is_reference():
            return "Reference source"

        condition = self.signal_data.get("condition")
        if not condition:
            return "Condition: none"

        source_message = condition.get("source_message", "")
        source_signal = condition.get("source_signal", "")
        source_text = source_signal if not source_message else f"{source_message}.{source_signal}"
        return f"Condition: {source_text} {condition.get('operator', '==')} {condition.get('value', '')}"

    def _direction_palette(self) -> tuple[QColor, QColor]:
        if self.is_reference():
            return QColor("#e2e8f0"), QColor("#475569")
        direction = self.signal_data["direction"].lower()
        if direction == "tx":
            return QColor("#dbeafe"), QColor("#1d4ed8")
        return QColor("#dcfce7"), QColor("#15803d")

    def _badge_text(self) -> str:
        if self.is_reference():
            return "REF"
        return self.signal_data["direction"].upper()

    def _dialog_text(self) -> str:
        lines = [
            f"Signal: {self.signal_data['signal']}",
            f"Direction: {self.signal_data['direction'].upper()}",
            f"Node: {self.signal_data['node']}",
            f"Message: {self.signal_data['message']}",
            f"Frame ID: {self.signal_data['frame_id']} (0x{self.signal_data['frame_id']:X})",
            f"Start Bit: {self._display_start_bit()}",
            f"Length: {self.signal_data['length']}",
        ]

        condition = self.signal_data.get("condition")
        if condition:
            lines.extend(
                [
                    "",
                    "Receive Condition:",
                    f"  Source Node: {condition.get('source_node', '')}",
                    f"  Source Message: {condition.get('source_message', '')}",
                    f"  Source Signal: {condition.get('source_signal', '')}",
                    f"  Expression: {condition.get('operator', '==')} {condition.get('value', '')}",
                ]
            )

        return "\n".join(lines)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        del option
        del widget
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        border_color = QColor("#2563eb") if self.isSelected() else QColor("#475569")
        fill_color = QColor("#eff6ff") if self.isSelected() else QColor("#f8fafc")
        header_color = QColor("#e2e8f0") if self.isSelected() else QColor("#f1f5f9")
        badge_fill, badge_text = self._direction_palette()

        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(QRectF(0, 0, self.WIDTH, self.HEIGHT), 10, 10)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(header_color))
        painter.drawRoundedRect(QRectF(1, 1, self.WIDTH - 2, 34), 10, 10)
        painter.drawRect(QRectF(1, 18, self.WIDTH - 2, 16))

        badge_rect = QRectF(self.WIDTH - 58, 10, 42, 20)
        painter.setBrush(QBrush(badge_fill))
        painter.drawRoundedRect(badge_rect, 10, 10)

        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.setPen(QPen(badge_text))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._badge_text())

        painter.setPen(QPen(QColor("#cbd5e1"), 1))
        painter.drawLine(12, 134, self.WIDTH - 12, 134)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.show_details()
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self.snap_to_grid()

    def show_details(self) -> None:
        QMessageBox.information(
            QApplication.activeWindow(),
            f"Signal Details - {self.signal_data['signal']}",
            self._dialog_text(),
        )

    def has_condition(self) -> bool:
        return bool(self.signal_data.get("condition"))

    def is_reference(self) -> bool:
        return bool(self.signal_data.get("reference"))

    def set_condition(self, condition: dict | None) -> None:
        if condition:
            self.signal_data["condition"] = dict(condition)
        else:
            self.signal_data.pop("condition", None)

        if self._condition_item is not None:
            self._condition_item.setPlainText(self._condition_summary())
        self.setToolTip(self._dialog_text())

    def snap_to_grid(self) -> None:
        position = self.pos()
        self.setPos(self.snap_value(position.x()), self.snap_value(position.y()))

    @classmethod
    def snap_value(cls, value: float) -> float:
        return round(value / cls.GRID_SIZE) * cls.GRID_SIZE

    def to_node_payload(self, include_id: bool = True) -> dict:
        payload = {
            "node": self.signal_data["node"],
            "direction": self.signal_data["direction"],
            "message": self.signal_data["message"],
            "frame_id": self.signal_data["frame_id"],
            "signal": self.signal_data["signal"],
            "start_bit": self.signal_data["start_bit"],
            "length": self.signal_data["length"],
            "byte_order": self.signal_data.get("byte_order", "big_endian"),
        }
        if include_id:
            payload["id"] = self.node_id
        if self.has_condition():
            payload["condition"] = dict(self.signal_data["condition"])
        if self.is_reference():
            payload["reference"] = True
        return payload

    def to_export_dict(self) -> dict:
        scene_position = self.scenePos()
        export_data = {
            "id": self.node_id,
            "type": "signal",
            "node": self.signal_data["node"],
            "message": self.signal_data["message"],
            "signal": self.signal_data["signal"],
            "direction": self.signal_data["direction"],
            "x": round(scene_position.x(), 2),
            "y": round(scene_position.y(), 2),
            "meta": {
                "frame_id": self.signal_data["frame_id"],
                "start_bit": self.signal_data["start_bit"],
                "length": self.signal_data["length"],
                "byte_order": self.signal_data.get("byte_order", "big_endian"),
            },
        }
        if self.has_condition():
            export_data["condition"] = dict(self.signal_data["condition"])
        return export_data
