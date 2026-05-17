from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.translations import tr, Translator


SIDEBAR_STYLE = """
SidebarNavigation {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0b1320, stop:1 #0f1729);
}
"""

BRAND_BADGE_STYLE = """
QLabel#BrandBadge {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #3b82f6, stop:1 #1d4ed8);
    border-radius: 12px;
    color: #ffffff;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1px;
}
"""

BRAND_TITLE_STYLE = "color: #f1f5f9; font-size: 16px; font-weight: 700;"
BRAND_SUBTITLE_STYLE = "color: #64748b; font-size: 11px; font-weight: 500;"


class NavButton(QPushButton):
    def __init__(self, icon_text: str, label: str, parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self._label = label
        self.setText(f"{icon_text}  {label}")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            """
            QPushButton#NavButton {
                min-height: 42px;
                text-align: left;
                padding: 0 14px;
                border-radius: 10px;
                border: none;
                background: transparent;
                color: #94a3b8;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton#NavButton:hover {
                background: rgba(255, 255, 255, 0.06);
                color: #e2e8f0;
            }
            QPushButton#NavButton:checked {
                background: rgba(59, 130, 246, 0.15);
                color: #60a5fa;
                font-weight: 600;
            }
            """
        )
        self.setObjectName("NavButton")

    def set_label(self, label: str):
        self._label = label
        self.setText(f"{self._icon_text}  {label}")


class SidebarNavigation(QWidget):
    page_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(240)
        self.setStyleSheet(SIDEBAR_STYLE)
        self.setObjectName("SidebarNavigation")
        self.nav_buttons: list[NavButton] = []
        self._build()
        Translator.instance().language_changed.connect(self._retranslate_ui)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(24)

        brand = QFrame()
        brand.setObjectName("BrandCard")
        brand.setStyleSheet(
            """
            QFrame#BrandCard {
                background: rgba(255, 255, 255, 0.03);
                border-radius: 14px;
            }
            """
        )
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(14, 12, 14, 12)
        brand_layout.setSpacing(12)

        badge = QLabel("DA")
        badge.setObjectName("BrandBadge")
        badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_box = QWidget()
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        title = QLabel("DanmuAI")
        title.setStyleSheet(BRAND_TITLE_STYLE)
        self.subtitle = QLabel(tr("sidebar.brand_subtitle"))
        self.subtitle.setStyleSheet(BRAND_SUBTITLE_STYLE)
        text_layout.addWidget(title)
        text_layout.addWidget(self.subtitle)

        brand_layout.addWidget(badge)
        brand_layout.addWidget(text_box, 1)
        layout.addWidget(brand)

        nav = QWidget()
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)

        nav_items = [
            ("01", "sidebar.overview"),
            ("02", "sidebar.settings"),
            ("03", "sidebar.logs"),
            ("04", "sidebar.persona"),
        ]

        for index, (icon, key) in enumerate(nav_items):
            btn = NavButton(icon, tr(key))
            btn.clicked.connect(lambda checked, idx=index: self._on_nav_clicked(idx))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        nav_layout.addStretch()
        layout.addWidget(nav, 1)

        footer = QFrame()
        footer.setObjectName("FooterCard")
        footer.setStyleSheet(
            """
            QFrame#FooterCard {
                background: rgba(255, 255, 255, 0.03);
                border-radius: 12px;
            }
            """
        )
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(14, 12, 14, 12)
        footer_layout.setSpacing(10)

        self.chip = QLabel(tr("sidebar.desensitized"))
        self.chip.setObjectName("StatusChip")
        self.chip.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.chip.setStyleSheet(
            """
            QLabel#StatusChip {
                background: rgba(16, 185, 129, 0.12);
                color: #34d399;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            """
        )
        footer_layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignLeft)

        self.meta = QLabel(tr("sidebar.footer"))
        self.meta.setStyleSheet("color: #64748b; font-size: 11px; line-height: 1.5;")
        self.meta.setWordWrap(True)
        footer_layout.addWidget(self.meta)
        layout.addWidget(footer)

        if self.nav_buttons:
            self.nav_buttons[0].setChecked(True)

    def _retranslate_ui(self):
        nav_keys = ["sidebar.overview", "sidebar.settings", "sidebar.logs", "sidebar.persona"]
        for btn, key in zip(self.nav_buttons, nav_keys):
            btn.set_label(tr(key))
        self.subtitle.setText(tr("sidebar.brand_subtitle"))
        self.chip.setText(tr("sidebar.desensitized"))
        self.meta.setText(tr("sidebar.footer"))

    def _on_nav_clicked(self, index: int):
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        self.page_changed.emit(index)

    def set_active(self, index: int):
        if 0 <= index < len(self.nav_buttons):
            self._on_nav_clicked(index)
