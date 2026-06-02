import time

from app.mic_buffer import MicRingBuffer, clamp_mic_window_sec
from app.mic_capture import MicCaptureService
from app.mic_encode import pcm_to_wav_data_uri
from app.mic_prompt import build_mic_insert_user_pt
from main import MIC_POLL_MS, MIC_POLL_PHASE_MS


def test_clamp_mic_window_sec():
    assert clamp_mic_window_sec(0) == 1
    assert clamp_mic_window_sec(5) == 5
    assert clamp_mic_window_sec(99) == 30


def test_ring_buffer_keeps_recent_only():
    buf = MicRingBuffer(sample_rate=1000, capacity_sec=2)
    buf.append(b"\x01" * 2000)
    buf.append(b"\x02" * 2000)
    recent = buf.take_recent(1)
    assert len(recent) == 1000 * 2
    assert recent[0] == 2


def test_pcm_to_wav_data_uri():
    pcm = b"\x00\x01" * 2000
    uri = pcm_to_wav_data_uri(pcm)
    assert uri is not None
    assert uri.startswith("data:audio/wav;base64,")


def test_pcm_to_wav_data_uri_rejects_short():
    assert pcm_to_wav_data_uri(b"\x00\x01") is None


def test_mic_poll_interval_constants():
    assert MIC_POLL_MS == 600
    assert MIC_POLL_PHASE_MS == 250


def test_try_snapshot_pcm_ms_returns_pcm_when_lock_free():
    cap = MicCaptureService()
    cap._buffer.append(b"\x01\x02" * 8000)
    pcm = cap.try_snapshot_pcm_ms(200)
    assert pcm is not None
    assert len(pcm) > 0


def test_try_snapshot_pcm_ms_returns_none_when_lock_held():
    cap = MicCaptureService()
    cap._buffer.append(b"\x01\x02" * 8000)
    buf = cap._buffer
    buf._lock.acquire()
    try:
        start = time.perf_counter()
        pcm = cap.try_snapshot_pcm_ms(200)
        elapsed = time.perf_counter() - start
        assert pcm is None
        assert elapsed < 0.05
    finally:
        buf._lock.release()


def test_build_mic_insert_user_pt():
    out = build_mic_insert_user_pt("请生成弹幕：")
    assert "请生成弹幕：" in out
    assert "麦克风" in out
    assert "截图" in out

    out = build_mic_insert_user_pt("base")
    assert "麦克风插入" in out
    assert out.startswith("base")
    assert "请生成 6条 JSON 数组弹幕" in out
    assert "前3条必须直接回应" in out
    assert "后 3 条可结合截图氛围" in out
    assert "仍要在前 2 条体现听到了用户说话" in out
