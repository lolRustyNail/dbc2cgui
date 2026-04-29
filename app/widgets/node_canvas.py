from __future__ import annotations

import json
from contextlib import contextmanager

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QContextMenuEvent, QKeyEvent, QMouseEvent, QPainter, QPen, QBrush, QTransform, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu, QMessageBox

from app.widgets.condition_dialog import ConditionDialog
from app.widgets.condition_link_item import ConditionLinkItem
from app.widgets.link_item import LinkItem
from app.widgets.signal_node_item import SignalNodeItem


class NodeCanvasView(QGraphicsView):
    content_changed = Signal()
    custom_node_edit_requested = Signal(str)
    MIME_TYPE = "application/x-dbc-signal"
    GRID_SIZE = SignalNodeItem.GRID_SIZE
    MIN_ZOOM = 0.35
    MAX_ZOOM = 3.0
    ZOOM_STEP = 1.15
    MAX_HISTORY = 100

    def __init__(self):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self._available_condition_sources: list[dict] = []
        self._is_panning = False
        self._pan_start = QPoint()
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._history_depth = 0
        self._suppress_history = False
        self._move_snapshot: dict | None = None
        self._move_start_positions: dict[str, tuple[float, float]] = {}
        self._condition_links: list[ConditionLinkItem] = []
        self._links: list[LinkItem] = []
        self._is_connecting = False
        self._connect_source_item: SignalNodeItem | None = None
        self._connect_source_edge: str | None = None
        self._connect_source_pos = None
        self._connect_current_pos = None
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#f1f5f9"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._minimap_dragging = False
        self._expand_scene_on_scroll = True

    # ---------------------- Minimap overlay ----------------------

    MINIMAP_W = 180
    MINIMAP_H = 120
    MINIMAP_MARGIN = 8

    def _minimap_rect(self) -> QRectF:
        """The minimap area in viewport coordinates (bottom-right corner)."""
        vp = self.viewport().rect()
        return QRectF(
            vp.right() - self.MINIMAP_W - self.MINIMAP_MARGIN,
            vp.bottom() - self.MINIMAP_H - self.MINIMAP_MARGIN,
            self.MINIMAP_W,
            self.MINIMAP_H,
        )

    def _scene_bounds_for_minimap(self) -> QRectF:
        return self._scene.sceneRect()

    def _minimap_transform(self) -> QTransform:
        bounds = self._scene_bounds_for_minimap()
        mr = self._minimap_rect()
        sx = mr.width() / bounds.width()
        sy = mr.height() / bounds.height()
        scale = min(sx, sy)
        dx = mr.x() + (mr.width() - bounds.width() * scale) / 2 - bounds.left() * scale
        dy = mr.y() + (mr.height() - bounds.height() * scale) / 2 - bounds.top() * scale
        return QTransform().translate(dx, dy).scale(scale, scale)

    def _draw_minimap(self, painter: QPainter) -> None:
        mr = self._minimap_rect()
        # Background
        painter.setPen(QPen(QColor("#94a3b8"), 1))
        painter.setBrush(QBrush(QColor("#e2e8f0")))
        painter.drawRoundedRect(mr, 4, 4)
        painter.save()
        painter.setClipRect(mr)
        tf = self._minimap_transform()
        # Condition links
        painter.setPen(QPen(QColor("#f59e0b"), 1, Qt.PenStyle.DashLine))
        for item in self._scene.items():
            if isinstance(item, ConditionLinkItem):
                p1 = tf.map(item.source_item.sceneBoundingRect().center())
                p2 = tf.map(item.target_item.sceneBoundingRect().center())
                painter.drawLine(p1.toPoint(), p2.toPoint())
        # Nodes
        for item in self._scene.items():
            if isinstance(item, SignalNodeItem):
                r = tf.mapRect(item.sceneBoundingRect())
                color = QColor("#c4b5fd") if item.is_reference() else QColor("#94a3b8")
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor("#64748b"), 0.8))
                painter.drawRoundedRect(r, 2, 2)
        # Viewport indicator
        vp_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        mapped_vp = tf.mapRect(vp_rect)
        painter.setBrush(QBrush(QColor(59, 130, 246, 60)))
        painter.setPen(QPen(QColor(59, 130, 246, 180), 1.5))
        painter.drawRect(mapped_vp)
        painter.restore()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_minimap(painter)
        if self._is_connecting and self._connect_source_pos and self._connect_current_pos:
            v1 = self.mapFromScene(self._connect_source_pos)
            v2 = self.mapFromScene(self._connect_current_pos)
            painter.setPen(QPen(QColor("#3b82f6"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(v1, v2)
        painter.end()

    def _minimap_navigate(self, viewport_pos: QPoint) -> None:
        tf, ok = self._minimap_transform().inverted()
        if not ok:
            return
        sp = tf.map(QPoint(viewport_pos.x(), viewport_pos.y()))
        self.centerOn(sp.x(), sp.y())

    def _in_minimap(self, pos: QPoint) -> bool:
        return self._minimap_rect().contains(pos.x(), pos.y())

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(self.MIME_TYPE):
            super().dropEvent(event)
            return

        payload = json.loads(bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8"))
        scene_position = self.mapToScene(event.position().toPoint())
        self.add_signal_node(payload, scene_position.x(), scene_position.y())
        event.acceptProposedAction()

    def add_signal_node(self, payload: dict, x: float, y: float, snap: bool = True) -> None:
        with self._batch_history():
            item = SignalNodeItem(payload)
            if snap:
                x, y = self.snap_point(x, y)
            item.setPos(x, y)
            self._scene.addItem(item)
        self.content_changed.emit()

    def set_available_condition_sources(self, sources: list[dict]) -> None:
        unique_sources: list[dict] = []
        seen_keys = set()
        for source in sources:
            key = (source.get("source_message", ""), source.get("source_signal", ""))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            unique_sources.append(
                {
                    "source_node": source.get("source_node", ""),
                    "direction": source.get("direction", "ref"),
                    "source_message": source.get("source_message", ""),
                    "source_signal": source.get("source_signal", ""),
                    "frame_id": source.get("frame_id", 0),
                    "start_bit": source.get("start_bit", 0),
                    "length": source.get("length", 0),
                    "byte_order": source.get("byte_order", "big_endian"),
                }
            )
        self._available_condition_sources = unique_sources

    def load_nodes(self, nodes: list[dict]) -> None:
        self._suppress_history = True
        try:
            self.clear_canvas()
            for node in nodes:
                payload = {
                    "id": node.get("id"),
                    "node": node["node"],
                    "direction": node["direction"],
                    "message": node["message"],
                    "frame_id": node["frame_id"],
                    "signal": node["signal"],
                    "start_bit": node["start_bit"],
                    "length": node["length"],
                    "byte_order": node.get("byte_order", "big_endian"),
                }
                if node.get("condition"):
                    payload["condition"] = dict(node["condition"])
                self.add_signal_node(payload, node.get("x", 0), node.get("y", 0), snap=False)

            # Restore condition link visibility for nodes with shown=true
            for scene_item in list(self._scene.items()):
                if not isinstance(scene_item, SignalNodeItem) or scene_item.is_reference():
                    continue
                condition = scene_item.signal_data.get("condition")
                if condition and condition.get("shown"):
                    self._show_condition_dependency(scene_item)
        finally:
            self._suppress_history = False
        self.clear_history()

    def clear_canvas(self) -> None:
        self._scene.clear()
        self._condition_links.clear()
        self._links.clear()

    def export_nodes(self) -> list[dict]:
        nodes = [
            item.to_export_dict()
            for item in self._scene.items()
            if isinstance(item, SignalNodeItem) and not item.is_reference()
        ]
        nodes.sort(key=lambda item: item["id"])
        return nodes

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            self.delete_selected_items()
            return
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_D:
            self.duplicate_selected_items()
            return
        if mods & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Z:
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self.redo()
            else:
                self.undo()
            return
        if mods & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_Y:
            self.redo()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._in_minimap(event.pos()):
            self._minimap_dragging = True
            self._minimap_navigate(event.pos())
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            mods = event.modifiers()
            item = self._signal_item_at(event.position().toPoint())
            if item is not None and (mods & Qt.KeyboardModifier.ControlModifier):
                scene_pos = self.mapToScene(event.position().toPoint())
                edge = item.edge_at(scene_pos)
                if edge is not None:
                    self._is_connecting = True
                    self._connect_source_item = item
                    self._connect_source_edge = edge
                    self._connect_source_pos = item.edge_anchor_point(edge)
                    self._connect_current_pos = self._connect_source_pos
                    event.accept()
                    return
            self._capture_move_start(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._minimap_dragging:
            self._minimap_navigate(event.pos())
            event.accept()
            return
        if self._is_panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        if self._is_connecting:
            self._connect_current_pos = self.mapToScene(event.position().toPoint())
            self.viewport().update()
            event.accept()
            return
        super().mouseMoveEvent(event)
        self._update_condition_links()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._minimap_dragging:
            self._minimap_dragging = False
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self._is_connecting:
            self._is_connecting = False
            scene_pos = self.mapToScene(event.position().toPoint())
            target_item = self._signal_item_at(event.position().toPoint())
            if target_item is not None and target_item is not self._connect_source_item:
                self._finalize_link(self._connect_source_item, target_item)
            self._connect_source_item = None
            self._connect_current_pos = None
            self.viewport().update()
            event.accept()
            return
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._commit_move_history()
        self._update_condition_links()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
            self._apply_zoom(factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            signal_item = self._signal_item_at(event.position().toPoint())
            if signal_item is not None and signal_item.signal_data.get("type") == "custom":
                self.custom_node_edit_requested.emit(signal_item.node_id)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        signal_item = self._signal_item_at(event.pos())
        menu = QMenu(self)

        if signal_item is not None:
            signal_item.setSelected(True)
            is_custom = signal_item.signal_data.get("type") == "custom"

            if is_custom:
                edit_custom_action = menu.addAction("Edit Custom Node")
            else:
                details_action = menu.addAction("View Details")
                edit_condition_action = menu.addAction("Edit Receive Condition")

            show_dependency_action = None
            hide_dependency_action = None
            if signal_item.has_condition() and not signal_item.is_reference():
                if self._condition_link_for_target(signal_item) is None:
                    show_dependency_action = menu.addAction("Show Condition Dependency")
                else:
                    hide_dependency_action = menu.addAction("Hide Condition Dependency")
            clear_condition_action = None
            if signal_item.has_condition():
                clear_condition_action = menu.addAction("Clear Receive Condition")
            duplicate_action = menu.addAction("Duplicate Node")
            delete_action = menu.addAction("Delete Node")
            menu.addSeparator()
            fit_action = menu.addAction("Fit Nodes")
            chosen_action = menu.exec(event.globalPos())

            if is_custom:
                if chosen_action == edit_custom_action:
                    self.custom_node_edit_requested.emit(signal_item.node_id)
            else:
                if chosen_action == details_action:
                    signal_item.show_details()
                elif chosen_action == edit_condition_action:
                    self._edit_item_condition(signal_item)

            if show_dependency_action is not None and chosen_action == show_dependency_action:
                with self._batch_history():
                    self._show_condition_dependency(signal_item)
            elif hide_dependency_action is not None and chosen_action == hide_dependency_action:
                self._hide_condition_dependency(signal_item)
            elif clear_condition_action is not None and chosen_action == clear_condition_action:
                with self._batch_history():
                    self._hide_condition_dependency(signal_item)
                    signal_item.set_condition(None)
            elif chosen_action == duplicate_action:
                self._duplicate_item(signal_item)
            elif chosen_action == delete_action:
                self._remove_signal_item(signal_item)
            elif chosen_action == fit_action:
                self.fit_all_nodes()
            return

        reset_action = menu.addAction("Reset View")
        fit_action = None
        auto_layout_action = None
        if self._has_signal_nodes():
            auto_layout_action = menu.addAction("Auto Layout")
            fit_action = menu.addAction("Fit Nodes")

        chosen_action = menu.exec(event.globalPos())
        if chosen_action == reset_action:
            self.reset_view()
        elif auto_layout_action is not None and chosen_action == auto_layout_action:
            self.auto_layout()
        elif fit_action is not None and chosen_action == fit_action:
            self.fit_all_nodes()

    def _apply_zoom(self, factor: float) -> None:
        current_zoom = self.transform().m11()
        next_zoom = current_zoom * factor
        if next_zoom < self.MIN_ZOOM:
            factor = self.MIN_ZOOM / current_zoom
        elif next_zoom > self.MAX_ZOOM:
            factor = self.MAX_ZOOM / current_zoom

        if factor == 1:
            return

        self.scale(factor, factor)
        self.viewport().update()

    def scrollContentsBy(self, dx, dy) -> None:
        super().scrollContentsBy(dx, dy)
        self._expand_scene_rect()
        self.viewport().update()

    def _expand_scene_rect(self) -> None:
        """Grow the scene rect if the viewport approaches the edge, giving an infinite canvas feel."""
        if not self._expand_scene_on_scroll:
            return
        vp_scene = self.mapToScene(self.viewport().rect()).boundingRect()
        sr = self._scene.sceneRect()
        margin = 2000
        need_expand = False
        new_left = sr.left()
        new_top = sr.top()
        new_right = sr.right()
        new_bottom = sr.bottom()
        if vp_scene.left() < sr.left() + margin:
            new_left = vp_scene.left() - margin
            need_expand = True
        if vp_scene.top() < sr.top() + margin:
            new_top = vp_scene.top() - margin
            need_expand = True
        if vp_scene.right() > sr.right() - margin:
            new_right = vp_scene.right() + margin
            need_expand = True
        if vp_scene.bottom() > sr.bottom() - margin:
            new_bottom = vp_scene.bottom() + margin
            need_expand = True
        if need_expand:
            self._scene.setSceneRect(new_left, new_top, new_right - new_left, new_bottom - new_top)

    def reset_view(self) -> None:
        self.resetTransform()
        self.centerOn(0, 0)

    def fit_all_nodes(self) -> None:
        items = [item for item in self._scene.items() if isinstance(item, SignalNodeItem)]
        if not items:
            return

        bounds = items[0].sceneBoundingRect()
        for item in items[1:]:
            bounds = bounds.united(item.sceneBoundingRect())

        self.fitInView(bounds.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)

    def auto_layout(self) -> None:
        """Arrange all non-reference nodes grouped by message in a vertical grid layout.

        Nodes are laid out top-to-bottom in columns (max_rows per column),
        then move right. Each message group gets its own column block.
        """
        items = [
            item for item in self._scene.items()
            if isinstance(item, SignalNodeItem) and not item.is_reference()
        ]
        if not items:
            return

        # Group by message
        groups: dict[str, list[SignalNodeItem]] = {}
        for item in items:
            msg = item.signal_data.get("message", "")
            groups.setdefault(msg, []).append(item)

        # Sort messages alphabetically, sort signals within each message by start_bit
        sorted_messages = sorted(groups.keys())
        for msg in sorted_messages:
            groups[msg].sort(
                key=lambda it: (it.signal_data.get("start_bit", 0), it.signal_data.get("signal", ""))
            )

        node_w = SignalNodeItem.WIDTH
        node_h = SignalNodeItem.HEIGHT
        h_gap = 40
        v_gap = 24
        group_gap = 120  # extra horizontal gap between message groups
        max_rows = max(1, 8)  # nodes per column before wrapping right

        with self._batch_history():
            x = 0.0
            for msg in sorted_messages:
                group_items = groups[msg]
                for i, item in enumerate(group_items):
                    row = i % max_rows
                    col = i // max_rows
                    item_x = x + col * (node_w + h_gap)
                    item_y = row * (node_h + v_gap)
                    sx, sy = self.snap_point(item_x, item_y)
                    item.setPos(sx, sy)
                cols_needed = (len(group_items) + max_rows - 1) // max_rows
                x += cols_needed * (node_w + h_gap) + group_gap

        self._update_condition_links()
        self.content_changed.emit()
        self.fit_all_nodes()

    def delete_selected_items(self) -> None:
        selected_condition_links = [
            item for item in self._scene.selectedItems() if isinstance(item, ConditionLinkItem)
        ]
        if selected_condition_links:
            with self._batch_history():
                for link in selected_condition_links:
                    self._hide_condition_dependency(link.target_item)
            self.content_changed.emit()
            return

        selected_link_items = [
            item for item in self._scene.selectedItems() if isinstance(item, LinkItem)
        ]
        if selected_link_items:
            with self._batch_history():
                for link in selected_link_items:
                    self._scene.removeItem(link)
                    if link in self._links:
                        self._links.remove(link)
            self.content_changed.emit()
            return

        selected_signal_items = [
            item for item in self._scene.selectedItems() if isinstance(item, SignalNodeItem)
        ]
        if not selected_signal_items:
            return
        with self._batch_history():
            for item in selected_signal_items:
                self._remove_signal_item(item)
        self.content_changed.emit()

    def duplicate_selected_items(self) -> None:
        if any(isinstance(item, ConditionLinkItem) for item in self._scene.selectedItems()):
            return

        selected_signal_items = [
            item
            for item in self._scene.selectedItems()
            if isinstance(item, SignalNodeItem) and not item.is_reference()
        ]
        if not selected_signal_items:
            return
        with self._batch_history():
            for item in selected_signal_items:
                self._duplicate_item(item)
        self.content_changed.emit()

    def _duplicate_item(self, item: SignalNodeItem) -> None:
        payload = item.to_node_payload(include_id=False)
        position = item.scenePos()
        self.add_signal_node(payload, position.x() + 32, position.y() + 32)

    def _edit_item_condition(self, item: SignalNodeItem) -> None:
        available_sources = self._condition_sources_for_item(item)
        if not available_sources:
            QMessageBox.information(
                self,
                "No Condition Sources",
                "No signal sources are currently available for configuring a receive condition.",
            )
            return

        condition = ConditionDialog.get_condition(
            self,
            available_sources,
            item.signal_data,
            item.signal_data.get("condition"),
        )
        if condition is not None:
            with self._batch_history():
                item.set_condition(condition)
                if self._condition_link_for_target(item) is not None:
                    self._hide_condition_dependency(item)
                    self._show_condition_dependency(item)
                if item.signal_data.get("type") == "custom":
                    item.signal_data["source_message"] = condition.get("source_message", "")
                    item.signal_data["source_signal"] = condition.get("source_signal", "")
                    item._build_text()
                    item.setToolTip(item._dialog_text())
            self.content_changed.emit()

    def _show_condition_dependency(self, target_item: SignalNodeItem) -> None:
        condition = target_item.signal_data.get("condition")
        if not condition:
            return
        if self._condition_link_for_target(target_item) is not None:
            return

        source_item = self._find_condition_source_item(condition, exclude_item=target_item)
        if source_item is None:
            payload = self._condition_source_payload(condition)
            # Use saved position if available, otherwise calculate default
            if "source_x" in condition and "source_y" in condition:
                x, y = condition["source_x"], condition["source_y"]
            else:
                x, y = self._reference_position_for_target(target_item)
            self.add_signal_node(payload, x, y)
            source_item = self._find_condition_source_item(condition, exclude_item=target_item)
            if source_item is None:
                return

        link = ConditionLinkItem(source_item, target_item, condition, on_edit=self._edit_item_condition)
        self._scene.addItem(link)
        self._condition_links.append(link)
        self._update_condition_links()

    def _hide_condition_dependency(self, target_item: SignalNodeItem) -> None:
        link = self._condition_link_for_target(target_item)
        if link is None:
            return

        with self._batch_history():
            source_item = link.source_item
            self._scene.removeItem(link)
            if link in self._condition_links:
                self._condition_links.remove(link)
            if source_item.is_reference() and not self._has_links_for_item(source_item):
                self._scene.removeItem(source_item)
        self.content_changed.emit()

    def _condition_link_for_target(self, target_item: SignalNodeItem) -> ConditionLinkItem | None:
        for scene_item in self._scene.items():
            if isinstance(scene_item, ConditionLinkItem) and scene_item.target_item is target_item:
                return scene_item
        return None

    def _find_condition_source_item(
        self,
        condition: dict,
        exclude_item: SignalNodeItem | None = None,
    ) -> SignalNodeItem | None:
        candidates = []
        for scene_item in self._scene.items():
            if not isinstance(scene_item, SignalNodeItem):
                continue
            if scene_item is exclude_item:
                continue
            if (
                scene_item.signal_data.get("message") == condition.get("source_message")
                and scene_item.signal_data.get("signal") == condition.get("source_signal")
            ):
                candidates.append(scene_item)

        if not candidates:
            return None

        candidates.sort(key=lambda item: 1 if item.is_reference() else 0)
        return candidates[0]

    def _condition_source_payload(self, condition: dict) -> dict:
        source_info = self._condition_source_info(condition)
        return {
            "node": source_info.get("source_node", condition.get("source_node", "")),
            "direction": source_info.get("direction", "ref"),
            "message": source_info.get("source_message", condition.get("source_message", "")),
            "frame_id": source_info.get("frame_id", 0),
            "signal": source_info.get("source_signal", condition.get("source_signal", "")),
            "start_bit": source_info.get("start_bit", 0),
            "length": source_info.get("length", 0),
            "byte_order": source_info.get("byte_order", "big_endian"),
            "reference": True,
        }

    def _condition_source_info(self, condition: dict) -> dict:
        for source in self._available_condition_sources:
            if (
                source.get("source_message") == condition.get("source_message")
                and source.get("source_signal") == condition.get("source_signal")
            ):
                return source
        return dict(condition)

    def _reference_position_for_target(self, target_item: SignalNodeItem) -> tuple[float, float]:
        position = target_item.scenePos()
        base_x = position.x() - SignalNodeItem.WIDTH - 120
        base_y = position.y()
        offset_index = 0
        while self._reference_collision(base_x, base_y + (offset_index * (SignalNodeItem.HEIGHT + 24))):
            offset_index += 1
        return self.snap_point(base_x, base_y + (offset_index * (SignalNodeItem.HEIGHT + 24)))

    def _reference_collision(self, x: float, y: float) -> bool:
        for scene_item in self._scene.items():
            if not isinstance(scene_item, SignalNodeItem):
                continue
            scene_position = scene_item.scenePos()
            if abs(scene_position.x() - x) < 8 and abs(scene_position.y() - y) < 8:
                return True
        return False

    def _condition_sources_for_item(self, item: SignalNodeItem) -> list[dict]:
        sources = list(self._available_condition_sources)
        if not sources:
            sources = self._collect_condition_sources_from_canvas()

        current_condition = item.signal_data.get("condition")
        if current_condition:
            current_source = {
                "source_node": current_condition.get("source_node", ""),
                "source_message": current_condition.get("source_message", ""),
                "source_signal": current_condition.get("source_signal", ""),
            }
            if current_source["source_signal"] and current_source not in sources:
                sources.append(current_source)

        return sources

    def _collect_condition_sources_from_canvas(self) -> list[dict]:
        sources: list[dict] = []
        seen_keys = set()
        for scene_item in self._scene.items():
            if not isinstance(scene_item, SignalNodeItem):
                continue
            key = (
                scene_item.signal_data.get("message", ""),
                scene_item.signal_data.get("signal", ""),
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            sources.append(
                {
                    "source_node": scene_item.signal_data.get("node", ""),
                    "direction": scene_item.signal_data.get("direction", ""),
                    "source_message": scene_item.signal_data.get("message", ""),
                    "source_signal": scene_item.signal_data.get("signal", ""),
                    "frame_id": scene_item.signal_data.get("frame_id", 0),
                    "start_bit": scene_item.signal_data.get("start_bit", 0),
                    "length": scene_item.signal_data.get("length", 0),
                    "byte_order": scene_item.signal_data.get("byte_order", "big_endian"),
                }
            )
        return sources

    def _remove_signal_item(self, item: SignalNodeItem) -> None:
        with self._batch_history():
            for scene_item in list(self._scene.items()):
                if not isinstance(scene_item, ConditionLinkItem):
                    continue
                if scene_item.source_item is item or scene_item.target_item is item:
                    source_item = scene_item.source_item
                    self._scene.removeItem(scene_item)
                    if scene_item in self._condition_links:
                        self._condition_links.remove(scene_item)
                    if source_item is not item and source_item.is_reference() and not self._has_links_for_item(source_item):
                        self._scene.removeItem(source_item)
            self._scene.removeItem(item)

    def _has_links_for_item(self, item: SignalNodeItem) -> bool:
        return any(
            isinstance(scene_item, ConditionLinkItem)
            and (scene_item.source_item is item or scene_item.target_item is item)
            for scene_item in self._scene.items()
        )

    def _update_condition_links(self) -> None:
        for scene_item in self._scene.items():
            if isinstance(scene_item, ConditionLinkItem):
                scene_item.update_path()
            elif isinstance(scene_item, LinkItem):
                scene_item.update_path()
        self.viewport().update()

    def _finalize_link(self, source: SignalNodeItem, target: SignalNodeItem) -> None:
        link = LinkItem(source, target, label="")
        self._scene.addItem(link)
        self._links.append(link)
        self.content_changed.emit()

    def add_link(self, source_id: str, target_id: str, label: str = "", link_id: str = "") -> None:
        source = self._find_node_by_id(source_id)
        target = self._find_node_by_id(target_id)
        if source and target:
            link = LinkItem(source, target, label=label, link_id=link_id)
            self._scene.addItem(link)
            self._links.append(link)

    def export_links(self) -> list[dict]:
        return [link.to_dict() for link in self._links]

    def update_custom_node_data(self, node) -> None:
        for item in self._scene.items():
            if isinstance(item, SignalNodeItem) and item.node_id == node.id:
                item.signal_data.update({
                    "signal": node.name,
                    "target_variable": node.target_variable,
                    "description": node.description,
                    "source_message": node.source_message,
                    "source_signal": node.source_signal,
                    "mapping_table": [{"dbc_value": m.dbc_value, "radar_value": m.radar_value} for m in node.mapping_table],
                })
                item._build_text()
                item.setToolTip(item._dialog_text())
                break

    def remove_custom_node_by_id(self, node_id: str) -> None:
        for item in list(self._scene.items()):
            if isinstance(item, SignalNodeItem) and item.node_id == node_id:
                self._remove_signal_item(item)
                break

    def snap_point(self, x: float, y: float) -> tuple[float, float]:
        return SignalNodeItem.snap_value(x), SignalNodeItem.snap_value(y)

    def _signal_item_at(self, position) -> SignalNodeItem | None:
        item = self.itemAt(position)
        while item is not None:
            if isinstance(item, SignalNodeItem):
                return item
            item = item.parentItem()
        return None

    def _has_signal_nodes(self) -> bool:
        return any(isinstance(item, SignalNodeItem) for item in self._scene.items())

    # ---------------------- Undo / Redo history ----------------------

    def _capture_state(self) -> dict:
        nodes: list[dict] = []
        for scene_item in self._scene.items():
            if isinstance(scene_item, SignalNodeItem):
                data = scene_item.to_node_payload(include_id=True)
                pos = scene_item.scenePos()
                data["x"] = pos.x()
                data["y"] = pos.y()
                nodes.append(data)
        links: list[dict] = []
        for scene_item in self._scene.items():
            if isinstance(scene_item, ConditionLinkItem):
                links.append(
                    {
                        "source_id": scene_item.source_item.node_id,
                        "target_id": scene_item.target_item.node_id,
                        "condition": dict(scene_item.condition),
                    }
                )
        return {"nodes": nodes, "links": links}

    def _restore_state(self, state: dict) -> None:
        self._suppress_history = True
        try:
            self._scene.clear()
            self._condition_links.clear()
            id_map: dict[str, SignalNodeItem] = {}
            for node in state["nodes"]:
                item = SignalNodeItem(node)
                item.setPos(node["x"], node["y"])
                self._scene.addItem(item)
                id_map[item.node_id] = item
            for link in state["links"]:
                source = id_map.get(link["source_id"])
                target = id_map.get(link["target_id"])
                if source is None or target is None:
                    continue
                link_item = ConditionLinkItem(
                    source, target, link["condition"], on_edit=self._edit_item_condition
                )
                self._scene.addItem(link_item)
                self._condition_links.append(link_item)
            self._update_condition_links()
        finally:
            self._suppress_history = False

    def _push_history(self) -> None:
        if self._suppress_history:
            return
        self._undo_stack.append(self._capture_state())
        if len(self._undo_stack) > self.MAX_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    @contextmanager
    def _batch_history(self):
        if self._suppress_history:
            yield
            return
        if self._history_depth == 0:
            self._push_history()
        self._history_depth += 1
        try:
            yield
        finally:
            self._history_depth -= 1

    def record_history(self) -> None:
        """Public hook for callers to snapshot current state before an external change."""
        self._push_history()

    def clear_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> None:
        if not self._undo_stack:
            return
        current = self._capture_state()
        state = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_state(state)
        self.content_changed.emit()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        current = self._capture_state()
        state = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_state(state)
        self.content_changed.emit()

    def _capture_move_start(self, view_pos: QPoint) -> None:
        item = self._signal_item_at(view_pos)
        if item is None:
            self._move_snapshot = None
            self._move_start_positions = {}
            return
        self._move_snapshot = self._capture_state()
        positions: dict[str, tuple[float, float]] = {}
        tracked = {item}
        for sel in self._scene.selectedItems():
            if isinstance(sel, SignalNodeItem):
                tracked.add(sel)
        for node in tracked:
            pos = node.scenePos()
            positions[node.node_id] = (pos.x(), pos.y())
        self._move_start_positions = positions

    def _commit_move_history(self) -> None:
        if self._move_snapshot is None:
            return
        snapshot = self._move_snapshot
        starts = self._move_start_positions
        self._move_snapshot = None
        self._move_start_positions = {}

        changed = False
        for node_id, (ox, oy) in starts.items():
            item = self._find_node_by_id(node_id)
            if item is None:
                changed = True
                break
            pos = item.scenePos()
            if abs(pos.x() - ox) > 0.5 or abs(pos.y() - oy) > 0.5:
                changed = True
                break
        if not changed or self._suppress_history:
            return
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self.MAX_HISTORY:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.content_changed.emit()

    def _find_node_by_id(self, node_id: str) -> SignalNodeItem | None:
        for scene_item in self._scene.items():
            if isinstance(scene_item, SignalNodeItem) and scene_item.node_id == node_id:
                return scene_item
        return None

    # -----------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect) -> None:
        super().drawBackground(painter, rect)
        grid_size = self.GRID_SIZE
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)
        painter.setPen(QPen(QColor("#e2e8f0"), 1))

        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid_size

        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid_size
