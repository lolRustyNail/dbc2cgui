from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.converter import ConverterManager
from app.convert_worker import ConvertWorker
from app.dbc_loader import load_dbc_document
from app.json_exporter import (
    export_canvas_json,
    export_custom_nodes_json,
    load_canvas_json,
    load_custom_nodes_json,
    custom_node_to_canvas_dict,
)
from app.models import CustomNode, MappingEntry
from app.state import AppState
from app.widgets.custom_node_dialog import CustomNodeDialog
from app.widgets.dbc_tree import DbcTreeWidget
from app.widgets.node_canvas import NodeCanvasView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.state = AppState()
        self._tree_drop_offset = 0
        self.left_panel = QWidget()
        self.dbc_search = QLineEdit()
        self.dbc_tree = DbcTreeWidget()
        self.node_canvas = NodeCanvasView()
        self.converter_manager = ConverterManager()
        self._convert_worker: ConvertWorker | None = None

        self.setWindowTitle("DBC2C")
        self._settings = QSettings("DBC2C", "DBC2C")

        self._build_actions()
        self._build_layout()
        self._build_progress_bar()
        self._build_shortcuts()
        self._restore_window_state()
        self.statusBar().showMessage("Import a DBC file to start building nodes.")

    def _build_actions(self) -> None:
        self.import_action = QAction("Import DBC", self)
        self.import_action.setShortcut(QKeySequence("Ctrl+O"))
        self.import_action.setStatusTip("Import a DBC file")
        self.import_action.triggered.connect(self.import_dbc)

        self.import_json_action = QAction("Import JSON", self)
        self.import_json_action.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self.import_json_action.setStatusTip("Import a saved canvas JSON file")
        self.import_json_action.triggered.connect(self.import_json)

        self.export_action = QAction("Export JSON", self)
        self.export_action.setShortcut(QKeySequence.StandardKey.Save)
        self.export_action.setStatusTip("Export the current canvas JSON")
        self.export_action.triggered.connect(self.export_json)

        self.import_custom_nodes_action = QAction("Import Custom Nodes", self)
        self.import_custom_nodes_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.import_custom_nodes_action.setStatusTip("Import custom mapping nodes from file")
        self.import_custom_nodes_action.triggered.connect(self._import_custom_nodes)

        self.export_custom_nodes_action = QAction("Export Custom Nodes", self)
        self.export_custom_nodes_action.setStatusTip("Export custom mapping nodes to file")
        self.export_custom_nodes_action.triggered.connect(self._export_custom_nodes)

        self.clear_action = QAction("Clear Canvas", self)
        self.clear_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.clear_action.setStatusTip("Clear all nodes from the canvas")
        self.clear_action.triggered.connect(self.clear_canvas)

        self.focus_search_action = QAction("Focus Search", self)
        self.focus_search_action.setShortcut(QKeySequence.StandardKey.Find)
        self.focus_search_action.setStatusTip("Focus the DBC search box")
        self.focus_search_action.triggered.connect(self.focus_search)

        self.duplicate_action = QAction("Duplicate Selected Nodes", self)
        self.duplicate_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_action.setStatusTip("Duplicate selected canvas nodes")
        self.duplicate_action.triggered.connect(self.node_canvas.duplicate_selected_items)

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Undo))
        self.undo_action.setStatusTip("Undo the last canvas change")
        self.undo_action.triggered.connect(self.node_canvas.undo)
        self.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut(QKeySequence(QKeySequence.StandardKey.Redo))
        self.redo_action.setStatusTip("Redo the previously undone canvas change")
        self.redo_action.triggered.connect(self.node_canvas.redo)
        self.addAction(self.redo_action)

        self.fit_nodes_action = QAction("Fit Nodes", self)
        self.fit_nodes_action.setShortcut(QKeySequence("Ctrl+Shift+F"))
        self.fit_nodes_action.setStatusTip("Fit all canvas nodes into view")
        self.fit_nodes_action.triggered.connect(self.node_canvas.fit_all_nodes)

        self.auto_layout_action = QAction("Auto Layout", self)
        self.auto_layout_action.setShortcut(QKeySequence("Ctrl+L"))
        self.auto_layout_action.setStatusTip("Arrange nodes grouped by message")
        self.auto_layout_action.triggered.connect(self.node_canvas.auto_layout)

        self.reset_view_action = QAction("Reset View", self)
        self.reset_view_action.setShortcut(QKeySequence("Ctrl+0"))
        self.reset_view_action.setStatusTip("Reset canvas zoom and position")
        self.reset_view_action.triggered.connect(self.node_canvas.reset_view)

        self.convert_action = QAction("Convert", self)
        self.convert_action.setShortcut(QKeySequence("Ctrl+G"))
        self.convert_action.setStatusTip("Convert current canvas to code")
        self.convert_action.triggered.connect(self._convert)

        self.load_converter_action = QAction("Load Converter Script", self)
        self.load_converter_action.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.load_converter_action.setStatusTip("Load a Python converter script")
        self.load_converter_action.triggered.connect(self._load_converter_script)

        self.remove_converter_action = QAction("Remove Converter Script", self)
        self.remove_converter_action.setStatusTip("Remove a loaded converter script")
        self.remove_converter_action.triggered.connect(self._remove_converter_script)

        self.changelog_action = QAction("Changelog", self)
        self.changelog_action.setStatusTip("Show the application changelog")
        self.changelog_action.triggered.connect(self.show_changelog)

        self.about_action = QAction("About DBC2C", self)
        self.about_action.setStatusTip("About this application")
        self.about_action.triggered.connect(self.show_about)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(self.import_action)
        toolbar.addAction(self.import_json_action)
        toolbar.addAction(self.export_action)
        toolbar.addAction(self.clear_action)
        toolbar.addSeparator()
        toolbar.addAction(self.auto_layout_action)
        toolbar.addAction(self.fit_nodes_action)
        toolbar.addSeparator()
        toolbar.addAction(self.convert_action)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.import_json_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.import_custom_nodes_action)
        file_menu.addAction(self.export_custom_nodes_action)
        file_menu.addSeparator()
        file_menu.addAction(self.clear_action)
        file_menu.addSeparator()
        file_menu.addAction(self.convert_action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.focus_search_action)
        edit_menu.addAction(self.duplicate_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.auto_layout_action)
        view_menu.addAction(self.fit_nodes_action)
        view_menu.addAction(self.reset_view_action)

        tools_menu = self.menuBar().addMenu("Tools")
        tools_menu.addAction(self.load_converter_action)
        tools_menu.addAction(self.remove_converter_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.convert_action)

        info_menu = self.menuBar().addMenu("Info")
        info_menu.addAction(self.changelog_action)
        info_menu.addSeparator()
        info_menu.addAction(self.about_action)

    def _build_layout(self) -> None:
        self.dbc_search.setPlaceholderText("Search nodes, messages, or signals")
        self.dbc_search.setClearButtonEnabled(True)
        self.dbc_search.textChanged.connect(self.dbc_tree.apply_filter)
        self.dbc_tree.signal_activated.connect(self._add_signal_from_tree)
        self.dbc_tree.message_activated.connect(self._add_message_from_tree)
        self.node_canvas.content_changed.connect(self._on_canvas_changed)
        self.dbc_tree.create_custom_node_requested.connect(self._create_custom_node)
        self.dbc_tree.edit_custom_node_requested.connect(self._edit_custom_node)
        self.dbc_tree.delete_custom_node_requested.connect(self._delete_custom_node)
        self.node_canvas.custom_node_edit_requested.connect(self._edit_custom_node)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.dbc_search)
        left_layout.addWidget(self.dbc_tree)
        self.left_panel.setLayout(left_layout)

        self._splitter = QSplitter(self)
        self._splitter.addWidget(self.left_panel)
        self._splitter.addWidget(self.node_canvas)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        screen = QApplication.primaryScreen().availableGeometry()
        left_width = int(screen.width() * 0.22)
        right_width = int(screen.width() * 0.63)
        self._splitter.setSizes([left_width, right_width])
        self.setCentralWidget(self._splitter)

    def _build_progress_bar(self) -> None:
        self._progress_bar = QProgressBar(self)
        self._progress_bar.setMaximumWidth(300)
        self._progress_bar.setMaximumHeight(16)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setVisible(False)
        self.statusBar().addPermanentWidget(self._progress_bar)

    def _build_shortcuts(self) -> None:
        self.delete_shortcut = QShortcut(QKeySequence("Delete"), self.node_canvas)
        self.delete_shortcut.activated.connect(self.node_canvas.delete_selected_items)

        self.backspace_shortcut = QShortcut(QKeySequence("Backspace"), self.node_canvas)
        self.backspace_shortcut.activated.connect(self.node_canvas.delete_selected_items)

        self.redo_shortcut_shift_z = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut_shift_z.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.redo_shortcut_shift_z.activated.connect(self.node_canvas.redo)

    def focus_search(self) -> None:
        self.dbc_search.setFocus()
        self.dbc_search.selectAll()

    def show_changelog(self) -> None:
        changelog_path = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        try:
            text = changelog_path.read_text(encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Changelog Unavailable",
                f"Could not read changelog:\n{exc}",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Changelog")
        dialog.resize(680, 520)

        browser = QTextBrowser(dialog)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(text)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        buttons.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dialog.accept)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(browser)
        layout.addWidget(buttons)

        dialog.exec()

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About DBC2C",
            (
                "<h3>DBC2C</h3>"
                "<p>A visual editor for DBC signal relationships.</p>"
                "<p>Drag signals from a DBC file onto the canvas, configure receive "
                "conditions between them, and export the result as JSON.</p>"
                "<p>Built with PySide6 and cantools.</p>"
            ),
        )

    def import_dbc(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import DBC",
            "",
            "DBC Files (*.dbc);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            document = load_dbc_document(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))
            return

        self.state.current_document = document
        self.dbc_tree.load_document(document, self.state.custom_nodes)
        self.node_canvas.set_available_condition_sources(
            self._collect_condition_sources_from_document(document)
        )
        self.dbc_search.clear()
        self.node_canvas.clear_canvas()
        self.node_canvas.clear_history()
        self.state.current_canvas_file = None
        self.state.has_unsaved_changes = False
        self._update_title()
        self.statusBar().showMessage(
            f"Loaded {Path(file_path).name}. Drag signals to the canvas."
        )

    def import_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Canvas JSON",
            "",
            "JSON Files (*.json);;All Files (*.*)",
        )
        if not file_path:
            return

        try:
            payload = load_canvas_json(file_path)
        except Exception as exc:
            QMessageBox.critical(self, "Import JSON Failed", str(exc))
            return

        dbc_message = self._restore_document_from_canvas(payload.get("dbc_file"))
        self.dbc_search.clear()
        self.node_canvas.load_nodes(payload["nodes"])
        if self.state.current_document is None:
            self.node_canvas.set_available_condition_sources(
                self._collect_condition_sources_from_nodes(payload["nodes"])
            )
        self.state.current_canvas_file = file_path
        self.state.has_unsaved_changes = False

        for data in payload.get("custom_nodes", []):
            self.node_canvas.add_signal_node(data, data.get("x", 0), data.get("y", 0), snap=False)

        for data in payload.get("links", []):
            source_id = data.get("source_id", "")
            target_id = data.get("target_id", "")
            label = data.get("label", "")
            link_id = data.get("id", "")
            self.node_canvas.add_link(source_id, target_id, label, link_id)

        self._update_title()

        status_message = f"Loaded {len(payload['nodes'])} canvas nodes from {Path(file_path).name}."
        if dbc_message:
            status_message = f"{status_message} {dbc_message}"
        self.statusBar().showMessage(status_message)

    def export_json(self) -> None:
        default_name = "canvas.json"
        if self.state.current_document is not None:
            default_name = f"{Path(self.state.current_document.file_path).stem}_canvas.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Canvas JSON",
            default_name,
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        try:
            export_canvas_json(
                file_path=file_path,
                dbc_file=(
                    self.state.current_document.file_path
                    if self.state.current_document is not None
                    else None
                ),
                nodes=self.node_canvas.export_nodes(),
                links=self.node_canvas.export_links() or None,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        self.state.current_canvas_file = file_path
        self.state.has_unsaved_changes = False
        self._update_title()
        self.statusBar().showMessage(f"Exported canvas JSON to {file_path}")

    def _convert(self) -> None:
        script_path = self._select_converter()
        if not script_path:
            QMessageBox.information(
                self, "No Converter",
                "Please load a converter script first (Tools → Load Converter Script).",
            )
            return

        canvas_data = self._build_canvas_data()
        if not canvas_data.get("messages") and not canvas_data.get("custom_nodes"):
            self.statusBar().showMessage("Nothing to convert — canvas is empty.")
            return

        output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not output_dir:
            return

        self.convert_action.setEnabled(False)
        self._progress_bar.setMaximum(0)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)
        self.statusBar().showMessage("Conversion started...")

        self._convert_worker = ConvertWorker(
            canvas_data, output_dir, self.converter_manager, script_path, self
        )
        self._convert_worker.progress.connect(self._on_convert_progress)
        self._convert_worker.finished.connect(self._on_convert_finished)
        self._convert_worker.start()

    def _on_convert_progress(self, current: int, total: int, message: str) -> None:
        if total > 0:
            self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self.statusBar().showMessage(message)

    def _on_convert_finished(self, success: bool, output_dir: str, error: str) -> None:
        self._progress_bar.setVisible(False)
        self.convert_action.setEnabled(True)
        self._convert_worker = None

        if success:
            self.statusBar().showMessage(f"Conversion completed. Output: {output_dir}")
            QMessageBox.information(
                self, "Conversion Complete",
                f"Conversion completed successfully.\n\nOutput:\n{output_dir}",
            )
        else:
            self.statusBar().showMessage("Conversion failed.")
            QMessageBox.critical(
                self, "Conversion Failed",
                f"An error occurred:\n\n{error}",
            )

    def _load_converter_script(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Load Converter Script", "",
            "Python Files (*.py);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            name = self.converter_manager.load_script(file_path)
            if file_path not in self.state.converter_scripts:
                self.state.converter_scripts.append(file_path)
            self.statusBar().showMessage(f"Loaded converter: {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Load Failed", str(exc))

    def _remove_converter_script(self) -> None:
        scripts = self.converter_manager.get_scripts()
        if not scripts:
            QMessageBox.information(self, "No Scripts", "No converter scripts loaded.")
            return
        items = [f"{s['name']} ({s['path']})" for s in scripts]
        item, ok = QInputDialog.getItem(self, "Remove Converter", "Select script:", items, 0, False)
        if ok and item:
            idx = items.index(item)
            path = scripts[idx]["path"]
            self.converter_manager.remove_script(path)
            self.state.converter_scripts = [p for p in self.state.converter_scripts if p != path]
            self.statusBar().showMessage(f"Removed converter: {scripts[idx]['name']}")

    def _select_converter(self) -> str | None:
        scripts = self.converter_manager.get_scripts()
        if not scripts:
            return None
        if len(scripts) == 1:
            return scripts[0]["path"]
        items = [s["name"] for s in scripts]
        item, ok = QInputDialog.getItem(self, "Select Converter", "Choose converter:", items, 0, False)
        if ok and item:
            idx = items.index(item)
            return scripts[idx]["path"]
        return None

    def _build_canvas_data(self) -> dict:
        """Build the full message-grouped canvas data dict (mirrors export JSON)."""
        from app.json_exporter import _build_messages_from_canvas
        dbc_file = (
            self.state.current_document.file_path
            if self.state.current_document is not None
            else None
        )
        custom_nodes = []
        for node in self.state.custom_nodes:
            custom_nodes.append({
                "id": node.id,
                "type": "custom",
                "signal": node.name,
                "target_variable": node.target_variable,
                "description": node.description,
                "source_message": node.source_message,
                "source_signal": node.source_signal,
                "mapping_table": [{"dbc_value": m.dbc_value, "radar_value": m.radar_value} for m in node.mapping_table],
            })
        return {
            "version": 2,
            "dbc_file": dbc_file,
            "messages": _build_messages_from_canvas(dbc_file, self.node_canvas.export_nodes()),
            "custom_nodes": custom_nodes,
            "links": self.node_canvas.export_links(),
        }

    def clear_canvas(self) -> None:
        if self.node_canvas.export_nodes():
            self.node_canvas.record_history()
        self.node_canvas.clear_canvas()
        self._tree_drop_offset = 0
        self.state.has_unsaved_changes = True
        self._update_title()
        self.statusBar().showMessage("Canvas cleared.")

    def _create_custom_node(self) -> None:
        node = CustomNodeDialog.get_custom_node(self)
        if node:
            self.state.custom_nodes.append(node)
            self.dbc_tree.add_custom_node(node)
            self.state.has_unsaved_changes = True
            self._update_title()
            self.statusBar().showMessage(f"Created custom node: {node.name}")

    def _edit_custom_node(self, node_id: str) -> None:
        node = next((n for n in self.state.custom_nodes if n.id == node_id), None)
        if not node:
            return
        updated = CustomNodeDialog.get_custom_node(self, current_node=node)
        if updated:
            idx = next(i for i, n in enumerate(self.state.custom_nodes) if n.id == node_id)
            self.state.custom_nodes[idx] = updated
            self.dbc_tree.update_custom_node(updated)
            self.node_canvas.update_custom_node_data(updated)
            self.state.has_unsaved_changes = True
            self._update_title()

    def _delete_custom_node(self, node_id: str) -> None:
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Delete Custom Node",
            "Are you sure you want to delete this custom node?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.state.custom_nodes = [n for n in self.state.custom_nodes if n.id != node_id]
            self.dbc_tree.remove_custom_node(node_id)
            self.node_canvas.remove_custom_node_by_id(node_id)
            self.state.has_unsaved_changes = True
            self._update_title()

    def _import_custom_nodes(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Custom Nodes", "",
            "Custom Node Files (*.custom.json);;All Files (*.*)",
        )
        if not file_path:
            return
        try:
            nodes_data = load_custom_nodes_json(file_path)
            for data in nodes_data:
                canvas_dict = custom_node_to_canvas_dict(data)
                mapping = [MappingEntry(dbc_value=m["dbc_value"], radar_value=m["radar_value"]) for m in data.get("mapping_table", [])]
                node = CustomNode(
                    id=data.get("id", ""),
                    name=data.get("name", ""),
                    target_variable=data.get("target_variable", ""),
                    description=data.get("description", ""),
                    source_message=data.get("source_message", ""),
                    source_signal=data.get("source_signal", ""),
                    mapping_table=mapping,
                )
                self.state.custom_nodes.append(node)
                self.dbc_tree.add_custom_node(node)
            self.state.has_unsaved_changes = True
            self._update_title()
            self.statusBar().showMessage(f"Imported {len(nodes_data)} custom nodes.")
        except Exception as exc:
            QMessageBox.critical(self, "Import Failed", str(exc))

    def _export_custom_nodes(self) -> None:
        if not self.state.custom_nodes:
            QMessageBox.information(self, "No Custom Nodes", "No custom nodes to export.")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Custom Nodes", "custom_nodes.custom.json",
            "Custom Node Files (*.custom.json)",
        )
        if not file_path:
            return
        try:
            nodes_data = []
            for node in self.state.custom_nodes:
                nodes_data.append({
                    "id": node.id,
                    "name": node.name,
                    "target_variable": node.target_variable,
                    "description": node.description,
                    "source_message": node.source_message,
                    "source_signal": node.source_signal,
                    "mapping_table": [{"dbc_value": m.dbc_value, "radar_value": m.radar_value} for m in node.mapping_table],
                })
            export_custom_nodes_json(file_path, nodes_data)
            self.statusBar().showMessage(f"Exported {len(self.state.custom_nodes)} custom nodes.")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _add_signal_from_tree(self, payload: dict) -> None:
        x, y = self._next_tree_drop_position()
        self.node_canvas.add_signal_node(payload, x, y)
        self.statusBar().showMessage(
            f"Added signal {payload['signal']} from {payload['message']} to the canvas."
        )

    def _add_message_from_tree(self, payloads: list[dict]) -> None:
        if not payloads:
            return

        with self.node_canvas._batch_history():
            for payload in payloads:
                x, y = self._next_tree_drop_position()
                self.node_canvas.add_signal_node(payload, x, y)

        self.statusBar().showMessage(
            f"Added {len(payloads)} signals from {payloads[0]['message']} to the canvas."
        )

    def _next_tree_drop_position(self) -> tuple[float, float]:
        center = self.node_canvas.mapToScene(self.node_canvas.viewport().rect().center())
        offset = self._tree_drop_offset * 28
        self._tree_drop_offset = (self._tree_drop_offset + 1) % 6
        return center.x() + offset, center.y() + offset

    def _restore_document_from_canvas(self, dbc_file: str | None) -> str:
        if not dbc_file:
            self.state.current_document = None
            self.dbc_tree.clear()
            self.dbc_tree.setHeaderLabel("DBC")
            self.dbc_tree.load_custom_nodes(self.state.custom_nodes)
            self.node_canvas.set_available_condition_sources([])
            self.dbc_search.clear()
            return ""

        dbc_path = Path(dbc_file)
        if not dbc_path.exists():
            self.state.current_document = None
            self.dbc_tree.clear()
            self.dbc_tree.setHeaderLabel("DBC")
            self.dbc_tree.load_custom_nodes(self.state.custom_nodes)
            self.node_canvas.set_available_condition_sources([])
            self.dbc_search.clear()
            QMessageBox.warning(
                self,
                "DBC Not Found",
                f"The referenced DBC file was not found:\n{dbc_file}\n\nCanvas nodes were restored without the left tree.",
            )
            return "DBC file not found; tree not restored."

        try:
            document = load_dbc_document(str(dbc_path))
        except Exception as exc:
            self.state.current_document = None
            self.dbc_tree.clear()
            self.dbc_tree.setHeaderLabel("DBC")
            self.dbc_tree.load_custom_nodes(self.state.custom_nodes)
            self.node_canvas.set_available_condition_sources([])
            self.dbc_search.clear()
            QMessageBox.warning(
                self,
                "DBC Load Failed",
                f"Failed to load the DBC referenced by the canvas JSON:\n{exc}\n\nCanvas nodes were restored without the left tree.",
            )
            return "DBC load failed; tree not restored."

        self.state.current_document = document
        self.dbc_tree.load_document(document, self.state.custom_nodes)
        self.node_canvas.set_available_condition_sources(
            self._collect_condition_sources_from_document(document)
        )
        return f"DBC restored from {dbc_path.name}."

    def _collect_condition_sources_from_document(self, document) -> list[dict]:
        sources: list[dict] = []
        seen_keys = set()

        for node in document.nodes:
            for direction, messages in (("tx", node.tx_messages), ("rx", node.rx_messages)):
                for message in messages:
                    for signal in message.signals:
                        key = (message.name, signal.name)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        sources.append(
                            {
                                "source_node": node.name,
                                "direction": direction,
                                "source_message": message.name,
                                "source_signal": signal.name,
                                "frame_id": message.frame_id,
                                "start_bit": signal.start_bit,
                                "length": signal.length,
                                "byte_order": signal.byte_order,
                            }
                        )

        return sources

    def _collect_condition_sources_from_nodes(self, nodes: list[dict]) -> list[dict]:
        sources: list[dict] = []
        seen_keys = set()
        for node in nodes:
            key = (node["message"], node["signal"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            sources.append(
                {
                    "source_node": node["node"],
                    "direction": node.get("direction", "ref"),
                    "source_message": node["message"],
                    "source_signal": node["signal"],
                    "frame_id": node.get("frame_id", 0),
                    "start_bit": node.get("start_bit", 0),
                    "length": node.get("length", 0),
                    "byte_order": node.get("byte_order", "big_endian"),
                }
            )
        return sources

    def _on_canvas_changed(self) -> None:
        self.state.has_unsaved_changes = True
        self._update_title()

    def _update_title(self) -> None:
        parts = ["DBC2C"]
        if self.state.current_document is not None:
            parts.append(Path(self.state.current_document.file_path).name)
        if self.state.current_canvas_file is not None:
            parts.append(Path(self.state.current_canvas_file).name)
        if self.state.has_unsaved_changes:
            parts.append("*")
        self.setWindowTitle(" - ".join(parts))

    def _restore_window_state(self) -> None:
        geo = self._settings.value("window/geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.resize(
                int(screen.width() * 0.85),
                int(screen.height() * 0.85),
            )
            self.move(
                int((screen.width() - self.width()) / 2),
                int((screen.height() - self.height()) / 2),
            )

        splitter_sizes = self._settings.value("window/splitter_sizes")
        if splitter_sizes is not None:
            self._splitter.setSizes([int(s) for s in splitter_sizes])

        last_dbc = self._settings.value("recent/last_dbc", "")
        if last_dbc and Path(last_dbc).exists():
            try:
                self.import_dbc_silent(last_dbc)
            except Exception:
                pass

        custom_nodes_json = self._settings.value("custom_nodes", "")
        if custom_nodes_json:
            try:
                custom_nodes_data = json.loads(custom_nodes_json)
                for data in custom_nodes_data:
                    mapping = [MappingEntry(dbc_value=m["dbc_value"], radar_value=m["radar_value"]) for m in data.get("mapping_table", [])]
                    node = CustomNode(
                        id=data.get("id", ""),
                        name=data.get("name", ""),
                        target_variable=data.get("target_variable", ""),
                        description=data.get("description", ""),
                        source_message=data.get("source_message", ""),
                        source_signal=data.get("source_signal", ""),
                        mapping_table=mapping,
                    )
                    self.state.custom_nodes.append(node)
                self.dbc_tree.load_custom_nodes(self.state.custom_nodes)
            except Exception:
                pass

        links_json = self._settings.value("links", "")
        if links_json:
            try:
                links_data = json.loads(links_json)
                for data in links_data:
                    source_id = data.get("source_id", "")
                    target_id = data.get("target_id", "")
                    label = data.get("label", "")
                    link_id = data.get("id", "")
                    self.node_canvas.add_link(source_id, target_id, label, link_id)
            except Exception:
                pass

        scripts_json = self._settings.value("converter_scripts", "")
        if scripts_json:
            try:
                scripts = json.loads(scripts_json)
                for path in scripts:
                    if Path(path).exists():
                        self.converter_manager.load_script(path)
                        self.state.converter_scripts.append(path)
            except Exception:
                pass

    def _save_window_state(self) -> None:
        self._settings.setValue("window/geometry", self.saveGeometry())
        self._settings.setValue("window/splitter_sizes", self._splitter.sizes())
        if self.state.current_document is not None:
            self._settings.setValue("recent/last_dbc", self.state.current_document.file_path)
        else:
            self._settings.remove("recent/last_dbc")
        custom_nodes_data = []
        for node in self.state.custom_nodes:
            custom_nodes_data.append({
                "id": node.id,
                "name": node.name,
                "target_variable": node.target_variable,
                "description": node.description,
                "source_message": node.source_message,
                "source_signal": node.source_signal,
                "mapping_table": [{"dbc_value": m.dbc_value, "radar_value": m.radar_value} for m in node.mapping_table],
            })
        self._settings.setValue("custom_nodes", json.dumps(custom_nodes_data))
        links_data = self.node_canvas.export_links()
        self._settings.setValue("links", json.dumps(links_data))
        self._settings.setValue("converter_scripts", json.dumps(self.state.converter_scripts))

    def closeEvent(self, event) -> None:
        if self._convert_worker is not None and self._convert_worker.isRunning():
            self._convert_worker.cancel()
            self._convert_worker.wait(3000)

        if self.state.has_unsaved_changes:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self.export_json()
                if self.state.has_unsaved_changes:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
        self._save_window_state()
        super().closeEvent(event)

    def import_dbc_silent(self, file_path: str) -> None:
        """Load a DBC file without dialog or status message (for auto-restore)."""
        document = load_dbc_document(file_path)
        self.state.current_document = document
        self.dbc_tree.load_document(document, self.state.custom_nodes)
        self.node_canvas.set_available_condition_sources(
            self._collect_condition_sources_from_document(document)
        )
        self._update_title()
        self.statusBar().showMessage(
            f"Restored {Path(file_path).name}. Drag signals to the canvas."
        )


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
