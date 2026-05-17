from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.translations import tr, Translator
from ui.theme import CARD_STYLE, MUTED_CARD_STYLE, make_card, make_page_container, make_page_title, wrap_scroll


class MetricCard(QFrame):
    def __init__(self, title: str, subtitle: str, badge_text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setStyleSheet(CARD_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 700; color: #102033;")
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet("font-size: 12px; color: #7c8da4; line-height: 1.5;")
        title_box.addWidget(self.title_label)
        title_box.addWidget(self.subtitle_label)
        top.addLayout(title_box, 1)

        self.badge = QLabel(badge_text)
        self.badge.setVisible(bool(badge_text))
        self.badge.setStyleSheet(
            """
            QLabel {
                background: #e8f1ff;
                color: #175cd3;
                border-radius: 999px;
                padding: 6px 10px;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top)

        self.value_label = QLabel("0")
        self.value_label.setStyleSheet("font-size: 34px; font-weight: 700; color: #102033;")
        layout.addWidget(self.value_label)

        self.foot_label = QLabel("")
        self.foot_label.setWordWrap(True)
        self.foot_label.setStyleSheet("font-size: 12px; color: #4c5f75; line-height: 1.5;")
        layout.addWidget(self.foot_label)

    def update_value(self, value: str, footnote: str = ""):
        self.value_label.setText(value)
        self.foot_label.setText(footnote)


class QuickActionCard(QPushButton):
    def __init__(self, title: str, description: str, variant: str = "secondary", parent=None):
        super().__init__(parent)
        self.setText("")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(88)

        if variant == "primary":
            self.setStyleSheet(
                """
                QPushButton {
                    border: none;
                    border-radius: 18px;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #175cd3, stop:1 #3b82f6);
                    text-align: left;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #144fb7, stop:1 #2563eb);
                }
                """
            )
            title_color = "#ffffff"
            desc_color = "rgba(255,255,255,0.85)"
        elif variant == "danger":
            self.setStyleSheet(
                """
                QPushButton {
                    border: 1px solid #f1c7c2;
                    border-radius: 18px;
                    background: #fff2f1;
                    text-align: left;
                }
                QPushButton:hover {
                    background: #feeceb;
                }
                """
            )
            title_color = "#b42318"
            desc_color = "#b42318"
        else:
            self.setStyleSheet(MUTED_CARD_STYLE.replace("QFrame", "QPushButton"))
            title_color = "#102033"
            desc_color = "#4c5f75"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {title_color};")
        self.desc_label = QLabel(description)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"font-size: 12px; color: {desc_color}; line-height: 1.6;")
        layout.addWidget(self.title_label)
        layout.addWidget(self.desc_label)


class ControlPanel(QWidget):
    start_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = False
        self._error_label = None
        self._api_status = "ok"
        self._build()
        Translator.instance().language_changed.connect(self._retranslate_ui)

    def _build(self):
        container, layout = make_page_container()
        self.title_widget = make_page_title(
            tr("control.title"),
            tr("control.subtitle"),
        )
        layout.addWidget(self.title_widget)

        self.status_banner = QFrame()
        self.status_banner.setObjectName("Card")
        self.status_banner.setStyleSheet(CARD_STYLE)
        banner_layout = QHBoxLayout(self.status_banner)
        banner_layout.setContentsMargins(22, 18, 22, 18)
        banner_layout.setSpacing(18)

        self.status_dot = QLabel("●")
        self.status_dot.setFixedWidth(24)
        self.status_dot.setStyleSheet("font-size: 22px; color: #94a3b8;")
        banner_layout.addWidget(self.status_dot, 0, Qt.AlignmentFlag.AlignTop)

        banner_text = QVBoxLayout()
        banner_text.setContentsMargins(0, 0, 0, 0)
        banner_text.setSpacing(4)

        self.status_title = QLabel(tr("control.status_stopped"))
        self.status_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #102033;")
        self.status_desc = QLabel(tr("control.status_stopped_desc"))
        self.status_desc.setWordWrap(True)
        self.status_desc.setStyleSheet("font-size: 13px; color: #4c5f75; line-height: 1.6;")
        banner_text.addWidget(self.status_title)
        banner_text.addWidget(self.status_desc)
        banner_layout.addLayout(banner_text, 1)

        self.status_badge = QLabel(tr("control.badge_stopped"))
        self.status_badge.setStyleSheet(
            """
            QLabel {
                background: #eef2f7;
                color: #6b7d93;
                border-radius: 999px;
                padding: 8px 12px;
                font-size: 12px;
                font-weight: 700;
            }
            """
        )
        banner_layout.addWidget(self.status_badge, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.status_banner)

        self.error_widget = QFrame()
        self.error_widget.setVisible(False)
        self.error_widget.setStyleSheet(
            """
            QFrame {
                background: #fff2f1;
                border: 1px solid #f1c7c2;
                border-radius: 18px;
            }
            """
        )
        error_layout = QHBoxLayout(self.error_widget)
        error_layout.setContentsMargins(18, 16, 18, 16)
        error_layout.setSpacing(12)
        error_icon = QLabel("!")
        error_icon.setStyleSheet("font-size: 18px; font-weight: 700; color: #b42318;")
        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("font-size: 13px; color: #b42318; line-height: 1.6;")
        error_layout.addWidget(error_icon)
        error_layout.addWidget(self._error_label, 1)
        layout.addWidget(self.error_widget)

        metric_grid = QGridLayout()
        metric_grid.setHorizontalSpacing(18)
        metric_grid.setVerticalSpacing(18)

        self.stat_danmu = MetricCard(tr("control.stat_danmu"), tr("control.stat_danmu_desc"), "5")
        self.stat_queue = MetricCard(tr("control.stat_queue"), tr("control.stat_queue_desc"), tr("control.stat_queue_desc"))
        self.stat_display = MetricCard(tr("control.stat_display"), tr("control.stat_display_desc"), "")
        self.stat_tokens = MetricCard(tr("control.stat_tokens"), tr("control.stat_tokens_desc"), "")
        self.stat_runtime = MetricCard(tr("control.stat_runtime"), tr("control.stat_runtime_desc"), "")
        metric_grid.addWidget(self.stat_danmu, 0, 0)
        metric_grid.addWidget(self.stat_queue, 0, 1)
        metric_grid.addWidget(self.stat_display, 0, 2)
        metric_grid.addWidget(self.stat_tokens, 1, 0)
        metric_grid.addWidget(self.stat_runtime, 1, 1)
        layout.addLayout(metric_grid)

        self.control_card, self.control_body = make_card(
            tr("control.quick_title"),
            tr("control.quick_subtitle"),
        )
        control_row = QHBoxLayout()
        control_row.setSpacing(12)

        self.btn_start = QuickActionCard(tr("control.start"), tr("control.start_desc"), "primary")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop = QuickActionCard(tr("control.stop"), tr("control.stop_desc"), "danger")
        self.btn_stop.clicked.connect(self._on_stop)

        control_row.addWidget(self.btn_start)
        control_row.addWidget(self.btn_stop)
        self.control_body.addLayout(control_row)
        layout.addWidget(self.control_card)
        layout.addStretch()

        scroll = wrap_scroll(container)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)
        self._update_status()

    def _retranslate_ui(self):
        self.title_widget.setTitle(tr("control.title"))
        self.title_widget.setSubtitle(tr("control.subtitle"))
        self._update_status()
        self.stat_danmu.title_label.setText(tr("control.stat_danmu"))
        self.stat_danmu.subtitle_label.setText(tr("control.stat_danmu_desc"))
        self.stat_queue.title_label.setText(tr("control.stat_queue"))
        self.stat_queue.subtitle_label.setText(tr("control.stat_queue_desc"))
        self.stat_display.title_label.setText(tr("control.stat_display"))
        self.stat_display.subtitle_label.setText(tr("control.stat_display_desc"))
        self.stat_tokens.title_label.setText(tr("control.stat_tokens"))
        self.stat_tokens.subtitle_label.setText(tr("control.stat_tokens_desc"))
        self.stat_runtime.title_label.setText(tr("control.stat_runtime"))
        self.stat_runtime.subtitle_label.setText(tr("control.stat_runtime_desc"))
        self.control_card._title_label.setText(tr("control.quick_title"))
        self.control_card._subtitle_label.setText(tr("control.quick_subtitle"))
        self.btn_start.title_label.setText(tr("control.start"))
        self.btn_start.desc_label.setText(tr("control.start_desc"))
        self.btn_stop.title_label.setText(tr("control.stop"))
        self.btn_stop.desc_label.setText(tr("control.stop_desc"))

    def _on_start(self):
        self._is_running = True
        self._update_status()
        self.start_clicked.emit()

    def _on_stop(self):
        self._is_running = False
        self._update_status()
        self.stop_clicked.emit()

    def _update_status(self):
        if not self._is_running:
            self.status_dot.setStyleSheet("font-size: 22px; color: #94a3b8;")
            self.status_title.setText(tr("control.status_stopped"))
            self.status_desc.setText(tr("control.status_stopped_desc"))
            self.status_badge.setText(tr("control.badge_stopped"))
            self.status_badge.setStyleSheet(
                """
                QLabel {
                    background: #eef2f7;
                    color: #6b7d93;
                    border-radius: 999px;
                    padding: 8px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }
                """
            )
        else:
            self.status_dot.setStyleSheet("font-size: 22px; color: #12715b;")
            self.status_title.setText(tr("control.status_running"))
            self.status_desc.setText(tr("control.status_running_desc"))
            self.status_badge.setText(tr("control.badge_running"))
            self.status_badge.setStyleSheet(
                """
                QLabel {
                    background: #e7f6f2;
                    color: #12715b;
                    border-radius: 999px;
                    padding: 8px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }
                """
            )

    def update_stats(self, danmu_count: int, queue_count: int, display_count: int, total_tokens: int = 0, runtime_seconds: float = 0.0):
        self.stat_danmu.update_value(str(danmu_count), tr("control.stat_danmu_foot"))
        self.stat_queue.update_value(str(queue_count), tr("control.stat_queue_foot"))
        self.stat_display.update_value(str(display_count), tr("control.stat_display_foot"))
        if total_tokens > 0:
            self.stat_tokens.update_value(f"{total_tokens:,}", tr("control.stat_tokens_foot"))
        else:
            self.stat_tokens.update_value("0", tr("control.stat_tokens_foot"))
        if runtime_seconds > 0:
            hours = int(runtime_seconds // 3600)
            minutes = int((runtime_seconds % 3600) // 60)
            seconds = int(runtime_seconds % 60)
            if hours > 0:
                runtime_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                runtime_str = f"{minutes}m {seconds}s"
            else:
                runtime_str = f"{seconds}s"
            self.stat_runtime.update_value(runtime_str, tr("control.stat_runtime_foot"))
        else:
            self.stat_runtime.update_value("0s", tr("control.stat_runtime_foot"))

    def set_error_status(self, message: str, is_error: bool = True):
        if not self._error_label:
            return

        if not message or not is_error:
            self.error_widget.setVisible(False)
            self._api_status = "ok"
            return

        sanitized = message
        if "base64," in sanitized:
            sanitized = sanitized.split("base64,")[0] + f"base64,...({tr('common.hidden')})"
        if "sk-" in sanitized or "ak-" in sanitized:
            sanitized = tr("common.hidden_api_key")

        self._error_label.setText(sanitized)
        self.error_widget.setVisible(True)

        lower_message = message.lower()
        if "401" in message or "403" in message or "api key" in lower_message:
            self._api_status = "auth_failed"
        elif any(keyword in message for keyword in ["超时", "timeout", "504"]):
            self._api_status = "timeout"
        elif any(keyword in message for keyword in ["频繁", "429", "rate", "many requests"]):
            self._api_status = "rate_limited"
        elif any(keyword in message for keyword in ["余额", "402", "balance"]):
            self._api_status = "balance"
        else:
            self._api_status = "error"
