"""W-STARTUP-UX-OBS-001: reply_queue overflow logging (S-016)."""

import logging

from app.reply_queue import AIReplyFIFOBuffer, QueuedReply


def _item(n: int) -> QueuedReply:
    return QueuedReply(
        persona_id="p",
        batch_index=0,
        content_index=n,
        content=f"msg-{n}",
    )


def test_trim_overflow_logs_dropped_count(caplog):
    buf = AIReplyFIFOBuffer(max_items=2)
    with caplog.at_level(logging.WARNING, logger="app.reply_queue"):
        buf.push(_item(1))
        buf.push(_item(2))
        buf.push(_item(3))

    assert buf.size() == 2
    assert any("reason=reply_queue_trim" in r.message for r in caplog.records)
    assert any("dropped=1" in r.message for r in caplog.records)


def _fallback_item(content: str = "fb") -> QueuedReply:
    return QueuedReply(
        persona_id="p",
        batch_index=0,
        content_index=0,
        content=content,
        source="fallback",
        is_fallback=True,
        replaceable=True,
    )


def _ai_item(content: str = "ai") -> QueuedReply:
    return QueuedReply(
        persona_id="p",
        batch_index=0,
        content_index=0,
        content=content,
        source="ai",
    )


def test_prepend_prefers_dropping_replaceable_fallback_over_ai_tail():
    """S-017: prepend overflow must not evict AI batches before replaceable fallback."""
    buf = AIReplyFIFOBuffer(max_items=3)
    buf.push(_ai_item("ai1"))
    buf.push(_ai_item("ai2"))
    buf.prepend_batch(
        [_fallback_item("new-fb"), _fallback_item("old-fb")],
        preserve_existing=2,
    )

    remaining = []
    while not buf.is_empty():
        remaining.append(buf.pop().content)

    assert "ai2" in remaining
    assert "old-fb" not in remaining


def test_drop_replaceable_fallbacks_removes_matching_batch():
    buf = AIReplyFIFOBuffer(max_items=8)
    buf.push(
        QueuedReply(
            "p",
            0,
            0,
            "stale-fb",
            request_id="r1",
            batch_id=7,
            source="fallback",
            is_fallback=True,
            replaceable=True,
        )
    )
    buf.push(_ai_item("keep"))
    dropped = buf.drop_replaceable_fallbacks(request_id="r1", batch_id=7)
    assert dropped == 1
    assert buf.size() == 1
    assert buf.pop().content == "keep"
