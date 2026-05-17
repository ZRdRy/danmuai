from app.personae import PersonaManager, REPLY_CONTRACT
from app.reply_parser import normalize_reply_batch, parse_ai_reply_payload


class FakeConfig:
    def get(self, key, default=""):
        return default

    def get_json(self, key, default=None):
        return default or []

    def get_int(self, key, default=0):
        return default

    def set(self, key, value):
        pass

    def set_json(self, key, value):
        pass


def test_parse_ai_reply_payload_accepts_json_array():
    items = parse_ai_reply_payload('["第一条", "第二条"]')
    assert items == ["第一条", "第二条"]


def test_normalize_reply_batch_pads_to_five_items():
    items = normalize_reply_batch(["强相关1", "强相关2"])
    assert len(items) == 5
    assert items[:2] == ["强相关1", "强相关2"]


def test_builtin_persona_prompt_contains_release_contract():
    manager = PersonaManager(FakeConfig())
    system_pt, _ = manager.get_prompt("吐槽型")
    assert REPLY_CONTRACT in system_pt
    assert "固定返回 5 条弹幕" in system_pt
    assert "前 2 条必须强相关当前画面" in system_pt
    assert "后 3 条必须是适合直播间氛围的泛用弹幕" in system_pt
