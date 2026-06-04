import asyncio
import json
import logging
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
import db

client = genai.Client(api_key=GEMINI_API_KEY)
logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

SYSTEM = """You are analyzing a payment screenshot for a Telegram community subscription.

Extract:
- amount (with currency symbol, e.g. ₹999)
- status (Success / Failed / Pending)
- date (DD/MM/YYYY or as shown)
- time (HH:MM or as shown)
- utr (UTR number, transaction ID, or reference number — exact value)

Judge:
- is_valid: true if payment is successful and screenshot looks genuine
- suspicious: true if anything looks edited, inconsistent, or fake

Respond ONLY in this JSON format:
{
  "amount": "...",
  "status": "...",
  "date": "...",
  "time": "...",
  "utr": "...",
  "is_valid": true,
  "suspicious": false,
  "note": ""
}"""

_PARSE_ERROR = {"is_valid": False, "suspicious": True, "note": "Could not read screenshot."}


async def analyze(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    try:
        r = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                "Analyze this payment screenshot.",
            ],
            config=types.GenerateContentConfig(system_instruction=SYSTEM),
        )
        text = r.text.strip()
    except Exception as e:
        logger.error(f"Screenshot analysis failed: {e}")
        return _PARSE_ERROR

    start, end = text.find("{"), text.rfind("}") + 1
    if start == -1 or end <= start:
        return _PARSE_ERROR

    try:
        result = json.loads(text[start:end])
    except json.JSONDecodeError:
        return _PARSE_ERROR

    if result.get("is_valid") and await db.is_duplicate_utr(result.get("utr", "")):
        result["is_valid"] = False
        result["suspicious"] = True
        result["note"] = "Duplicate transaction ID — already used."

    return result
