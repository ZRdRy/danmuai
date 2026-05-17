from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.config_store import ConfigStore
from app.personae import (
    BUILTIN_PERSONAE,
    PersonaManager,
    default_user_prompt,
    get_reply_contract,
    persona_display_name,
    strip_reply_contract,
)
from app.templates import TemplateManager
from app.translations import tr, Translator
from ui.theme import INPUT_STYLE, LIST_STYLE, PRIMARY_BUTTON, SECONDARY_BUTTON, make_card, make_page_container, make_page_title, wrap_scroll


CONTRACT_STYLE = """
QTextEdit {
    border: 1px solid #bfdbfe;
    border-radius: 12px;
    background: #eff6ff;
    color: #1d4ed8;
    padding: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
"""

READONLY_STYLE = """
QTextEdit {
    border: 1px solid #d9e1ec;
    border-radius: 12px;
    background: #f8fafc;
    color: #64748b;
    padding: 8px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 13px;
}
"""


class TemplateEditor(QWidget):
    def __init__(self, config: ConfigStore, personae: PersonaManager):
        super().__init__()
        self.config = config
        self.templates = TemplateManager(config)
        self.personae = personae
        self.current_name = ""
        self._build()
        Translator.instance().language_changed.connect(self._retranslate_ui)

    def _build(self):
        container, layout = make_page_container()
        self.title_widget = make_page_title(
            tr("template.title"),
            tr("template.subtitle"),
        )
        layout.addWidget(self.title_widget)

        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)
        self.name_label = QLabel(tr("template.name"))
        self.name_label.setStyleSheet("font-size: 13px; color: #4c5f75;")
        top_bar.addWidget(self.name_label)

        self.name_combo = QComboBox()
        self.name_combo.currentIndexChanged.connect(lambda _: self._load_current())
        self.name_combo.setStyleSheet(INPUT_STYLE)
        top_bar.addWidget(self.name_combo, 1)

        self.new_btn = QPushButton(tr("template.new"))
        self.new_btn.setStyleSheet(SECONDARY_BUTTON)
        self.new_btn.clicked.connect(self._new_persona)
        top_bar.addWidget(self.new_btn)

        self.restore_btn = QPushButton(tr("template.restore"))
        self.restore_btn.setStyleSheet(SECONDARY_BUTTON)
        self.restore_btn.clicked.connect(self._restore_default)
        top_bar.addWidget(self.restore_btn)
        layout.addLayout(top_bar)

        content_row = QHBoxLayout()
        content_row.setSpacing(18)

        self.versions_card, self.versions_body = make_card(
            tr("template.version_title"),
            tr("template.version_subtitle"),
        )
        self.version_list = QListWidget()
        self.version_list.setStyleSheet(LIST_STYLE)
        self.version_list.itemDoubleClicked.connect(self._rollback_version)
        self.versions_body.addWidget(self.version_list)
        content_row.addWidget(self.versions_card, 1)

        editor_column = QVBoxLayout()
        editor_column.setSpacing(18)

        self.system_card, self.system_body = make_card(
            tr("template.system_title"),
            tr("template.system_subtitle"),
        )
        self.contract_view = QTextEdit()
        self.contract_view.setReadOnly(True)
        self.contract_view.setStyleSheet(CONTRACT_STYLE)
        self.contract_view.setPlainText(get_reply_contract())
        self.contract_view.setMaximumHeight(120)
        self.system_body.addWidget(self.contract_view)

        self.system_custom_edit = QTextEdit()
        self.system_custom_edit.setStyleSheet(INPUT_STYLE)
        self.system_custom_edit.setMinimumHeight(100)
        self.system_custom_edit.setPlaceholderText(tr("template.system_placeholder"))
        self.system_body.addWidget(self.system_custom_edit)
        editor_column.addWidget(self.system_card)

        self.user_card, self.user_body = make_card(
            tr("template.user_title"),
            tr("template.user_subtitle"),
        )
        self.user_edit = QTextEdit()
        self.user_edit.setReadOnly(True)
        self.user_edit.setStyleSheet(READONLY_STYLE)
        self.user_edit.setMinimumHeight(80)
        self.hint_label = QLabel(tr("template.hint"))
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("font-size: 12px; color: #7c8da4; line-height: 1.6;")
        self.user_body.addWidget(self.user_edit)
        self.user_body.addWidget(self.hint_label)
        editor_column.addWidget(self.user_card)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.save_btn = QPushButton(tr("template.save"))
        self.save_btn.setStyleSheet(PRIMARY_BUTTON)
        self.save_btn.clicked.connect(self._save)
        action_row.addStretch()
        action_row.addWidget(self.save_btn)
        editor_column.addLayout(action_row)

        content_row.addLayout(editor_column, 3)
        layout.addLayout(content_row)
        layout.addStretch()

        scroll = wrap_scroll(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        self._refresh_name_combo()
        self._load_current()

    def _retranslate_ui(self):
        self.title_widget.setTitle(tr("template.title"))
        self.title_widget.setSubtitle(tr("template.subtitle"))
        self.name_label.setText(tr("template.name"))
        self.new_btn.setText(tr("template.new"))
        self.restore_btn.setText(tr("template.restore"))
        self.versions_card._title_label.setText(tr("template.version_title"))
        self.versions_card._subtitle_label.setText(tr("template.version_subtitle"))
        self.system_card._title_label.setText(tr("template.system_title"))
        self.system_card._subtitle_label.setText(tr("template.system_subtitle"))
        self.contract_view.setPlainText(get_reply_contract())
        self.system_custom_edit.setPlaceholderText(tr("template.system_placeholder"))
        self.user_card._title_label.setText(tr("template.user_title"))
        self.user_card._subtitle_label.setText(tr("template.user_subtitle"))
        self.hint_label.setText(tr("template.hint"))
        self.save_btn.setText(tr("template.save"))
        self._refresh_name_combo()
        self._load_current()

    def _refresh_name_combo(self):
        current_name = self.current_name or self.name_combo.currentData() or self.name_combo.currentText()
        self.name_combo.blockSignals(True)
        self.name_combo.clear()
        for name in self.personae.list():
            self.name_combo.addItem(persona_display_name(name), name)
        index = self.name_combo.findData(current_name)
        if index < 0 and self.name_combo.count():
            index = 0
        if index >= 0:
            self.name_combo.setCurrentIndex(index)
        self.name_combo.blockSignals(False)

    def _load_current(self):
        current_name = self.name_combo.currentData() or self.name_combo.currentText()
        if current_name:
            self._load(current_name)

    def _set_editable(self, editable: bool):
        self.system_custom_edit.setReadOnly(not editable)
        self.system_custom_edit.setStyleSheet(INPUT_STYLE if editable else READONLY_STYLE)
        self.save_btn.setEnabled(editable)

    def _new_persona(self):
        name, ok = QInputDialog.getText(self, tr("template.new_dialog_title"), tr("template.new_dialog_label"))
        if ok and name.strip():
            name = name.strip()
            if name in self.personae.list():
                QMessageBox.warning(self, tr("template.duplicate"), tr("template.duplicate_msg"))
                return
            self.personae.save_custom(name, get_reply_contract(), default_user_prompt())
            self._refresh_name_combo()
            index = self.name_combo.findData(name)
            if index >= 0:
                self.name_combo.setCurrentIndex(index)

    def _load(self, name: str):
        self.current_name = name
        is_builtin = name in BUILTIN_PERSONAE
        system_pt, user_pt = self.templates.load(name)

        if is_builtin and not system_pt:
            system_pt, user_pt = self.personae.get_prompt(name)
            self._set_editable(False)
        elif not system_pt:
            custom = self.personae._load_custom()
            if name in custom:
                system_pt = custom[name]["system_pt"]
                user_pt = custom[name]["user_pt"]
            self._set_editable(True)
        else:
            self._set_editable(True)

        self.system_custom_edit.setPlainText(strip_reply_contract(system_pt))
        self.user_edit.setPlainText(user_pt or default_user_prompt())
        self._refresh_versions()

    def _refresh_versions(self):
        self.version_list.clear()
        for version in self.templates.versions(self.current_name):
            item = QListWidgetItem(f"v{version['version']}  {version['created_at'][:19]}")
            item.setData(Qt.ItemDataRole.UserRole, version["version"])
            self.version_list.addItem(item)

    def _rollback_version(self, item):
        version_number = item.data(Qt.ItemDataRole.UserRole)
        system_pt, user_pt = self.templates.load(self.current_name, version_number)
        self.system_custom_edit.setPlainText(strip_reply_contract(system_pt))
        self.user_edit.setPlainText(user_pt or default_user_prompt())
        self._set_editable(True)
        QMessageBox.information(self, tr("template.preview"), tr("template.preview_msg").format(version=version_number))

    def _restore_default(self):
        if self.current_name not in BUILTIN_PERSONAE:
            QMessageBox.information(self, tr("template.restore_hint"), tr("template.restore_msg"))
            return
        self.system_custom_edit.setPlainText("")
        _, user_pt = self.personae.get_prompt(self.current_name)
        self.user_edit.setPlainText(user_pt)
        self._set_editable(False)

    def _save(self):
        custom_system = self.system_custom_edit.toPlainText().strip()
        reply_contract = get_reply_contract()
        full_system = f"{reply_contract} {custom_system}".strip() if custom_system else reply_contract
        user_pt = self.user_edit.toPlainText()
        self.personae.save_custom(self.current_name, full_system, user_pt)
        self.templates.save(self.current_name, full_system, user_pt)
        self._refresh_versions()
        QMessageBox.information(
            self,
            tr("template.saved"),
            tr("template.saved_msg").format(name=persona_display_name(self.current_name)),
        )
