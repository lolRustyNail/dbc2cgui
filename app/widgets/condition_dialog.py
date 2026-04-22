from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)


class ConditionDialog(QDialog):
    def __init__(
        self,
        available_sources: list[dict],
        current_signal: dict,
        current_condition: dict | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._all_sources = list(available_sources)
        self._current_signal = dict(current_signal)
        self._current_condition = current_condition
        self._result_condition: dict | None = None
        self._source_combo = QComboBox()
        self._source_search = QLineEdit()
        self._operator_combo = QComboBox()
        self._value_edit = QLineEdit()
        self._show_all_checkbox = QCheckBox("Show all signals")

        self.setWindowTitle("Configure Receive Condition")
        self.setModal(True)
        self.resize(560, 240)

        self._build_form()
        if current_condition is not None and not self._is_same_message_source(current_condition):
            self._show_all_checkbox.setChecked(True)
        self._populate_sources()
        self._load_condition(current_condition)

    @staticmethod
    def get_condition(
        parent,
        available_sources: list[dict],
        current_signal: dict,
        current_condition: dict | None = None,
    ) -> dict | None:
        dialog = ConditionDialog(available_sources, current_signal, current_condition, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog._result_condition
        return None

    def _build_form(self) -> None:
        self._source_search.setPlaceholderText("Filter source signals")
        self._source_search.textChanged.connect(self._populate_sources)
        self._operator_combo.addItems(["==", "!=", ">", ">=", "<", "<="])
        self._value_edit.setPlaceholderText("e.g. 1, 2, 0xFF")
        self._show_all_checkbox.toggled.connect(self._populate_sources)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QFormLayout(self)
        layout.addRow("Condition Source", self._source_combo)
        layout.addRow("Search", self._source_search)
        layout.addRow("Source Scope", self._show_all_checkbox)
        layout.addRow("Operator", self._operator_combo)
        layout.addRow("Compare Value", self._value_edit)
        layout.addRow(buttons)

    def _populate_sources(self) -> None:
        current_source = self._selected_or_current_source()
        self._source_combo.blockSignals(True)
        self._source_combo.clear()

        visible_sources = self._filtered_sources()
        for source in visible_sources:
            self._source_combo.addItem(self._source_label(source), source)

        if current_source is not None:
            for index in range(self._source_combo.count()):
                source = self._source_combo.itemData(index)
                if self._same_source(source, current_source):
                    self._source_combo.setCurrentIndex(index)
                    break

        self._source_combo.blockSignals(False)

    def _filtered_sources(self) -> list[dict]:
        search_text = self._source_search.text().strip().lower()
        sources = self._visible_sources()
        if not search_text:
            return sources

        return [
            source
            for source in sources
            if search_text in self._source_label(source).lower()
            or search_text in source.get("source_signal", "").lower()
            or search_text in source.get("source_message", "").lower()
            or search_text in source.get("source_node", "").lower()
        ]

    def _visible_sources(self) -> list[dict]:
        sources = self._normalized_sources()
        if self._show_all_checkbox.isChecked():
            return sources

        same_message_sources = [source for source in sources if self._is_same_message_source(source)]
        if same_message_sources:
            return same_message_sources
        return sources

    def _normalized_sources(self) -> list[dict]:
        sources = [source for source in self._all_sources if not self._is_current_signal(source)]
        current_source = self._selected_or_current_source()
        if current_source is not None and current_source.get("source_signal") and not any(
            self._same_source(item, current_source) for item in sources
        ):
            sources.append(current_source)

        same_message_sources = [source for source in sources if self._is_same_message_source(source)]
        other_sources = [source for source in sources if not self._is_same_message_source(source)]
        same_message_sources.sort(key=self._source_sort_key)
        other_sources.sort(key=self._source_sort_key)
        return same_message_sources + other_sources

    def _load_condition(self, current_condition: dict | None) -> None:
        if current_condition is None:
            if self._source_combo.count() > 0:
                self._source_combo.setCurrentIndex(0)
            return

        operator = current_condition.get("operator", "==")
        operator_index = self._operator_combo.findText(operator)
        if operator_index >= 0:
            self._operator_combo.setCurrentIndex(operator_index)

        self._value_edit.setText(str(current_condition.get("value", "")))

    def _accept(self) -> None:
        source = self._source_combo.currentData()
        if not source:
            QMessageBox.warning(self, "Missing Source", "Select a source signal for the receive condition.")
            return

        value = self._value_edit.text().strip()
        if not value:
            QMessageBox.warning(self, "Missing Value", "Enter a compare value for the receive condition.")
            return

        self._result_condition = {
            "source_node": source.get("source_node", ""),
            "source_message": source.get("source_message", ""),
            "source_signal": source.get("source_signal", ""),
            "operator": self._operator_combo.currentText(),
            "value": value,
        }
        self.accept()

    def _selected_or_current_source(self) -> dict | None:
        current_data = self._source_combo.currentData()
        if current_data:
            return current_data
        if self._current_condition is None:
            return None
        return {
            "source_node": self._current_condition.get("source_node", ""),
            "source_message": self._current_condition.get("source_message", ""),
            "source_signal": self._current_condition.get("source_signal", ""),
        }

    def _is_current_signal(self, source: dict) -> bool:
        return (
            source.get("source_message") == self._current_signal.get("message")
            and source.get("source_signal") == self._current_signal.get("signal")
        )

    def _is_same_message_source(self, source: dict) -> bool:
        return source.get("source_message") == self._current_signal.get("message")

    def _source_sort_key(self, source: dict) -> tuple[int, int, str, str, str]:
        signal_name = source.get("source_signal", "")
        signal_name_lower = signal_name.lower()
        current_signal = str(self._current_signal.get("signal", ""))
        current_signal_lower = current_signal.lower()
        current_tokens = {token.lower() for token in self._name_tokens(current_signal)}
        source_tokens = {token.lower() for token in self._name_tokens(signal_name)}
        shared_tokens = len(current_tokens & source_tokens)
        starts_with_current = 0 if current_signal_lower and signal_name_lower.startswith(current_signal_lower) else 1
        validity_rank = self._validity_rank(signal_name_lower)
        return (
            starts_with_current,
            validity_rank,
            -shared_tokens,
            signal_name_lower,
            source.get("source_node", "").lower(),
        )

    @staticmethod
    def _validity_rank(signal_name_lower: str) -> int:
        if "valid" in signal_name_lower or "invalid" in signal_name_lower:
            return 0
        if "state" in signal_name_lower or "status" in signal_name_lower:
            return 1
        if "flag" in signal_name_lower:
            return 2
        return 3

    @staticmethod
    def _name_tokens(name: str) -> set[str]:
        if not name:
            return set()
        return {token for token in re.split(r"[^a-zA-Z0-9]+|(?<=[a-z])(?=[A-Z])", name) if token}

    @staticmethod
    def _same_source(left: dict, right: dict) -> bool:
        return (
            left.get("source_message") == right.get("source_message")
            and left.get("source_signal") == right.get("source_signal")
        )

    def _source_label(self, source: dict) -> str:
        same_message = self._is_same_message_source(source)
        if same_message and not self._show_all_checkbox.isChecked():
            return source.get("source_signal", "")

        parts = [source.get("source_message", ""), source.get("source_signal", "")]
        if source.get("source_node"):
            parts.append(source.get("source_node", ""))
        return " / ".join(part for part in parts if part)
