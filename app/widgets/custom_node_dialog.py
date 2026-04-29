from __future__ import annotations

import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.models import CustomNode, MappingEntry


class CustomNodeDialog(QDialog):
    def __init__(
        self,
        parent=None,
        current_node: CustomNode | None = None,
    ):
        super().__init__(parent)
        self._current_node = current_node
        self._result_node: CustomNode | None = None

        self.setWindowTitle("Create Custom Mapping Node" if current_node is None else "Edit Custom Mapping Node")
        self.setModal(True)
        self.resize(520, 420)

        self._name_edit = QLineEdit()
        self._target_var_edit = QLineEdit()
        self._desc_edit = QLineEdit()
        self._length_spin = QSpinBox()
        self._length_spin.setRange(1, 64)
        self._length_spin.setValue(8)
        self._byte_order_combo = QComboBox()
        self._byte_order_combo.addItems(["Big Endian", "Little Endian"])
        self._mapping_table = QTableWidget()
        self._mapping_table.setColumnCount(3)
        self._mapping_table.setHorizontalHeaderLabels(["DBC Value", "Radar Value", ""])
        self._mapping_table.horizontalHeader().setStretchLastSection(True)
        self._mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
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
        form.addRow("Target Variable", self._target_var_edit)
        form.addRow("Description", self._desc_edit)
        form.addRow("Signal Length", self._length_spin)
        form.addRow("Byte Order", self._byte_order_combo)

        mapping_layout = QVBoxLayout()
        mapping_layout.addWidget(QLabel("Mapping Table (DBC Value → Radar Value)"))
        mapping_layout.addWidget(self._mapping_table)
        mapping_layout.addWidget(add_row_btn)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(form)
        main_layout.addLayout(mapping_layout)
        main_layout.addWidget(buttons)

    def _add_mapping_row(self, dbc_value: str = "", radar_value: str = "") -> None:
        row = self._mapping_table.rowCount()
        self._mapping_table.insertRow(row)
        self._mapping_table.setItem(row, 0, QTableWidgetItem(dbc_value))
        self._mapping_table.setItem(row, 1, QTableWidgetItem(radar_value))
        del_btn = QPushButton("✕")
        del_btn.setFixedWidth(32)
        del_btn.clicked.connect(lambda checked, r=row: self._delete_mapping_row(r))
        self._mapping_table.setCellWidget(row, 2, del_btn)

    def _delete_mapping_row(self, row: int) -> None:
        if 0 <= row < self._mapping_table.rowCount():
            self._mapping_table.removeRow(row)

    def _load_node(self, node: CustomNode) -> None:
        self._name_edit.setText(node.name)
        self._target_var_edit.setText(node.target_variable)
        self._desc_edit.setText(node.description)
        self._length_spin.setValue(node.length)
        index = self._byte_order_combo.findText(
            "Big Endian" if node.byte_order == "big_endian" else "Little Endian"
        )
        if index >= 0:
            self._byte_order_combo.setCurrentIndex(index)
        for entry in node.mapping_table:
            self._add_mapping_row(entry.dbc_value, entry.radar_value)

    def _accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Enter a name for the custom node.")
            return

        target_var = self._target_var_edit.text().strip()
        if not target_var:
            QMessageBox.warning(self, "Missing Variable", "Enter a target variable name.")
            return

        byte_order = "big_endian" if self._byte_order_combo.currentText() == "Big Endian" else "little_endian"

        mapping_table: list[MappingEntry] = []
        for row in range(self._mapping_table.rowCount()):
            dbc_item = self._mapping_table.item(row, 0)
            radar_item = self._mapping_table.item(row, 1)
            if dbc_item and radar_item:
                dbc_val = dbc_item.text().strip()
                radar_val = radar_item.text().strip()
                if dbc_val and radar_val:
                    mapping_table.append(MappingEntry(dbc_value=dbc_val, radar_value=radar_val))

        node_id = self._current_node.id if self._current_node else uuid.uuid4().hex
        source_message = self._current_node.source_message if self._current_node else ""
        source_signal = self._current_node.source_signal if self._current_node else ""

        self._result_node = CustomNode(
            id=node_id,
            name=name,
            target_variable=target_var,
            description=self._desc_edit.text().strip(),
            source_message=source_message,
            source_signal=source_signal,
            mapping_table=mapping_table,
            frame_id=self._current_node.frame_id if self._current_node else 0,
            start_bit=self._current_node.start_bit if self._current_node else 0,
            length=self._length_spin.value(),
            byte_order=byte_order,
        )
        self.accept()
