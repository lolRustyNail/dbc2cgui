from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsSceneMouseEvent, QGraphicsSimpleTextItem


class ConditionLinkItem(QGraphicsPathItem):
    def __init__(self, source_item, target_item, condition: dict, on_edit=None):
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.condition = dict(condition)
        self._on_edit = on_edit
        self._default_color = QColor("#10b981")
        self._selected_color = QColor("#059669")
        self._label_item = QGraphicsSimpleTextItem(self)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(-1)
        self._label_item.setText(f"{self.condition.get('operator', '==')} {self.condition.get('value', '')}")
        self.update_path()

    def update_path(self) -> None:
        source_rect = self.source_item.sceneBoundingRect()
        target_rect = self.target_item.sceneBoundingRect()

        source_center = source_rect.center()
        target_center = target_rect.center()

        if source_center.x() <= target_center.x():
            start = QPointF(source_rect.right(), source_center.y())
            end = QPointF(target_rect.left(), target_center.y())
            control_delta = max(80.0, abs(end.x() - start.x()) * 0.35)
            control_1 = QPointF(start.x() + control_delta, start.y())
            control_2 = QPointF(end.x() - control_delta, end.y())
        else:
            start = QPointF(source_rect.left(), source_center.y())
            end = QPointF(target_rect.right(), target_center.y())
            control_delta = max(80.0, abs(end.x() - start.x()) * 0.35)
            control_1 = QPointF(start.x() - control_delta, start.y())
            control_2 = QPointF(end.x() + control_delta, end.y())

        path = QPainterPath(start)
        path.cubicTo(control_1, control_2, end)
        self.setPath(path)

        label_rect = self._label_item.boundingRect()
        label_pos = path.pointAtPercent(0.5)
        self._label_item.setPos(label_pos.x() - (label_rect.width() / 2), label_pos.y() - 20)
        self._label_item.setBrush(self._selected_color if self.isSelected() else QColor("#047857"))

    def highlight_endpoints(self) -> None:
        scene = self.scene()
        if scene is not None:
            scene.clearSelection()
        self.setSelected(True)
        self.source_item.setSelected(True)
        self.target_item.setSelected(True)
        self.update_path()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.highlight_endpoints()
        event.accept()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.highlight_endpoints()
        if self._on_edit is not None:
            self._on_edit(self.target_item)
        event.accept()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.update_path()
        return result

    def paint(self, painter: QPainter, option, widget=None) -> None:
        pen = QPen(
            self._selected_color if self.isSelected() else self._default_color,
            3 if self.isSelected() else 2,
            Qt.PenStyle.DashLine,
        )
        self.setPen(pen)
        super().paint(painter, option, widget)
