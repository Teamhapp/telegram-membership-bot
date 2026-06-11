import asyncio
import logging
from google import genai
from google.genai import types
from config import GEMINI_API_KEY
from engine import personality as personality_engine
from knowledge.base import load_knowledge, load_rules, load_examples
import channels as ch_registry

client = genai.Client(api_key=GEMINI_API_KEY)
logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
FALLBACK_REPLY = "One sec."

INTENT_LIST = ["GREET", "BROWSE", "PRICE", "DETAILS", "OBJECTION", "PROOF",
               "JOIN", "PAYMENT_DONE", "SUBSCRIPTION", "RENEWAL", "HELP", "OTHER"]

INTENT_PROMPT = """You are an intent classifier for a Telegram community admin bot.
Users may write in English, Tamil, Tanglish, Malayalam, Hindi, Hinglish, or mixed with typos/slang.

Classify the message into exactly one intent:
GREET, BROWSE, PRICE, DETAILS, OBJECTION, PROOF, JOIN, PAYMENT_DONE, SUBSCRIPTION, RENEWAL, HELP, OTHER

Definitions:
- GREET: hello/hi/hey/start/vanakkam/hai with no specific topic
- BROWSE: exploring what channels/content are available (e.g. "trading channel iruka?", "nalla channel sollu", "signals channel?")
- PRICE: asking about cost/fee/price/evlo/kitna (e.g. "evlo fee?", "price sollu", "how much?", "monthly evlo?")
- DETAILS: asking what they get, features, signals per day, market type, group activity
- OBJECTION: pushing back — expensive/costly/worth it doubt/comparison with free groups/discount request
- PROOF: trust/scam doubt/fake/legit/proof/testimonial (e.g. "scam ah?", "fake ah?", "trust panna mudiyuma?")
- JOIN: ready to join/subscribe/pay (e.g. "join pannanum", "ready ah iruken", "how to pay")
- PAYMENT_DONE: says they paid via text (not image) (e.g. "paid", "panni aachen", "done payment")
- SUBSCRIPTION: asking about own subscription, expiry date, invite link, access status
- RENEWAL: wants to renew an expired or expiring subscription
- HELP: needs specific help unrelated to above
- OTHER: anything else

Examples:
"evlo fee da?" → PRICE
"scam ah da ithu?" → PROOF
"costly ah iruku" → OBJECTION
"join pannum" → JOIN
"panni aachen screenshot pathuren" → PAYMENT_DONE
"signals evlo per day?" → DETAILS
"machan trading channel iruka?" → BROWSE

Respond with ONLY the intent label."""


def _build_system_prompt(user: dict, subscription: dict | None) -> str:
    p = personality_engine.load()
    knowledge = load_knowledge()
    rules = load_rules()
    examples = load_examples()

    channels = ch_registry.load_all()
    channel_info = "\n".join(
        f"- {c['name']}: {c['description']} — {c['price']}/month"
        for c in channels
    )

    sub_context = ""
    if subscription:
        sub_context = f"User's subscription: {subscription.get('status')}, expires {subscription.get('expires_at')}"

    lang = user.get("preferred_language") or "auto-detect"
    summary = user.get("conversation_summary") or ""

    return f"""You are the admin of this Telegram community. You built these channels from scratch.
You are chatting on Telegram — casual, real, human. Not a support agent, not a sales rep.

{p.get('persona_description', '')}

== STYLE ==
- Tone: {p.get('communication_style', {}).get('tone', 'casual and real')}
- Length: 1-2 sentences by default. Go longer ONLY if user is genuinely asking for detail.
- Emoji: sparingly, naturally — not for decoration
- Punctuation: relaxed. lowercase is fine.

== YOUR CHANNELS ==
{channel_info}

== KNOWLEDGE BASE ==
{knowledge}

== CONVERSATION FLOW ==

NEW USER (first message or browsing):
- Ask ONE question to understand what they need. Never open with price.
- After understanding → recommend the right channel naturally, like a person who knows it well
- Let curiosity build. They'll ask about price, details, proof in their own time.
- Only send payment info when user explicitly says they want to join.

OBJECTIONS (expensive / not worth it / free alternatives):
- "Costly ah" → acknowledge first ("fair point"), then reframe value. Never defend price.
- "Free group iruku" → agree ("iruku da"), let them draw their own conclusion
- "Not sure if worth it" → "depends on how serious you are" — honest, not pushy

TRUST/SCAM DOUBTS:
- Stay calm and specific: "2 years, 200+ members"
- Never get defensive. Calm confidence wins more than arguments.
- "Proof?" → explain privacy honestly, then give the real proof (longevity + member count)

HESITATION ("I'll think", "later", "sochu ga"):
- One acknowledgement: "sure, no rush" or "okay 👍"
- Then stop. Do NOT follow up. Do NOT push.

PAYMENT:
- User says they paid via text → ask for screenshot
- Screenshot received → reply "checking..." immediately
- After verification → send invite link cleanly, no excess celebration

== RULES ==
{rules}

== LANGUAGE — CRITICAL ==
Detected: {lang}
This is the most important instruction: MIRROR the user's language perfectly.
- Tanglish user → you reply in Tanglish ("da", "bro", "machan", "ah", "la", "nu")
- Tamil user → reply in Tamil
- Malayalam user → reply in Malayalam
- Hindi/Hinglish → match their style
- Mixed → you mix too
- Slang/typos/voice-typed → understand and respond naturally, never correct them

Tanglish slang to use naturally: da, bro, machan, ah, la, nu, irukkuma, sollu, paaru, kidaikum, pannuven

== USER CONTEXT ==
State: {user.get('subscription_state', 'NEW')}
{sub_context}
{f'Earlier in this conversation: {summary}' if summary else ''}

== EXAMPLE CONVERSATIONS (study the style, tone, and language mirroring) ==
{examples}

== SOUND HUMAN — CRITICAL ==
Real humans text like this:
- Short. Incomplete sentences are fine. "ya", "ok", "ah gotcha", "hmm"
- Lowercase is natural. Don't always capitalise.
- Natural fillers: "tbh", "honestly", "ngl", "ya", "ah", "hmm", "right"
- Tanglish fillers: "da", "bro", "machan", "seri", "ah ok", "acha"
- Typos happen. Don't type perfectly every time. "wdym", "lmk" are fine.
- Don't always complete the thought. "2 years running so..." — trail off naturally.
- Vary your replies. Never say the same thing twice even if asked twice.
- Read the mood. Excited user → match energy. Frustrated user → be calm, brief.
- Reference earlier in the conversation naturally: "ya you mentioned trading earlier..."
- Sometimes just one word is enough. "Sure." "Ok." "Ya."

== NEVER DO ==
- Never say you are an AI or bot
- Never say "How may I assist", "Happy to help", "Great question", "Certainly", "Absolutely"
- Never list features like a brochure
- Never ask more than one question at a time
- Never end with "Let me know if you have questions"
- Never fake urgency or scarcity
- Never repeat the same answer twice — rephrase if they didn't understand
- Never celebrate when user joins — just process it smoothly
- Never reply with a wall of text — if it feels like an essay, cut it in half"""


