import json
from pathlib import Path

_KB = Path(__file__).parent.parent / "data" / "knowledge.json"
_RULES = Path(__file__).parent.parent / "data" / "rules.json"
_EXAMPLES = Path(__file__).parent.parent / "data" / "examples.json"


def load_knowledge() -> str:
    data = json.loads(_KB.read_text(encoding="utf-8"))
    lines = [f"Community: {data.get('community_name', '')}"]
    lines.append(f"Description: {data.get('description', '')}")
    lines.append(f"Price: {data.get('price', '')}")
    lines.append(f"Refund policy: {data.get('refund_policy', '')}")
    lines.append(f"Content: {data.get('content_type', '')}")
    lines.append(f"Who is it for: {data.get('who_is_it_for', '')}")
    faqs = data.get("faqs", [])
    if faqs:
        lines.append("FAQs:")
        for faq in faqs:
            lines.append(f"  Q: {faq['question']}")
            lines.append(f"  A: {faq['answer']}")
    return "\n".join(lines)


def load_rules() -> str:
    data = json.loads(_RULES.read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    return "\n".join(f"- {r}" for r in rules)


def load_examples() -> str:
    data = json.loads(_EXAMPLES.read_text(encoding="utf-8"))
    examples = data.get("examples", [])
    lines = []
    for ex in examples:
        lines.append(f'User: {ex["user"]}')
        lines.append(f'Reply: {ex["reply"]}')
        lines.append("")
    return "\n".join(lines)
