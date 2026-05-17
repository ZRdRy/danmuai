from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextCursor
from PyQt6.QtWidgets import QApplication, QCheckBox, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from app.logger import SanitizedLogger
from app.translations import tr, Translator
from ui.theme import CHECKBOX_STYLE, SECONDARY_BUTTON, make_card, make_page_container, make_page_title, wrap_scroll


class LogPanel(QWidget):
    LEVEL_COLORS = {
        "DEBUG": QColor("#7c8da4"),
        "INFO": QColor("#175cd3"),
        "WARNING": QColor("#9a6700"),
        "ERROR": QColor("#b42318"),
    }
    LEVEL_ORDER = ["DEBUG", "INFO", "WARNING", "ERROR"]

    def __init__(self, logger: SanitizedLogger):
        super().__init__()
        self.logger = logger
        self._all_logs: list[tuple[str, str]] = []
        self._filters: set[str] = {"INFO", "WARNING", "ERROR"}
        self._auto_scroll = True
        logger.log_emitted.connect(self._on_log)
        self._build()
        Translator.instance().language_changed.connect(self._retranslate_ui)

    def _build(self):
        container, layout = make_page_container()
        self.title_widget = make_page_title(
            tr("log.title"),
            tr("log.subtitle"),
        )
        layout.addWidget(self.title_widget)

        self.toolbar_card, self.toolbar_body = make_card(
            tr("log.filter_title"),
            tr("log.filter_subtitle"),
        )
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.level_label = QLabel(tr("log.level"))
        self.level_label.setStyleSheet("font-size: 13px; color: #4c5f75;")
        toolbar.addWidget(self.level_label)

        self.filter_checks = {}
        for level in self.LEVEL_ORDER:
            checkbox = QCheckBox(level)
            checkbox.setChecked(level in self._filters)
            checkbox.toggled.connect(lambda checked, lv=level: self._toggle_filter(lv, checked))
            checkbox.setStyleSheet(CHECKBOX_STYLE)
            self.filter_checks[level] = checkbox
            toolbar.addWidget(checkbox)

        toolbar.addStretch()

        self.auto_scroll_cb = QCheckBox(tr("log.auto_scroll"))
        self.auto_scroll_cb.setChecked(True)
        self.auto_scroll_cb.setStyleSheet(CHECKBOX_STYLE)
        self.auto_scroll_cb.toggled.connect(lambda checked: setattr(self, "_auto_scroll", checked))
        toolbar.addWidget(self.auto_scroll_cb)

        self.copy_btn = QPushButton(tr("log.copy_selected"))
        self.copy_btn.setStyleSheet(SECONDARY_BUTTON)
        self.copy_btn.clicked.connect(self._copy_selected)
        toolbar.addWidget(self.copy_btn)

        self.clear_btn = QPushButton(tr("log.clear"))
        self.clear_btn.setStyleSheet(SECONDARY_BUTTON)
        self.clear_btn.clicked.connect(self._clear)
        toolbar.addWidget(self.clear_btn)

        self.toolbar_body.addLayout(toolbar)
        layout.addWidget(self.toolbar_card)

        self.log_card, self.log_body = make_card(
            tr("log.realtime_title"),
            tr("log.realtime_subtitle"),
        )
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet(
            """
            QTextEdit {
                min-height: 460px;
                border: 1px solid #d9e1ec;
                border-radius: 16px;
                background: #0f172a;
                color: #dbe7f6;
                padding: 14px;
            }
            """
        )
        self.text_edit.setFont(QFont("Consolas", 10))
        self.text_edit.document().setMaximumBlockCount(10000)
        self.log_body.addWidget(self.text_edit)
        layout.addWidget(self.log_card)
        layout.addStretch()

        scroll = wrap_scroll(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _retranslate_ui(self):
        self.title_widget.setTitle(tr("log.title"))
        self.title_widget.setSubtitle(tr("log.subtitle"))
        self.toolbar_card._title_label.setText(tr("log.filter_title"))
        self.toolbar_card._subtitle_label.setText(tr("log.filter_subtitle"))
        self.level_label.setText(tr("log.level"))
        self.auto_scroll_cb.setText(tr("log.auto_scroll"))
        self.copy_btn.setText(tr("log.copy_selected"))
        self.clear_btn.setText(tr("log.clear"))
        self.log_card._title_label.setText(tr("log.realtime_title"))
        self.log_card._subtitle_label.setText(tr("log.realtime_subtitle"))

    def _on_log(self, level: str, message: str):
        self._all_logs.append((level, message))
        if level in self._filters:
            self._append_log(level, message)

    def _append_log(self, level: str, message: str):
        color = self.LEVEL_COLORS.get(level, QColor("#dbe7f6")).name()
        safe_message = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.text_edit.append(f'<span style="color:{color};">[{level}] {safe_message}</span>')
        if self._auto_scroll:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.text_edit.setTextCursor(cursor)

    def _toggle_filter(self, level: str, checked: bool):
        if checked:
            self._filters.add(level)
        else:
            self._filters.discard(level)
        self._rebuild()

    def _rebuild(self):
        self.text_edit.clear()
        for level, message in self._all_logs:
            if level in self._filters:
                self._append_log(level, message)

    def _copy_selected(self):
        text = self.text_edit.textCursor().selectedText()
        if text:
            QApplication.clipboard().setText(text)

    def _clear(self):
        self._all_logs.clear()
        self.text_edit.clear()
