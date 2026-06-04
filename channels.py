"""
Channel registry — loads and provides channel configs from data/channels.json.
Single source of truth for all channel-related data.
"""
import json
from pathlib import Path

_PATH = Path(__file__).parent / "data" / "channels.json"


def load_all() -> list[dict]:
    return json.loads(_PATH.read_text(encoding="utf-8"))["channels"]


def get(channel_id: str) -> dict | None:
    return next((c for c in load_all() if c["id"] == channel_id), None)


def get_by_telegram_id(telegram_id: str) -> dict | None:
    return next((c for c in load_all() if c["telegram_id"] == telegram_id), None)


def summary_list() -> str:
    """Human-readable channel list for bot replies."""
    channels = load_all()
    lines = []
    for i, ch in enumerate(channels, 1):
        lines.append(f"{i}. {ch['name']} — {ch['price']}/month\n   {ch['description']}")
    return "\n\n".join(lines)
