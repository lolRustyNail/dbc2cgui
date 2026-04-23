from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from app.dbc_loader import load_dbc_document
from app.json_exporter import export_canvas_json, load_canvas_json
from app.state import AppState
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

        self.setWindowTitle("DBC2C")
        self.resize(1400, 900)

        self._build_actions()
        self._build_layout()
        self._build_shortcuts()
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

        self.reset_view_action = QAction("Reset View", self)
        self.reset_view_action.setShortcut(QKeySequence("Ctrl+0"))
        self.reset_view_action.setStatusTip("Reset canvas zoom and position")
        self.reset_view_action.triggered.connect(self.node_canvas.reset_view)

        self.convert_action = QAction("Convert", self)
        self.convert_action.setShortcut(QKeySequence("Ctrl+G"))
        self.convert_action.setStatusTip("Convert current canvas to code")
        self.convert_action.triggered.connect(self._convert)

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
        toolbar.addAction(self.convert_action)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.import_action)
        file_menu.addAction(self.import_json_action)
        file_menu.addAction(self.export_action)
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
        view_menu.addAction(self.fit_nodes_action)
        view_menu.addAction(self.reset_view_action)

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

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(8)
        left_layout.addWidget(self.dbc_search)
        left_layout.addWidget(self.dbc_tree)
        self.left_panel.setLayout(left_layout)

        splitter = QSplitter(self)
        splitter.addWidget(self.left_panel)
        splitter.addWidget(self.node_canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 1040])
        self.setCentralWidget(splitter)

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
        self.dbc_tree.load_document(document)
        self.node_canvas.set_available_condition_sources(
            self._collect_condition_sources_from_document(document)
        )
        self.dbc_search.clear()
        self.node_canvas.clear_canvas()
        self.node_canvas.clear_history()
        self.state.current_canvas_file = None
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
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))
            return

        self.state.current_canvas_file = file_path
        self._update_title()
        self.statusBar().showMessage(f"Exported canvas JSON to {file_path}")

    def _convert(self) -> None:
        """Convert the current canvas nodes to code.

        This is a stub — fill in the actual conversion logic here.
        `canvas_data` contains the full message-grouped JSON structure
        (same as what Export JSON writes to disk).
        """
        canvas_data = self._build_canvas_data()
        if not canvas_data.get("messages"):
            self.statusBar().showMessage("Nothing to convert — canvas is empty.")
            return
        # TODO: implement conversion logic using canvas_data
        self.statusBar().showMessage(
            f"Convert: received {len(canvas_data['messages'])} message(s) "
            f"with {sum(len(m['signals']) for m in canvas_data['messages'])} signal(s). "
            "(stub — no conversion logic yet)"
        )
        print("123")

    def _build_canvas_data(self) -> dict:
        """Build the full message-grouped canvas data dict (mirrors export JSON)."""
        from app.json_exporter import _build_messages_from_canvas
        dbc_file = (
            self.state.current_document.file_path
            if self.state.current_document is not None
            else None
        )
        return {
            "version": 2,
            "dbc_file": dbc_file,
            "messages": _build_messages_from_canvas(dbc_file, self.node_canvas.export_nodes()),
        }

    def clear_canvas(self) -> None:
        if self.node_canvas.export_nodes():
            self.node_canvas.record_history()
        self.node_canvas.clear_canvas()
        self._tree_drop_offset = 0
        self.statusBar().showMessage("Canvas cleared.")

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
            self.node_canvas.set_available_condition_sources([])
            self.dbc_search.clear()
            return ""

        dbc_path = Path(dbc_file)
        if not dbc_path.exists():
            self.state.current_document = None
            self.dbc_tree.clear()
            self.dbc_tree.setHeaderLabel("DBC")
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
            self.node_canvas.set_available_condition_sources([])
            self.dbc_search.clear()
            QMessageBox.warning(
                self,
                "DBC Load Failed",
                f"Failed to load the DBC referenced by the canvas JSON:\n{exc}\n\nCanvas nodes were restored without the left tree.",
            )
            return "DBC load failed; tree not restored."

        self.state.current_document = document
        self.dbc_tree.load_document(document)
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

    def _update_title(self) -> None:
        parts = ["DBC2C"]
        if self.state.current_document is not None:
            parts.append(Path(self.state.current_document.file_path).name)
        if self.state.current_canvas_file is not None:
            parts.append(Path(self.state.current_canvas_file).name)
        self.setWindowTitle(" - ".join(parts))


def run() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
