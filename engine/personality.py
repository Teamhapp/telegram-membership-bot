import json
from pathlib import Path

_PATH = Path(__file__).parent.parent / "data" / "personality.json"


def load() -> dict:
    return json.loads(_PATH.read_text(encoding="utf-8"))


def to_prompt(p: dict) -> str:
    """Legacy helper — kept for compatibility."""
    return p.get("persona_description", "")
