"""PET-016: desktop pet context menu includes quit-application action."""

from unittest.mock import Mock

from main import DanmuApp

from tests.conftest import bind_minimal_danmu_app


def test_pet_context_menu_has_quit_application_action(qapp):
    from app.pet.pet_window import PetWindow

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app)
    app.quit = Mock()
    window = PetWindow(app)
    window.show()

    menu = window._build_context_menu()
    action_texts = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert action_texts[-1] == "退出应用"

    quit_action = menu.actions()[-1]
    quit_action.trigger()
    app.quit.assert_called_once()


def test_pet_context_menu_skipped_when_click_through(qapp, monkeypatch):
    from dataclasses import replace

    from app.pet.pet_window import PetWindow

    app = DanmuApp.__new__(DanmuApp)
    bind_minimal_danmu_app(app)
    window = PetWindow(app)
    window._settings = replace(window._settings, click_through=True)

    build_mock = Mock()
    monkeypatch.setattr(window, "_build_context_menu", build_mock)

    class FakeEvent:
        @staticmethod
        def globalPos():
            return None

    window.contextMenuEvent(FakeEvent())
    build_mock.assert_not_called()
