from __future__ import annotations

import math
import uuid

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QInputDialog,
    QStyle,
)


class LinkItem(QGraphicsPathItem):
    HIT_WIDTH = 16.0
    ARROW_SIZE = 12

    def __init__(self, source_item, target_item, label: str = "", link_id: str = ""):
        super().__init__()
        self.link_id = link_id or uuid.uuid4().hex
        self.source_item = source_item
        self.target_item = target_item
        self._label = label
        self._default_color = QColor("#6366f1")
        self._selected_color = QColor("#4f46e5")
        self._label_item = QGraphicsSimpleTextItem(self)
        self._label_item.setText(label)
        self._label_item.setBrush(QColor("#4338ca"))
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)
        self.setPen(QPen(self._default_color, 2, Qt.PenStyle.SolidLine))
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

        # Calculate arrow angle at the end of the curve
        t = 0.98
        p_before = path.pointAtPercent(t)
        p_end = path.pointAtPercent(1.0)
        angle = math.atan2(p_end.y() - p_before.y(), p_end.x() - p_before.x())

        arrow_p1 = QPointF(
            p_end.x() - self.ARROW_SIZE * math.cos(angle - math.pi / 6),
            p_end.y() - self.ARROW_SIZE * math.sin(angle - math.pi / 6),
        )
        arrow_p2 = QPointF(
            p_end.x() - self.ARROW_SIZE * math.cos(angle + math.pi / 6),
            p_end.y() - self.ARROW_SIZE * math.sin(angle + math.pi / 6),
        )

        arrow_path = QPainterPath()
        arrow_path.moveTo(arrow_p1)
        arrow_path.lineTo(p_end)
        arrow_path.lineTo(arrow_p2)
        arrow_path.closeSubpath()

        combined = path
        combined.addPath(arrow_path)
        self.setPath(combined)

        # Position label at the midpoint of the curve
        if self._label:
            label_rect = self._label_item.boundingRect()
            label_pos = path.pointAtPercent(0.5)
            self._label_item.setPos(label_pos.x() - label_rect.width() / 2, label_pos.y() - 20)
        else:
            self._label_item.setPos(-1000, -1000)

    def set_label(self, label: str) -> None:
        self._label = label
        self._label_item.setText(label)
        self.update_path()

    def highlight_endpoints(self) -> None:
        scene = self.scene()
        if scene is not None:
            for selected in list(scene.selectedItems()):
                if selected is self or selected is self.source_item or selected is self.target_item:
                    continue
                selected.setSelected(False)
        self.setSelected(True)
        self.source_item.setSelected(True)
        self.target_item.setSelected(True)

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_WIDTH)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def boundingRect(self) -> QRectF:
        base = super().boundingRect()
        pad = self.HIT_WIDTH / 2 + 2
        return base.adjusted(-pad, -pad, pad, pad)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.highlight_endpoints()
        event.accept()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.highlight_endpoints()
        text, ok = QInputDialog.getText(
            QApplication.activeWindow(),
            "Edit Link Label",
            "Label:",
            text=self._label,
        )
        if ok:
            self.set_label(text)
        event.accept()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            if self._label_item is not None:
                self._label_item.setBrush(
                    self._selected_color if bool(value) else QColor("#4338ca")
                )
            self.update()
        return result

    def paint(self, painter: QPainter, option, widget=None) -> None:
        option.state &= ~QStyle.StateFlag.State_Selected
        pen = QPen(
            self._selected_color if self.isSelected() else self._default_color,
            3 if self.isSelected() else 2,
            Qt.PenStyle.SolidLine,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

    def to_dict(self) -> dict:
        return {
            "id": self.link_id,
            "source_id": self.source_item.node_id,
            "target_id": self.target_item.node_id,
            "label": self._label,
        }
