"""W-TEST-COVER-004: AIReplyFIFOBuffer.set_max_items runtime truncation."""

from __future__ import annotations

from app.reply_queue import AIReplyFIFOBuffer, QueuedReply


def _item(i: int) -> QueuedReply:
    return QueuedReply("p", 1, i, f"line-{i}", screenshot_round=1)


def test_set_max_items_trims_oldest_when_shrinking():
    buf = AIReplyFIFOBuffer(max_items=8)
    for i in range(8):
        buf.push(_item(i))

    buf.set_max_items(2)

    assert buf.size() == 2
    assert buf.pop().content == "line-0"
    assert buf.pop().content == "line-1"
    assert buf.pop() is None


def test_set_max_items_zero_disables_trimming():
    buf = AIReplyFIFOBuffer(max_items=2)
    buf.push(_item(0))
    buf.push(_item(1))
    buf.set_max_items(0)
    buf.push(_item(2))
    assert buf.size() == 3
