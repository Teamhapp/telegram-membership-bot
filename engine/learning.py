import asyncio
import logging
from google import genai
from google.genai import types
import db
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"


async def analyze_for_faq(user_id: int, message: str, intent: str) -> str | None:
    if intent not in ("DETAILS", "PROOF", "HELP", "OTHER"):
        return None
    prompt = f"""Is this message a genuine question that could be an FAQ for a paid community?
If yes, rewrite it as a clean, normalized English question (1 sentence).
If no, reply: NO

Message: {message}"""
    try:
        r = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=40, temperature=0),
        )
        result = r.text.strip()
        if result and result.upper() != "NO" and "?" in result:
            await db.upsert_faq_candidate(result)
            return result
    except Exception as e:
        logger.error(f"FAQ analysis failed: {e}")
    return None
