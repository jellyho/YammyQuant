"""Cheap keyword-based sentiment — a fallback when the operator isn't scoring by hand.

Returns a score in roughly [-1, 1]. This is intentionally simple: the real
judgement is the operator (Claude Code) reading headlines via ``yq news``. The
lexicon is small and editable; English + a few Korean finance terms.
"""

from __future__ import annotations

_BULLISH = {
    "surge", "soar", "rally", "gain", "jump", "rise", "beat", "record", "high",
    "upgrade", "bullish", "breakout", "approve", "approval", "partnership", "adopt",
    "growth", "profit", "win", "outperform", "buy", "accumulate",
    "상승", "급등", "호재", "최고", "돌파", "흑자", "성장", "승인", "수혜",
}
_BEARISH = {
    "plunge", "crash", "slump", "fall", "drop", "tumble", "miss", "downgrade",
    "bearish", "hack", "exploit", "lawsuit", "ban", "halt", "fraud", "default",
    "loss", "warning", "sell", "liquidation", "delist", "bankrupt",
    "하락", "급락", "악재", "폭락", "적자", "손실", "경고", "규제", "해킹", "상장폐지",
}


def score_text(text: str) -> float:
    """Crude lexicon sentiment in [-1, 1]; 0.0 when neutral/unknown."""
    if not text:
        return 0.0
    low = text.lower()
    pos = sum(1 for w in _BULLISH if w in low)
    neg = sum(1 for w in _BEARISH if w in low)
    if pos == 0 and neg == 0:
        return 0.0
    return round((pos - neg) / (pos + neg), 3)
