from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.translations import Translator, tr
from ui.theme import INPUT_STYLE, PRIMARY_BUTTON, SECONDARY_BUTTON


DIALOG_STYLE = """
QDialog {
    background: white;
    border-radius: 16px;
}
"""

LABEL_STYLE = """
QLabel {
    font-size: 13px;
    font-weight: 600;
    color: #102033;
}
"""

ERROR_STYLE = """
QLabel {
    font-size: 12px;
    color: #b42318;
}
"""


class CustomModelDialog(QDialog):
    def __init__(self, parent=None, model_data=None):
        super().__init__(parent)
        self.model_data = model_data or {}
        self.setFixedWidth(400)
        self.setStyleSheet(DIALOG_STYLE)
        self._setup_ui()
        self._retranslate_ui()
        if model_data:
            self.set_data(model_data)
        Translator.instance().language_changed.connect(self._retranslate_ui)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #102033;")
        layout.addWidget(self.title_label)

        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(14)

        self.name_label = QLabel()
        self.name_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.name_label)
        self.name_input = QLineEdit()
        self.name_input.setStyleSheet(INPUT_STYLE)
        form_layout.addWidget(self.name_input)

        self.model_id_label = QLabel()
        self.model_id_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.model_id_label)
        self.model_id_input = QLineEdit()
        self.model_id_input.setStyleSheet(INPUT_STYLE)
        form_layout.addWidget(self.model_id_input)

        self.mode_label = QLabel()
        self.mode_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["doubao", "openai-compatible"])
        self.mode_combo.setStyleSheet(INPUT_STYLE)
        form_layout.addWidget(self.mode_combo)

        self.endpoint_label = QLabel()
        self.endpoint_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.endpoint_label)
        self.endpoint_input = QLineEdit()
        self.endpoint_input.setStyleSheet(INPUT_STYLE)
        form_layout.addWidget(self.endpoint_input)

        self.api_key_label = QLabel()
        self.api_key_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.api_key_label)
        self.api_key_input = QLineEdit()
        self.api_key_input.setStyleSheet(INPUT_STYLE)
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.api_key_input)

        self.description_label = QLabel()
        self.description_label.setStyleSheet(LABEL_STYLE)
        form_layout.addWidget(self.description_label)
        self.description_input = QLineEdit()
        self.description_input.setStyleSheet(INPUT_STYLE)
        form_layout.addWidget(self.description_input)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(ERROR_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        form_layout.addWidget(self.error_label)

        layout.addWidget(form_widget)

        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(12)
        button_layout.addStretch()

        self.cancel_button = QPushButton()
        self.cancel_button.setStyleSheet(SECONDARY_BUTTON)
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.save_button = QPushButton()
        self.save_button.setStyleSheet(PRIMARY_BUTTON)
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)

        layout.addWidget(button_widget)

    def _retranslate_ui(self):
        is_edit = bool(self.model_data)
        self.setWindowTitle(tr("custom_model.dialog_title_edit" if is_edit else "custom_model.dialog_title"))
        self.title_label.setText(tr("custom_model.dialog_title_edit" if is_edit else "custom_model.dialog_title"))
        self.name_label.setText(tr("custom_model.name"))
        self.name_input.setPlaceholderText(tr("custom_model.name_placeholder"))
        self.model_id_label.setText(tr("custom_model.model_id"))
        self.model_id_input.setPlaceholderText(tr("custom_model.model_id_placeholder"))
        self.mode_label.setText(tr("custom_model.api_mode"))
        self.endpoint_label.setText(tr("custom_model.endpoint"))
        self.endpoint_input.setPlaceholderText(tr("custom_model.endpoint_placeholder"))
        self.api_key_label.setText(tr("custom_model.api_key"))
        self.api_key_input.setPlaceholderText(tr("custom_model.api_key_placeholder"))
        self.description_label.setText(tr("custom_model.description"))
        self.description_input.setPlaceholderText(tr("custom_model.description_placeholder"))
        self.cancel_button.setText(tr("custom_model.cancel"))
        self.save_button.setText(tr("custom_model.save"))

    def _on_save(self):
        self.error_label.hide()
        name = self.name_input.text().strip()
        model_id = self.model_id_input.text().strip()

        if not name:
            self.error_label.setText(tr("custom_model.error_name"))
            self.error_label.show()
            return

        if not model_id:
            self.error_label.setText(tr("custom_model.error_model_id"))
            self.error_label.show()
            return

        self.accept()

    def get_data(self):
        return {
            "name": self.name_input.text().strip(),
            "modelId": self.model_id_input.text().strip(),
            "mode": self.mode_combo.currentText(),
            "endpoint": self.endpoint_input.text().strip(),
            "apiKey": self.api_key_input.text().strip(),
            "description": self.description_input.text().strip(),
        }

    def set_data(self, model: dict):
        self.name_input.setText(model.get("name", ""))
        self.model_id_input.setText(model.get("modelId", ""))
        mode = model.get("mode", "doubao")
        index = self.mode_combo.findText(mode)
        if index >= 0:
            self.mode_combo.setCurrentIndex(index)
        self.endpoint_input.setText(model.get("endpoint", ""))
        self.api_key_input.setText(model.get("apiKey", ""))
        self.description_input.setText(model.get("description", ""))
