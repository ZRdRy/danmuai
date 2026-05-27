"""弹幕去重记忆（prompt 层），与 danmu_engine.py 的屏幕弹幕去重（渲染层）协同但机制不同。

这里记录近期已播弹幕文本和表达角度，拼入 AI prompt 告诉模型「你最近说过这些，别重复」，
从生成源头减少重复；danmu_engine 的去重是在弹幕上屏时拦截已显示的相似文本。
两层协同：prompt 层引导 AI 换角度，渲染层兜底拦截漏网之鱼。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.memory.types import MAX_BULLET_SNIPPET_LEN, DisplayedBullet


def _truncate_bullet(content: str, max_len: int = MAX_BULLET_SNIPPET_LEN) -> str:
    text = (content or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


@dataclass
class BulletDedupMemory:
    recent_bullets: list[DisplayedBullet] = field(default_factory=list)
    recent_angles: list[str] = field(default_factory=list)  # 近期弹幕的表达角度标签（去重有序）
    avoid_angles: list[str] = field(default_factory=list)  # 告诉 AI「这些角度已用过，换一个」，引导生成多样性

    def is_empty(self) -> bool:
        return not self.recent_bullets

    def record(
        self,
        content: str,
        *,
        angle: str = "",
        window: int = 10,  # 滑动窗口大小，保留最近 N 条弹幕记忆；由 DanmuApp 传入 memory_window 配置
    ) -> None:
        snippet = _truncate_bullet(content)
        if not snippet:
            return
        bullet = DisplayedBullet(text=snippet, angle=angle or "", recorded_at=time.monotonic())
        self.recent_bullets.append(bullet)
        if window > 0 and len(self.recent_bullets) > window:
            self.recent_bullets = self.recent_bullets[-window:]
        self._rebuild_angles()

    def _rebuild_angles(self) -> None:
        angles: list[str] = []
        seen: set[str] = set()
        for bullet in reversed(self.recent_bullets):
            angle = (bullet.angle or "").strip()
            if not angle or angle in seen:
                continue
            seen.add(angle)
            angles.insert(0, angle)
        self.recent_angles = angles
        self.avoid_angles = list(angles)

    def clear(self) -> None:
        """全清：strict/medium 场景切换时使用，旧场景弹幕记忆不再适用"""
        self.recent_bullets.clear()
        self.recent_angles.clear()
        self.avoid_angles.clear()

    def trim_to(self, count: int) -> None:
        """保留最近 N 条：loose 场景切换时使用，减轻「换场景仍复读旧弹幕」但保留少量近期措辞参考"""
        if count <= 0:
            self.clear()
            return
        if len(self.recent_bullets) > count:
            self.recent_bullets = self.recent_bullets[-count:]
        self._rebuild_angles()
