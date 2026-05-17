from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget


WINDOW_STYLE = """
QMainWindow {
    background: #f4f7fb;
}
"""

PAGE_SCROLL_STYLE = """
QScrollArea {
    border: none;
    background: transparent;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 8px 0;
}
QScrollBar::handle:vertical {
    background: #c5d0df;
    border-radius: 5px;
    min-height: 40px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

CARD_STYLE = """
QFrame#Card {
    background: rgba(255, 255, 255, 0.96);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 20px;
}
"""

MUTED_CARD_STYLE = """
QFrame#MutedCard {
    background: #f8fafc;
    border: 1px solid rgba(148, 163, 184, 0.15);
    border-radius: 18px;
}
"""

PRIMARY_BUTTON = """
QPushButton {
    min-height: 40px;
    padding: 0 18px;
    border-radius: 12px;
    border: 1px solid #175cd3;
    background: #175cd3;
    color: white;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #144fb7;
    border-color: #144fb7;
}
QPushButton:disabled {
    background: #9bb5e7;
    border-color: #9bb5e7;
    color: #f3f6fb;
}
"""

SECONDARY_BUTTON = """
QPushButton {
    min-height: 40px;
    padding: 0 18px;
    border-radius: 12px;
    border: 1px solid #d1dbe7;
    background: white;
    color: #102033;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #f7faff;
    border-color: #bfcbdb;
}
QPushButton:disabled {
    color: #94a3b8;
    background: #f8fafc;
}
"""

DANGER_BUTTON = """
QPushButton {
    min-height: 40px;
    padding: 0 18px;
    border-radius: 12px;
    border: 1px solid #f1c7c2;
    background: #fff2f1;
    color: #b42318;
    font-size: 13px;
    font-weight: 600;
}
QPushButton:hover {
    background: #feeceb;
    border-color: #e5a9a1;
}
"""

INPUT_STYLE = """
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {
    min-height: 42px;
    padding: 0 14px;
    border: 1px solid #d1dbe7;
    border-radius: 12px;
    background: white;
    color: #102033;
    selection-background-color: #dbeafe;
    selection-color: #102033;
    font-size: 13px;
}
QTextEdit, QPlainTextEdit {
    padding: 12px 14px;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #175cd3;
}
QComboBox {
    padding-right: 36px;
}
QComboBox::drop-down {
    border: none;
    width: 32px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6b7d93;
    width: 10px;
    height: 6px;
}
QComboBox:hover::down-arrow {
    border-top-color: #175cd3;
}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 20px;
    border: none;
    background: transparent;
}
QDateEdit {
    padding-right: 36px;
}
QDateEdit::drop-down {
    border: none;
    width: 32px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QDateEdit::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #6b7d93;
    width: 10px;
    height: 6px;
}
QDateEdit:hover::down-arrow {
    border-top-color: #175cd3;
}
"""

TABLE_STYLE = """
QTableWidget {
    background: white;
    alternate-background-color: #f8fafc;
    border: 1px solid #d9e1ec;
    border-radius: 16px;
    gridline-color: #edf2f7;
    color: #102033;
    selection-background-color: #e8f1ff;
    selection-color: #102033;
}
QHeaderView::section {
    background: #f8fafc;
    color: #4c5f75;
    border: none;
    border-bottom: 1px solid #d9e1ec;
    padding: 12px 14px;
    font-size: 12px;
    font-weight: 700;
}
"""

LIST_STYLE = """
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QListWidget::item {
    border: 1px solid #d9e1ec;
    background: #f8fafc;
    border-radius: 12px;
    padding: 10px 12px;
    margin-bottom: 8px;
}
QListWidget::item:selected {
    background: #e8f1ff;
    border-color: #b7d0ff;
    color: #102033;
}
"""

CHECKBOX_STYLE = """
QCheckBox, QRadioButton {
    color: #102033;
    font-size: 13px;
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 18px;
    height: 18px;
}
QCheckBox::indicator {
    border: 1px solid #bfcbdb;
    border-radius: 6px;
    background: white;
}
QCheckBox::indicator:checked {
    background: #175cd3;
    border-color: #175cd3;
}
QRadioButton::indicator {
    border: 1px solid #bfcbdb;
    border-radius: 9px;
    background: white;
}
QRadioButton::indicator:checked {
    background: #175cd3;
    border-color: #175cd3;
}
"""


def wrap_scroll(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet(PAGE_SCROLL_STYLE)
    scroll.setWidget(content)
    return scroll


def make_page_container() -> tuple[QWidget, QVBoxLayout]:
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(28, 24, 28, 28)
    layout.setSpacing(18)
    return container, layout


def make_card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    card.setStyleSheet(CARD_STYLE)
    outer = QVBoxLayout(card)
    outer.setContentsMargins(22, 20, 22, 20)
    outer.setSpacing(16)

    header = QWidget()
    header_layout = QVBoxLayout(header)
    header_layout.setContentsMargins(0, 0, 0, 0)
    header_layout.setSpacing(4)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 15px; font-weight: 700; color: #102033;")
    header_layout.addWidget(title_label)

    subtitle_label = QLabel(subtitle)
    subtitle_label.setWordWrap(True)
    subtitle_label.setStyleSheet("font-size: 12px; color: #7c8da4;")
    subtitle_label.setVisible(bool(subtitle))
    header_layout.addWidget(subtitle_label)

    outer.addWidget(header)
    card._title_label = title_label
    card._subtitle_label = subtitle_label
    return card, outer


def make_page_title(title: str, subtitle: str) -> QWidget:
    block = QWidget()
    layout = QHBoxLayout(block)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(16)

    text_box = QWidget()
    text_layout = QVBoxLayout(text_box)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(4)

    title_label = QLabel(title)
    title_label.setStyleSheet("font-size: 24px; font-weight: 700; color: #102033;")
    text_layout.addWidget(title_label)

    subtitle_label = QLabel(subtitle)
    subtitle_label.setWordWrap(True)
    subtitle_label.setStyleSheet("font-size: 13px; color: #4c5f75;")
    text_layout.addWidget(subtitle_label)

    layout.addWidget(text_box)
    layout.addStretch()
    block._title_label = title_label
    block._subtitle_label = subtitle_label
    block.setTitle = lambda t: title_label.setText(t)
    block.setSubtitle = lambda s: subtitle_label.setText(s)
    return block
