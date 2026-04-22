from __future__ import annotations

import logging

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsSceneMouseEvent, QGraphicsSimpleTextItem, QStyle

_log = logging.getLogger(__name__)


class ConditionLinkItem(QGraphicsPathItem):
    # Width used purely for hit-testing so clicks land on the link even
    # between dashes. The visual stroke is still drawn with DashLine in paint().
    HIT_WIDTH = 16.0

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
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)
        self._label_item.setText(f"{self.condition.get('operator', '==')} {self.condition.get('value', '')}")
        # Fallback pen on the item itself: if the Python wrapper is ever GC'd,
        # the C++ base paint() will still draw something visible.
        self.setPen(QPen(self._default_color, 2, Qt.PenStyle.DashLine))
        self.update_path()

    def __del__(self):
        # Debug: if this fires while the item is still in the scene,
        # PySide6 GC'd the Python wrapper — that's the vanishing bug.
        try:
            scene = self.scene()
        except RuntimeError:
            scene = None
        if scene is not None:
            _log.warning("ConditionLinkItem.__del__ called while still in scene — GC bug!")

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
        if self._on_edit is not None:
            self._on_edit(self.target_item)
        event.accept()

    def itemChange(self, change, value):
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            # Visual refresh only - do NOT modify geometry (prepareGeometryChange /
            # setPath) from inside itemChange, as the scene is mid-iteration over
            # selection and it can corrupt dirty-region tracking, leaving the link
            # un-repainted ("vanished").
            if self._label_item is not None:
                self._label_item.setBrush(
                    self._selected_color if bool(value) else QColor("#047857")
                )
            self.update()
        return result

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # Suppress the default selection highlight (dashed outline rect);
        # we draw our own selection visuals via pen color/width.
        option.state &= ~QStyle.StateFlag.State_Selected
        pen = QPen(
            self._selected_color if self.isSelected() else self._default_color,
            3 if self.isSelected() else 2,
            Qt.PenStyle.DashLine,
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())
