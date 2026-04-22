from __future__ import annotations

import json
from contextlib import contextmanager

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QContextMenuEvent, QKeyEvent, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu, QMessageBox

from app.widgets.condition_dialog import ConditionDialog
from app.widgets.condition_link_item import ConditionLinkItem
from app.widgets.signal_node_item import SignalNodeItem


class NodeCanvasView(QGraphicsView):
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
        self._scene.setSceneRect(-2000, -2000, 4000, 4000)
        self.setScene(self._scene)
        self.setAcceptDrops(True)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setBackgroundBrush(QColor("#f1f5f9"))
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

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
                }
                if node.get("condition"):
                    payload["condition"] = dict(node["condition"])
                self.add_signal_node(payload, node.get("x", 0), node.get("y", 0), snap=False)
        finally:
            self._suppress_history = False
        self.clear_history()

    def clear_canvas(self) -> None:
        self._condition_links.clear()
        self._scene.clear()

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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._is_panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._capture_move_start(event.position().toPoint())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._is_panning:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)
        self._update_condition_links()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton and self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
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

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        signal_item = self._signal_item_at(event.pos())
        menu = QMenu(self)

        if signal_item is not None:
            signal_item.setSelected(True)
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

            if chosen_action == details_action:
                signal_item.show_details()
            elif chosen_action == edit_condition_action:
                self._edit_item_condition(signal_item)
            elif show_dependency_action is not None and chosen_action == show_dependency_action:
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
        if self._has_signal_nodes():
            fit_action = menu.addAction("Fit Nodes")

        chosen_action = menu.exec(event.globalPos())
        if chosen_action == reset_action:
            self.reset_view()
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

    def delete_selected_items(self) -> None:
        selected_links = [
            item for item in self._scene.selectedItems() if isinstance(item, ConditionLinkItem)
        ]
        if selected_links:
            with self._batch_history():
                for link in selected_links:
                    self._hide_condition_dependency(link.target_item)
            return

        selected_signal_items = [
            item for item in self._scene.selectedItems() if isinstance(item, SignalNodeItem)
        ]
        if not selected_signal_items:
            return
        with self._batch_history():
            for item in selected_signal_items:
                self._remove_signal_item(item)

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

    def _show_condition_dependency(self, target_item: SignalNodeItem) -> None:
        condition = target_item.signal_data.get("condition")
        if not condition:
            return
        if self._condition_link_for_target(target_item) is not None:
            return

        source_item = self._find_condition_source_item(condition, exclude_item=target_item)
        if source_item is None:
            payload = self._condition_source_payload(condition)
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
            self._condition_links.clear()
            self._scene.clear()
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

    def redo(self) -> None:
        if not self._redo_stack:
            return
        current = self._capture_state()
        state = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_state(state)

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
