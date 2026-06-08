"""TTS 音频格式工具（PCM / 下载字节 → WAV）。"""

from __future__ import annotations

import io
import wave


def pcm_to_wav(pcm: bytes, *, sample_rate: int = 24000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def ensure_wav_bytes(data: bytes, *, sample_rate: int = 24000) -> bytes:
    if data[:4] == b"RIFF":
        return data
    return pcm_to_wav(data, sample_rate=sample_rate)