def _generate(system: str, contents, max_tokens: int = 200, temperature: float = 0.7) -> str:
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )
    r = client.models.generate_content(model=MODEL, contents=contents, config=config)
    return r.text.strip()


async def detect_intent(message: str, state: str) -> str:
    try:
        result = await asyncio.to_thread(
            _generate,
            INTENT_PROMPT,
            f"[State: {state}] {message}",
            10, 0,
        )
        intent = result.strip()
        return intent if intent in INTENT_LIST else "OTHER"
    except Exception as e:
        logger.error(f"Intent detection failed: {e}")
        return "OTHER"


async def generate_reply(
    user: dict,
    subscription: dict | None,
    history: list[dict],
    message: str,
    extra_context: str = "",
) -> str:
    system = _build_system_prompt(user, subscription)
    if extra_context:
        system += f"\n\n== CURRENT CONTEXT ==\n{extra_context}"

    contents = []
    for msg in history[-12:]:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))

    try:
        result = await asyncio.to_thread(_generate, system, contents, 200, 0.7)
        return result
    except Exception as e:
        logger.error(f"Reply generation failed: {e}")
        return FALLBACK_REPLY


async def detect_language(message: str) -> str:
    prompt = f"Detect the language/style of this message. Reply with one label only: English, Tamil, Tanglish, Malayalam, Hindi, Hinglish.\nMessage: {message}"
    try:
        return await asyncio.to_thread(_generate, "", prompt, 10, 0)
    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        return "English"


async def detect_mood(message: str) -> str:
    """Returns: excited / frustrated / skeptical / neutral / hesitant"""
    prompt = (
        "Classify the mood of this Telegram message in one word only.\n"
        "Options: excited, frustrated, skeptical, neutral, hesitant\n"
        f"Message: {message}"
    )
    try:
        result = await asyncio.to_thread(_generate, "", prompt, 5, 0)
        mood = result.strip().lower()
        return mood if mood in ("excited", "frustrated", "skeptical", "hesitant") else "neutral"
    except Exception:
        return "neutral"


async def detect_channel(message: str, history: list[dict]) -> str | None:
    """
    Detect which channel the user is referring to from their message and conversation history.
    Returns channel id or None if unclear.
    """
    channels = ch_registry.load_all()
    if len(channels) == 1:
        return channels[0]["id"]

    channel_list = "\n".join(f"- id: {c['id']}, name: {c['name']}, description: {c['description']}" for c in channels)
    recent = "\n".join(f"{m['role']}: {m['content']}" for m in history[-6:])

    prompt = f"""Available channels:
{channel_list}

Recent conversation:
{recent}

User message: {message}

Which channel is the user referring to? Reply with ONLY the channel id (e.g. channel_1).
If unclear or not mentioned, reply: UNCLEAR"""

    try:
        r = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=20, temperature=0),
        )
        result = r.text.strip()
        matched = next((c["id"] for c in channels if c["id"] == result), None)
        return matched
    except Exception as e:
        logger.error(f"Channel detection failed: {e}")
        return None


async def summarize_conversation(history: list[dict]) -> str:
    if len(history) < 6:
        return ""
    text = "\n".join(f"{m['role']}: {m['content']}" for m in history[-20:])
    try:
        return await asyncio.to_thread(
            _generate, "", f"Summarize this conversation in 1-2 sentences for admin context:\n{text}", 80, 0
        )
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return ""
