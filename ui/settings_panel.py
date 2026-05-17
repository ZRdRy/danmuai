from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config_store import ConfigStore
from app.personae import persona_display_name
from app.translations import tr, Translator
from ui.custom_model_dialog import CustomModelDialog
from ui.theme import CHECKBOX_STYLE, DANGER_BUTTON, INPUT_STYLE, PRIMARY_BUTTON, SECONDARY_BUTTON, make_card, make_page_container, make_page_title, wrap_scroll

DANGER_BUTTON_SMALL = """
QPushButton {
    background: transparent;
    border: 1px solid #ef4444;
    border-radius: 6px;
    color: #ef4444;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton:hover {
    background: #fef2f2;
}
"""

SMALL_BUTTON = """
QPushButton {
    background: transparent;
    border: 1px solid #d1dbe7;
    border-radius: 6px;
    color: #4c5f75;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton:hover {
    background: #f7faff;
    border-color: #bfcbdb;
}
"""


class SettingsPanel(QWidget):
    def __init__(self, config: ConfigStore, app=None):
        super().__init__()
        self.config = config
        self.app = app
        self.custom_models: list = []
        self.default_model_id: str = ""
        self._build()
        self._load_values()

    def _build(self):
        container, layout = make_page_container()

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(16)

        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #102033;")
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 13px; color: #4c5f75;")
        text_layout.addWidget(self.subtitle_label)

        title_row.addWidget(text_box)
        title_row.addStretch()

        self.lang_btn = QPushButton()
        self.lang_btn.setStyleSheet(SECONDARY_BUTTON)
        self.lang_btn.clicked.connect(self._toggle_language)
        title_row.addWidget(self.lang_btn, 0, Qt.AlignmentFlag.AlignTop)

        self.save_btn = QPushButton()
        self.save_btn.setStyleSheet(PRIMARY_BUTTON)
        self.save_btn.clicked.connect(self._save)
        title_row.addWidget(self.save_btn, 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(title_row)

        self.api_card, self.api_body = make_card("", "")
        self.api_card_title = None
        self.api_card_subtitle = None
        for child in self.api_card.findChildren(QLabel):
            if self.api_card_title is None:
                self.api_card_title = child
            else:
                self.api_card_subtitle = child
        self.api_form = QFormLayout()
        self.api_form.setHorizontalSpacing(18)
        self.api_form.setVerticalSpacing(14)

        self.endpoint_edit = QLineEdit()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["doubao", "openai"])

        for widget in (
            self.endpoint_edit,
            self.key_edit,
            self.mode_combo,
        ):
            widget.setStyleSheet(INPUT_STYLE)

        self.api_endpoint_label = QLabel()
        self.api_form.addRow(self.api_endpoint_label, self.endpoint_edit)
        self.api_key_label = QLabel()
        self.api_form.addRow(self.api_key_label, self.key_edit)
        self.api_mode_label = QLabel()
        self.api_form.addRow(self.api_mode_label, self.mode_combo)
        self.api_body.addLayout(self.api_form)
        layout.addWidget(self.api_card)

        self.model_card, self.model_body = make_card("", "")
        self.model_card_title = None
        self.model_card_subtitle = None
        for child in self.model_card.findChildren(QLabel):
            if self.model_card_title is None:
                self.model_card_title = child
            else:
                self.model_card_subtitle = child
        self.model_form = QFormLayout()
        self.model_form.setHorizontalSpacing(18)
        self.model_form.setVerticalSpacing(14)

        self.model_combo = QComboBox()
        self.model_combo.addItem("doubao-seed-1-6-flash-250828")
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.1)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(10, 2000)

        for widget in (
            self.model_combo,
            self.temp_spin,
            self.max_tokens_spin,
        ):
            widget.setStyleSheet(INPUT_STYLE)

        self.model_current_label = QLabel()
        self.model_form.addRow(self.model_current_label, self.model_combo)
        self.model_temp_label = QLabel()
        self.model_form.addRow(self.model_temp_label, self.temp_spin)
        self.model_tokens_label = QLabel()
        self.model_form.addRow(self.model_tokens_label, self.max_tokens_spin)
        self.model_body.addLayout(self.model_form)
        layout.addWidget(self.model_card)

        self.custom_model_card, self.custom_model_body = make_card("", "")
        self.custom_model_card_title = None
        self.custom_model_card_subtitle = None
        for child in self.custom_model_card.findChildren(QLabel):
            if self.custom_model_card_title is None:
                self.custom_model_card_title = child
            else:
                self.custom_model_card_subtitle = child

        add_btn_row = QHBoxLayout()
        self.add_model_btn = QPushButton()
        self.add_model_btn.setStyleSheet(PRIMARY_BUTTON)
        self.add_model_btn.clicked.connect(self._on_add_model)
        add_btn_row.addWidget(self.add_model_btn)
        add_btn_row.addStretch()
        self.custom_model_body.addLayout(add_btn_row)

        self.model_list_container = QWidget()
        self.model_list_layout = QVBoxLayout(self.model_list_container)
        self.model_list_layout.setContentsMargins(0, 0, 0, 0)
        self.model_list_layout.setSpacing(8)
        self.custom_model_body.addWidget(self.model_list_container)

        self.empty_label = QLabel()
        self.empty_label.setStyleSheet("font-size: 12px; color: #7c8da4; padding: 16px;")
        self.model_list_layout.addWidget(self.empty_label)
        self.model_list_layout.addStretch()

        layout.addWidget(self.custom_model_card)

        self.capture_card, self.capture_body = make_card("", "")
        self.capture_card_title = None
        self.capture_card_subtitle = None
        for child in self.capture_card.findChildren(QLabel):
            if self.capture_card_title is None:
                self.capture_card_title = child
            else:
                self.capture_card_subtitle = child
        self.privacy_warning = QLabel()
        self.privacy_warning.setWordWrap(True)
        self.privacy_warning.setStyleSheet(
            """
            QLabel {
                background: #fff4db;
                border: 1px solid #f0dfa4;
                border-radius: 14px;
                padding: 14px 16px;
                color: #9a6700;
                font-size: 12px;
                line-height: 1.7;
            }
            """
        )
        self.capture_body.addWidget(self.privacy_warning)

        self.capture_form = QFormLayout()
        self.capture_form.setHorizontalSpacing(18)
        self.capture_form.setVerticalSpacing(14)

        self.screen_combo = QComboBox()
        self.screen_combo.setEnabled(False)
        self.image_max_width_spin = QSpinBox()
        self.image_max_width_spin.setRange(256, 4096)
        self.image_max_width_spin.setSingleStep(128)
        self.image_max_width_spin.setSuffix(" px")
        self.image_quality_spin = QSpinBox()
        self.image_quality_spin.setRange(1, 100)
        self.image_quality_spin.setSuffix(" %")

        self.screen_combo.setStyleSheet(INPUT_STYLE)
        self.image_max_width_spin.setStyleSheet(INPUT_STYLE)
        self.image_quality_spin.setStyleSheet(INPUT_STYLE)

        self.capture_screen_label = QLabel()
        self.capture_form.addRow(self.capture_screen_label, self.screen_combo)
        self.capture_max_width_label = QLabel()
        self.capture_form.addRow(self.capture_max_width_label, self.image_max_width_spin)
        self.capture_quality_label = QLabel()
        self.capture_form.addRow(self.capture_quality_label, self.image_quality_spin)
        self.capture_body.addLayout(self.capture_form)

        self.capture_note = QLabel()
        self.capture_note.setWordWrap(True)
        self.capture_note.setStyleSheet("font-size: 12px; color: #7c8da4; line-height: 1.6;")
        self.capture_body.addWidget(self.capture_note)

        preview_divider = QLabel("")
        preview_divider.setFixedHeight(1)
        preview_divider.setStyleSheet("background: #e2e8f0;")
        self.capture_body.addWidget(preview_divider)

        self.preview_title = QLabel()
        self.preview_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #102033; margin-top: 8px;")
        self.capture_body.addWidget(self.preview_title)

        self.preview_desc = QLabel()
        self.preview_desc.setStyleSheet("font-size: 12px; color: #7c8da4;")
        self.capture_body.addWidget(self.preview_desc)

        upload_btn_row = QHBoxLayout()
        self.upload_btn = QPushButton()
        self.upload_btn.setStyleSheet(INPUT_STYLE)
        self.upload_btn.clicked.connect(self._on_upload_image)
        upload_btn_row.addWidget(self.upload_btn)
        upload_btn_row.addStretch()
        self.capture_body.addLayout(upload_btn_row)

        self.preview_info = QLabel()
        self.preview_info.setStyleSheet("font-size: 12px; color: #7c8da4;")
        self.capture_body.addWidget(self.preview_info)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMaximumHeight(300)
        self.preview_scroll.setStyleSheet("QScrollArea { border: 1px solid #e2e8f0; border-radius: 8px; background: #f8fafc; }")
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("color: #94a3b8; padding: 20px;")
        self.preview_scroll.setWidget(self.preview_label)
        self.preview_scroll.setVisible(False)
        self.capture_body.addWidget(self.preview_scroll)

        layout.addWidget(self.capture_card)

        self.danmu_card, self.danmu_body = make_card("", "")
        self.danmu_card_title = None
        self.danmu_card_subtitle = None
        for child in self.danmu_card.findChildren(QLabel):
            if self.danmu_card_title is None:
                self.danmu_card_title = child
            else:
                self.danmu_card_subtitle = child
        self.danmu_form = QFormLayout()
        self.danmu_form.setHorizontalSpacing(18)
        self.danmu_form.setVerticalSpacing(14)

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 30)
        self.interval_spin.setSuffix(tr("settings.unit_seconds"))
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(0.5, 5.0)
        self.speed_spin.setSingleStep(0.5)
        self.speed_spin.setSuffix(" x")
        self.lines_spin = QSpinBox()
        self.lines_spin.setRange(2, 12)
        self.lines_spin.setSuffix(tr("settings.unit_lines"))
        self.dedup_spin = QDoubleSpinBox()
        self.dedup_spin.setRange(0.0, 1.0)
        self.dedup_spin.setSingleStep(0.05)
        self.dedup_spin.setDecimals(2)
        self.layout_mode_combo = QComboBox()
        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(0, 100)
        self.opacity_spin.setSuffix(" %")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(12, 72)
        self.font_size_spin.setSuffix(" px")

        for widget in (
            self.interval_spin,
            self.speed_spin,
            self.lines_spin,
            self.dedup_spin,
            self.layout_mode_combo,
            self.opacity_spin,
            self.font_size_spin,
        ):
            widget.setStyleSheet(INPUT_STYLE)

        self.danmu_interval_label = QLabel()
        self.danmu_form.addRow(self.danmu_interval_label, self.interval_spin)
        self.danmu_speed_label = QLabel()
        self.danmu_form.addRow(self.danmu_speed_label, self.speed_spin)
        self.danmu_lines_label = QLabel()
        self.danmu_form.addRow(self.danmu_lines_label, self.lines_spin)
        self.danmu_dedup_label = QLabel()
        self.danmu_form.addRow(self.danmu_dedup_label, self.dedup_spin)
        self.danmu_layout_label = QLabel()
        self.danmu_form.addRow(self.danmu_layout_label, self.layout_mode_combo)
        self.danmu_opacity_label = QLabel()
        self.danmu_form.addRow(self.danmu_opacity_label, self.opacity_spin)
        self.danmu_font_size_label = QLabel()
        self.danmu_form.addRow(self.danmu_font_size_label, self.font_size_spin)
        self.danmu_body.addLayout(self.danmu_form)
        layout.addWidget(self.danmu_card)

        self.freq_card, self.freq_body = make_card("", "")
        self.freq_card_title = None
        self.freq_card_subtitle = None
        for child in self.freq_card.findChildren(QLabel):
            if self.freq_card_title is None:
                self.freq_card_title = child
            else:
                self.freq_card_subtitle = child
        mode_row = QHBoxLayout()
        self.freq_auto_check = QCheckBox()
        self.freq_manual_check = QCheckBox()
        self.freq_auto_check.setChecked(True)
        self.freq_auto_check.toggled.connect(self._on_freq_mode_changed)
        self.freq_manual_check.toggled.connect(self._on_manual_toggled)

        checkbox_style = """
        QCheckBox {
            color: #102033;
            font-size: 13px;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
            border-radius: 5px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
        }
        QCheckBox::indicator:hover {
            border-color: #93c5fd;
        }
        QCheckBox::indicator:checked {
            background: #2563eb;
            border: 1px solid #2563eb;
        }
        """
        self.freq_auto_check.setStyleSheet(checkbox_style)
        self.freq_manual_check.setStyleSheet(checkbox_style)
        mode_row.addWidget(self.freq_auto_check)
        mode_row.addWidget(self.freq_manual_check)
        mode_row.addStretch()
        self.freq_body.addLayout(mode_row)

        self.freq_form = QFormLayout()
        self.freq_form.setHorizontalSpacing(18)
        self.freq_form.setVerticalSpacing(14)

        self.capture_mode_combo = QComboBox()
        self.max_on_screen_spin = QSpinBox()
        self.max_on_screen_spin.setRange(0, 50)
        self.max_on_screen_spin.setSuffix(tr("settings.unit_items"))
        self.freshness_combo = QComboBox()
        self.drop_stale_check = QCheckBox()
        self.empty_accel_check = QCheckBox()
        self.eviction_combo = QComboBox()

        for widget in (
            self.capture_mode_combo,
            self.max_on_screen_spin,
            self.freshness_combo,
            self.eviction_combo,
        ):
            widget.setStyleSheet(INPUT_STYLE)
        for widget in (self.drop_stale_check, self.empty_accel_check):
            widget.setStyleSheet(CHECKBOX_STYLE)

        self.freq_capture_mode_label = QLabel()
        self.freq_form.addRow(self.freq_capture_mode_label, self.capture_mode_combo)
        self.freq_max_on_screen_label = QLabel()
        self.freq_form.addRow(self.freq_max_on_screen_label, self.max_on_screen_spin)
        self.freq_freshness_label = QLabel()
        self.freq_form.addRow(self.freq_freshness_label, self.freshness_combo)
        self.freq_eviction_label = QLabel()
        self.freq_form.addRow(self.freq_eviction_label, self.eviction_combo)
        self.freq_body.addLayout(self.freq_form)
        self.freq_body.addWidget(self.drop_stale_check)
        self.freq_body.addWidget(self.empty_accel_check)

        self.freq_hint_label = QLabel()
        self.freq_hint_label.setWordWrap(True)
        self.freq_hint_label.setStyleSheet("font-size: 12px; color: #7c8da4; line-height: 1.6;")
        self.freq_body.addWidget(self.freq_hint_label)
        layout.addWidget(self.freq_card)

        self.persona_card, self.persona_body = make_card("", "")
        self.persona_card_title = None
        self.persona_card_subtitle = None
        for child in self.persona_card.findChildren(QLabel):
            if self.persona_card_title is None:
                self.persona_card_title = child
            else:
                self.persona_card_subtitle = child
        self.persona_scroll = QWidget()
        self.persona_layout = QVBoxLayout(self.persona_scroll)
        self.persona_layout.setContentsMargins(8, 8, 8, 8)
        self.persona_layout.setSpacing(6)
        self.persona_checkboxes: list[QCheckBox] = []

        self.persona_body.addWidget(self.persona_scroll)
        layout.addWidget(self.persona_card)

        layout.addStretch()

        scroll = wrap_scroll(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _retranslate_ui(self):
        self.title_label.setText(tr("settings.title"))
        self.subtitle_label.setText(tr("settings.subtitle"))
        self.lang_btn.setText(tr("settings.lang"))
        self.save_btn.setText(tr("settings.save"))

        if self.api_card_title:
            self.api_card_title.setText(tr("api.title"))
        if self.api_card_subtitle:
            self.api_card_subtitle.setText(tr("api.subtitle"))
        self.api_endpoint_label.setText(tr("api.endpoint"))
        self.api_key_label.setText(tr("api.key"))
        self.api_mode_label.setText(tr("api.mode"))

        if self.model_card_title:
            self.model_card_title.setText(tr("model.title"))
        if self.model_card_subtitle:
            self.model_card_subtitle.setText(tr("model.subtitle"))
        self.model_current_label.setText(tr("model.current"))
        self.model_temp_label.setText(tr("model.temperature"))
        self.model_tokens_label.setText(tr("model.max_tokens"))

        if self.custom_model_card_title:
            self.custom_model_card_title.setText(tr("custom_model.title"))
        if self.custom_model_card_subtitle:
            self.custom_model_card_subtitle.setText(tr("custom_model.subtitle"))
        self.add_model_btn.setText(tr("custom_model.add"))
        self.empty_label.setText(tr("custom_model.empty"))

        if self.capture_card_title:
            self.capture_card_title.setText(tr("capture.title"))
        if self.capture_card_subtitle:
            self.capture_card_subtitle.setText(tr("capture.subtitle"))
        self.privacy_warning.setText(tr("capture.privacy_warning"))
        self.capture_screen_label.setText(tr("capture.screen"))
        self.capture_max_width_label.setText(tr("capture.max_width"))
        self.capture_quality_label.setText(tr("capture.quality"))
        self.capture_note.setText(tr("capture.note"))
        self.preview_title.setText(tr("capture.preview"))
        self.preview_desc.setText(tr("capture.preview_desc"))
        self.upload_btn.setText(tr("capture.select_image"))
        self.preview_info.setText(tr("capture.no_image"))
        self.preview_label.setText(tr("capture.preview_area"))
        self.interval_spin.setSuffix(tr("settings.unit_seconds"))
        self.lines_spin.setSuffix(tr("settings.unit_lines"))
        self.max_on_screen_spin.setSuffix(tr("settings.unit_items"))

        if self.danmu_card_title:
            self.danmu_card_title.setText(tr("danmu.title"))
        if self.danmu_card_subtitle:
            self.danmu_card_subtitle.setText(tr("danmu.subtitle"))
        self.danmu_interval_label.setText(tr("danmu.interval"))
        self.danmu_speed_label.setText(tr("danmu.speed"))
        self.danmu_lines_label.setText(tr("danmu.lines"))
        self.danmu_dedup_label.setText(tr("danmu.dedup"))
        self.danmu_layout_label.setText(tr("danmu.layout"))
        self.danmu_opacity_label.setText(tr("danmu.opacity"))
        self.danmu_font_size_label.setText(tr("danmu.font_size"))

        layout_idx = self.layout_mode_combo.currentIndex()
        self.layout_mode_combo.clear()
        self.layout_mode_combo.addItems([
            tr("danmu.layout_fullscreen"),
            tr("danmu.layout_3_4"),
            tr("danmu.layout_1_2"),
            tr("danmu.layout_1_4"),
        ])
        self.layout_mode_combo.setCurrentIndex(layout_idx)

        if self.freq_card_title:
            self.freq_card_title.setText(tr("freq.title"))
        if self.freq_card_subtitle:
            self.freq_card_subtitle.setText(tr("freq.subtitle"))
        self.freq_auto_check.setText(tr("freq.auto"))
        self.freq_manual_check.setText(tr("freq.manual"))
        self.freq_capture_mode_label.setText(tr("freq.capture_mode"))
        self.freq_max_on_screen_label.setText(tr("freq.max_on_screen"))
        self.freq_freshness_label.setText(tr("freq.freshness"))
        self.freq_eviction_label.setText(tr("freq.eviction"))
        self.drop_stale_check.setText(tr("freq.drop_stale"))
        self.empty_accel_check.setText(tr("freq.empty_accel"))
        self.freq_hint_label.setText(tr("freq.hint"))

        capture_idx = self.capture_mode_combo.currentIndex()
        self.capture_mode_combo.clear()
        self.capture_mode_combo.addItems([
            tr("freq.capture_continuous"),
            tr("freq.capture_smart"),
        ])
        self.capture_mode_combo.setCurrentIndex(capture_idx)
        self.capture_mode_combo.setToolTip(tr("freq.capture_smart"))

        freshness_idx = self.freshness_combo.currentIndex()
        self.freshness_combo.clear()
        self.freshness_combo.addItems([
            tr("freq.freshness_loose"),
            tr("freq.freshness_medium"),
            tr("freq.freshness_strict"),
        ])
        self.freshness_combo.setCurrentIndex(freshness_idx)

        eviction_idx = self.eviction_combo.currentIndex()
        self.eviction_combo.clear()
        self.eviction_combo.addItems([
            tr("freq.eviction_natural"),
            tr("freq.eviction_accelerate"),
        ])
        self.eviction_combo.setCurrentIndex(eviction_idx)

        if self.persona_card_title:
            self.persona_card_title.setText(tr("persona.title"))
        if self.persona_card_subtitle:
            self.persona_card_subtitle.setText(tr("persona.subtitle"))

        current_screen_index = self.screen_combo.currentIndex()
        self.screen_combo.clear()
        for index, screen in enumerate(QApplication.screens()):
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            phys_w = int(geo.width() * dpr)
            phys_h = int(geo.height() * dpr)
            self.screen_combo.addItem(
                tr("settings.screen_label").format(index=index + 1, width=phys_w, height=phys_h)
            )
        if 0 <= current_screen_index < self.screen_combo.count():
            self.screen_combo.setCurrentIndex(current_screen_index)

        for cb in self.persona_checkboxes:
            internal_name = cb.property("persona_name") or cb.text()
            cb.setText(persona_display_name(internal_name))

        self._refresh_custom_models()

    def refresh(self):
        self._load_values()

    def _on_manual_toggled(self, checked):
        if checked:
            self.freq_auto_check.setChecked(False)
        self._on_freq_mode_changed()

    def _load_values(self):
        self.endpoint_edit.setText(self.config.get("api_endpoint", "https://ark.cn-beijing.volces.com/api/v3"))
        self.key_edit.setText(self.config.get_api_key())
        self.model_combo.setCurrentText(self.config.get("model", "doubao-seed-1-6-flash-250828"))
        self.mode_combo.setCurrentText(self.config.get("api_mode", "doubao"))
        self.temp_spin.setValue(self.config.get_float("temperature", 0.7))
        self.max_tokens_spin.setValue(self.config.get_int("max_tokens", 200))
        self.interval_spin.setValue(self.config.get_int("screenshot_interval", 3))
        self.speed_spin.setValue(self.config.get_float("danmu_speed", 2.2))
        self.lines_spin.setValue(self.config.get_int("danmu_lines", 6))
        self.dedup_spin.setValue(self.config.get_float("dedup_threshold", 0.85))

        freq_mode = self.config.get("freq_mode", "auto")
        self.freq_auto_check.setChecked(freq_mode == "auto")
        self.freq_manual_check.setChecked(freq_mode != "auto")

        capture_map = {"continuous": 0, "smart": 1}
        self.capture_mode_combo.setCurrentIndex(capture_map.get(self.config.get("capture_mode", "continuous"), 0))
        self.max_on_screen_spin.setValue(self.config.get_int("max_on_screen", 0))
        freshness_map = {"loose": 0, "medium": 1, "strict": 2}
        self.freshness_combo.setCurrentIndex(freshness_map.get(self.config.get("freshness", "medium"), 1))
        self.drop_stale_check.setChecked(self.config.get("drop_stale", "1") == "1")
        self.empty_accel_check.setChecked(self.config.get("empty_accel", "1") == "1")
        eviction_map = {"natural": 0, "accelerate": 1}
        self.eviction_combo.setCurrentIndex(eviction_map.get(self.config.get("eviction_mode", "natural"), 0))

        layout_mode = self.config.get("layout_mode", "fullscreen")
        mode_map = {"fullscreen": 0, "3/4": 1, "1/2": 2, "1/4": 3}
        self.layout_mode_combo.setCurrentIndex(mode_map.get(layout_mode, 0))
        self.opacity_spin.setValue(self.config.get_int("opacity", 100))
        self.font_size_spin.setValue(self.config.get_int("font_size", 24))

        self.screen_combo.clear()
        screens = QApplication.screens()
        current_idx = self.config.get_int("screen_index", 0)
        for index, screen in enumerate(screens):
            geo = screen.geometry()
            dpr = screen.devicePixelRatio()
            phys_w = int(geo.width() * dpr)
            phys_h = int(geo.height() * dpr)
            label = tr("settings.screen_label").format(index=index + 1, width=phys_w, height=phys_h)
            self.screen_combo.addItem(label)
        self.screen_combo.setCurrentIndex(current_idx if current_idx < self.screen_combo.count() else 0)
        self.image_max_width_spin.setValue(self.config.get_int("image_max_width", 768))
        self.image_quality_spin.setValue(self.config.get_int("image_quality", 100))

        if self.app and hasattr(self.app, "personae"):
            names = self.app.personae.list()
            active = set(self.app.personae.get_active())

            for cb in self.persona_checkboxes:
                cb.deleteLater()
            self.persona_checkboxes.clear()

            for name in names:
                cb = QCheckBox(persona_display_name(name))
                cb.setProperty("persona_name", name)
                cb.setChecked(name in active)
                cb.setStyleSheet("font-size: 13px; padding: 6px 4px;")
                self.persona_layout.addWidget(cb)
                self.persona_checkboxes.append(cb)

            self.persona_layout.addStretch()

        self._on_freq_mode_changed()

        self.custom_models = self.config.get_custom_models()
        self.default_model_id = self.config.get_default_model_id()
        self._refresh_custom_models()
        self._refresh_model_combo()

        self.current_lang = Translator.resolve_language(self.config.get("language", ""))
        Translator.set_language(self.current_lang)
        self._retranslate_ui()

    def _toggle_language(self):
        self.current_lang = "en" if self.current_lang == "zh" else "zh"
        Translator.set_language(self.current_lang)
        self._retranslate_ui()
        self.config.set("language", self.current_lang)

    def _on_freq_mode_changed(self):
        is_auto = self.freq_auto_check.isChecked()
        self.max_on_screen_spin.setEnabled(is_auto)
        self.freshness_combo.setEnabled(is_auto)
        self.drop_stale_check.setEnabled(is_auto)
        self.empty_accel_check.setEnabled(is_auto)
        self.eviction_combo.setEnabled(is_auto)
        self.interval_spin.setEnabled(not is_auto)
        self.freq_hint_label.setVisible(is_auto)

    def _save(self):
        mode_map = {0: "fullscreen", 1: "3/4", 2: "1/2", 3: "1/4"}
        capture_mode_map = {0: "continuous", 1: "smart"}
        freshness_map = {0: "loose", 1: "medium", 2: "strict"}
        eviction_map = {0: "natural", 1: "accelerate"}
        freq_mode = "auto" if self.freq_auto_check.isChecked() else "manual"

        items = {
            "api_endpoint": self.endpoint_edit.text().strip(),
            "api_mode": self.mode_combo.currentText(),
            "temperature": str(self.temp_spin.value()),
            "max_tokens": str(self.max_tokens_spin.value()),
            "screenshot_interval": str(self.interval_spin.value()),
            "danmu_speed": str(self.speed_spin.value()),
            "danmu_lines": str(self.lines_spin.value()),
            "dedup_threshold": str(self.dedup_spin.value()),
            "screen_index": str(self.screen_combo.currentIndex()),
            "hotkey": self.config.get("hotkey", "Ctrl+Shift+B"),
            "layout_mode": mode_map.get(self.layout_mode_combo.currentIndex(), "fullscreen"),
            "opacity": str(self.opacity_spin.value()),
            "font_size": str(self.font_size_spin.value()),
            "freq_mode": freq_mode,
            "capture_mode": capture_mode_map.get(self.capture_mode_combo.currentIndex(), "continuous"),
            "max_on_screen": str(self.max_on_screen_spin.value()),
            "freshness": freshness_map.get(self.freshness_combo.currentIndex(), "medium"),
            "drop_stale": "1" if self.drop_stale_check.isChecked() else "0",
            "empty_accel": "1" if self.empty_accel_check.isChecked() else "0",
            "eviction_mode": eviction_map.get(self.eviction_combo.currentIndex(), "natural"),
            "image_max_width": str(self.image_max_width_spin.value()),
            "image_quality": str(self.image_quality_spin.value()),
        }

        self.config.set_api_key(self.key_edit.text().strip())
        self.config.set_batch(items)

        self.config.set_custom_models(self.custom_models)
        selected_model_id = self.model_combo.currentText().strip()
        self.config.set_default_model_id(selected_model_id)
        self.config.set("model", selected_model_id)

        selected = [cb.property("persona_name") for cb in self.persona_checkboxes if cb.isChecked()]
        if not selected:
            selected = ["路人惊讶型"]
        if self.app and hasattr(self.app, "personae"):
            self.app.personae.set_active(selected)
        if self.app and hasattr(self.app, "config_changed"):
            self.app.config_changed.emit()

        QMessageBox.information(self, tr("common.done"), tr("common.saved"))

    def _on_upload_image(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("capture.select_image"),
            "",
            tr("settings.image_file_filter")
        )
        if not file_path:
            return

        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            self.preview_info.setText(tr("settings.preview_load_failed"))
            self.preview_info.setStyleSheet("font-size: 12px; color: #b42318;")
            return

        orig_width = pixmap.width()
        orig_height = pixmap.height()

        max_width = self.image_max_width_spin.value()
        quality = self.image_quality_spin.value()

        if orig_width > max_width:
            ratio = max_width / orig_width
            new_height = int(orig_height * ratio)
            scaled_pixmap = pixmap.scaled(
                max_width, new_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            final_width = scaled_pixmap.width()
            final_height = scaled_pixmap.height()
        else:
            scaled_pixmap = pixmap
            final_width = orig_width
            final_height = orig_height

        import io
        import base64
        from PIL import Image

        qimage = scaled_pixmap.toImage()
        width, height = qimage.width(), qimage.height()
        bits = qimage.bits()
        bits.setsize(height * qimage.bytesPerLine())
        pil_image = Image.frombuffer("RGBA", (width, height), bits, "raw", "BGRA", qimage.bytesPerLine(), 1)
        pil_image = pil_image.convert("RGB")

        buf = io.BytesIO()
        pil_image.save(buf, format="JPEG", quality=quality)
        compressed_size = len(buf.getvalue())
        b64_size = len(base64.b64encode(buf.getvalue()))

        self.preview_info.setText(
            tr("settings.preview_info").format(
                orig_width=orig_width,
                orig_height=orig_height,
                final_width=final_width,
                final_height=final_height,
                jpeg_kb=compressed_size / 1024,
                base64_kb=b64_size / 1024,
            )
        )
        self.preview_info.setStyleSheet("font-size: 12px; color: #12715b;")

        self.preview_label.setPixmap(scaled_pixmap)
        self.preview_label.setStyleSheet("padding: 10px;")
        self.preview_scroll.setVisible(True)

    def _refresh_custom_models(self):
        while self.model_list_layout.count() > 0:
            item = self.model_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.custom_models:
            self.empty_label = QLabel(tr("custom_model.empty"))
            self.empty_label.setStyleSheet("font-size: 12px; color: #7c8da4; padding: 16px;")
            self.model_list_layout.addWidget(self.empty_label)
            self.model_list_layout.addStretch()
            return

        for index, model in enumerate(self.custom_models):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(12)

            name_label = QLabel(model.get("name", tr("common.unnamed")))
            name_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #102033;")
            row_layout.addWidget(name_label)

            model_id_label = QLabel(model.get("modelId", ""))
            model_id_label.setStyleSheet("font-size: 11px; color: #7c8da4;")
            row_layout.addWidget(model_id_label)

            mode_label = QLabel(model.get("mode", "doubao"))
            mode_label.setStyleSheet(
                "font-size: 11px; color: #4c5f75; background: #f1f5f9; "
                "border-radius: 4px; padding: 2px 6px;"
            )
            row_layout.addWidget(mode_label)

            if model.get("modelId") == self.default_model_id:
                default_label = QLabel(tr("custom_model.default"))
                default_label.setStyleSheet("font-size: 11px; color: #16a34a; font-weight: 600;")
                row_layout.addWidget(default_label)

            row_layout.addStretch()

            edit_btn = QPushButton(tr("custom_model.edit"))
            edit_btn.setStyleSheet(SMALL_BUTTON)
            edit_btn.clicked.connect(lambda checked, idx=index: self._on_edit_model(idx))
            row_layout.addWidget(edit_btn)

            delete_btn = QPushButton(tr("custom_model.delete"))
            delete_btn.setStyleSheet(DANGER_BUTTON_SMALL)
            delete_btn.clicked.connect(lambda checked, idx=index: self._on_delete_model(idx))
            row_layout.addWidget(delete_btn)

            if model.get("modelId") != self.default_model_id:
                set_default_btn = QPushButton(tr("custom_model.set_default"))
                set_default_btn.setStyleSheet(SMALL_BUTTON)
                set_default_btn.clicked.connect(lambda checked, idx=index: self._on_set_default_model(idx))
                row_layout.addWidget(set_default_btn)

            self.model_list_layout.addWidget(row)

        self.model_list_layout.addStretch()

    def _on_add_model(self):
        dialog = CustomModelDialog(self)
        if dialog.exec():
            model_data = dialog.get_data()
            if model_data:
                self.custom_models.append(model_data)
                self._refresh_custom_models()
                self._refresh_model_combo()

    def _on_edit_model(self, index):
        if 0 <= index < len(self.custom_models):
            dialog = CustomModelDialog(self, self.custom_models[index])
            if dialog.exec():
                model_data = dialog.get_data()
                if model_data:
                    self.custom_models[index] = model_data
                    self._refresh_custom_models()
                    self._refresh_model_combo()

    def _on_delete_model(self, index):
        if 0 <= index < len(self.custom_models):
            model = self.custom_models[index]
            reply = QMessageBox.question(
                self,
                tr("custom_model.confirm_delete_title"),
                tr("custom_model.confirm_delete").format(name=model.get("name", tr("common.unnamed"))),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                if model.get("modelId") == self.default_model_id:
                    self.default_model_id = ""
                del self.custom_models[index]
                self._refresh_custom_models()
                self._refresh_model_combo()

    def _refresh_model_combo(self):
        self.model_combo.clear()
        self.model_combo.addItem("doubao-seed-1-6-flash-250828")
        for model in self.custom_models:
            model_id = model.get("modelId", "")
            if model_id:
                self.model_combo.addItem(model_id)
        if self.default_model_id:
            index = self.model_combo.findText(self.default_model_id)
            if index >= 0:
                self.model_combo.setCurrentIndex(index)

    def _on_set_default_model(self, index):
        if 0 <= index < len(self.custom_models):
            self.default_model_id = self.custom_models[index].get("modelId", "")
            self._refresh_custom_models()
            self._refresh_model_combo()
