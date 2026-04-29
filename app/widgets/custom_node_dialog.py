from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.models import CustomNode, MappingEntry

READONLY_BG = QColor("#f0f0f0")


class CustomNodeDialog(QDialog):
    def __init__(
        self,
        parent=None,
        current_node: CustomNode | None = None,
    ):
        super().__init__(parent)
        self._current_node = current_node
        self._result_node: CustomNode | None = None
        self._is_edit_mode = current_node is not None

        self.setWindowTitle("Create Custom Mapping Node" if current_node is None else "Edit Custom Mapping Node")
        self.setModal(True)
        self.resize(600, 400)

        self._name_edit = QLineEdit()
        self._desc_edit = QLineEdit()
        self._default_value_edit = QLineEdit()
        self._default_value_edit.setPlaceholderText("Value when DBC value not in mapping table")
        self._mapping_table = QTableWidget()
        self._mapping_table.setColumnCount(4)
        self._mapping_table.setHorizontalHeaderLabels(["DBC Value", "Radar Value", "Alias", ""])
        self._mapping_table.horizontalHeader().setStretchLastSection(True)
        self._mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._mapping_table.verticalHeader().setVisible(False)

        self._build_form()
        if current_node is not None:
            self._load_node(current_node)

    @staticmethod
    def get_custom_node(
        parent,
        current_node: CustomNode | None = None,
    ) -> CustomNode | None:
        dialog = CustomNodeDialog(parent, current_node)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._result_node
        return None

    def _build_form(self) -> None:
        add_row_btn = QPushButton("+ Add Row")
        add_row_btn.clicked.connect(lambda: self._add_mapping_row())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Name", self._name_edit)
        form.addRow("Description", self._desc_edit)
        form.addRow("Default Value", self._default_value_edit)

        if self._is_edit_mode:
            hint = QLabel("Gray columns are read-only in edit mode")
            hint.setStyleSheet("color: #666; font-size: 11px;")
        else:
            hint = QLabel("Radar Value and Alias will be read-only after creation")
            hint.setStyleSheet("color: #666; font-size: 11px;")

        mapping_layout = QVBoxLayout()
        mapping_layout.addWidget(QLabel("Mapping Table (DBC Value → Radar Value)"))
        mapping_layout.addWidget(hint)
        mapping_layout.addWidget(self._mapping_table)
        mapping_layout.addWidget(add_row_btn)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form)
        main_layout.addLayout(mapping_layout)
        main_layout.addWidget(buttons)

    def _add_mapping_row(self, dbc_value: str = "", radar_value: str = "", alias: str = "") -> None:
        row = self._mapping_table.rowCount()
        self._mapping_table.insertRow(row)

        dbc_item = QTableWidgetItem(dbc_value)
        if self._is_edit_mode:
            dbc_item.setBackground(QColor("#ffffff"))
        self._mapping_table.setItem(row, 0, dbc_item)

        radar_item = QTableWidgetItem(radar_value)
        radar_item.setBackground(READONLY_BG)
        if self._is_edit_mode:
            radar_item.setFlags(radar_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._mapping_table.setItem(row, 1, radar_item)

        alias_item = QTableWidgetItem(alias)
        alias_item.setBackground(READONLY_BG)
        if self._is_edit_mode:
            alias_item.setFlags(alias_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self._mapping_table.setItem(row, 2, alias_item)

        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(32)
        del_btn.clicked.connect(lambda checked, r=row: self._delete_mapping_row(r))
        self._mapping_table.setCellWidget(row, 3, del_btn)

    def _delete_mapping_row(self, row: int) -> None:
        if 0 <= row < self._mapping_table.rowCount():
            self._mapping_table.removeRow(row)

    def _load_node(self, node: CustomNode) -> None:
        self._name_edit.setText(node.name)
        self._desc_edit.setText(node.description)
        self._default_value_edit.setText(node.default_value)
        for entry in node.mapping_table:
            self._add_mapping_row(entry.dbc_value, entry.radar_value, entry.alias)

    def _accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a name for the custom node.")
            return

        mapping_table: list[MappingEntry] = []
        for row in range(self._mapping_table.rowCount()):
            dbc_item = self._mapping_table.item(row, 0)
            radar_item = self._mapping_table.item(row, 1)
            alias_item = self._mapping_table.item(row, 2)

            dbc_val = dbc_item.text().strip() if dbc_item else ""
            radar_val = radar_item.text().strip() if radar_item else ""
            alias_val = alias_item.text().strip() if alias_item else ""

            if not dbc_val or not radar_val or not alias_val:
                QMessageBox.warning(
                    self, "Incomplete Row",
                    f"Row {row + 1}: All fields (DBC Value, Radar Value, Alias) are required.",
                )
                return

            mapping_table.append(MappingEntry(dbc_value=dbc_val, radar_value=radar_val, alias=alias_val))

        node_id = self._current_node.id if self._current_node else uuid.uuid4().hex
        source_message = self._current_node.source_message if self._current_node else ""
        source_signal = self._current_node.source_signal if self._current_node else ""

        self._result_node = CustomNode(
            id=node_id,
            name=name,
            target_variable=name,
            description=self._desc_edit.text().strip(),
            source_message=source_message,
            source_signal=source_signal,
            mapping_table=mapping_table,
            default_value=self._default_value_edit.text().strip(),
        )
        self.accept()
