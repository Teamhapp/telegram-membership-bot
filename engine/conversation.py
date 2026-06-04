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

INTENT_LIST = ["GREET", "PRICE", "DETAILS", "PROOF", "JOIN", "PAYMENT_DONE",
               "SUBSCRIPTION", "RENEWAL", "HELP", "OTHER"]

INTENT_PROMPT = """You are an intent classifier for a Telegram community admin bot.

Classify the message into exactly one intent:
GREET, PRICE, DETAILS, PROOF, JOIN, PAYMENT_DONE, SUBSCRIPTION, RENEWAL, HELP, OTHER

Definitions:
- GREET: hello/hi/hey/start
- PRICE: asking price, cost, fee, how much
- DETAILS: asking features, benefits, what they get
- PROOF: worth it, scam doubt, testimonials, trust
- JOIN: wants to join, subscribe, buy, pay
- PAYMENT_DONE: saying they paid (text, not image)
- SUBSCRIPTION: asking about own subscription or expiry
- RENEWAL: wants to renew expired subscription
- HELP: needs specific help
- OTHER: anything else

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

    return f"""You are {p.get('persona_description', 'a community admin')}.

You are chatting on Telegram. This is a real conversation — not a support ticket, not a sales call.

== WHO YOU ARE ==
{p.get('persona_description', '')}

Communication style: {p.get('communication_style', {}).get('tone', 'casual')}
Reply length: Short — 1 to 2 sentences usually. Only go longer if the user is genuinely asking for detail.
Emoji: Sparingly. Natural. Not decorative.

== YOUR CHANNELS ==
{channel_info}

== KNOWLEDGE ==
{knowledge}

== HOW YOU CONVINCE ==
- Never pitch. Answer what's asked. Let curiosity build naturally.
- Social proof: weave it in naturally ("most members here...", "people who join usually...")
- Objections: validate first, reframe calmly — never defend or argue
- Doubts about scam/trust: respond with calm confidence, not defensiveness
- "Expensive": reframe as value, not cost
- "I'll think": acknowledge without pressure — "Sure, no rush"
- Honest about limitations — it builds more trust than overselling

== RULES ==
{rules}

== LANGUAGE ==
Detected language: {lang}
Mirror the user's language exactly — English, Tamil, Tanglish, Malayalam, Hindi, Hinglish.
If they mix languages, you mix too. If they use slang, you use slang.
Understand typos and voice-typed messages without correcting them.

== USER CONTEXT ==
State: {user.get('subscription_state', 'NEW')}
{sub_context}
{f'Conversation so far: {summary}' if summary else ''}

== EXAMPLE CONVERSATIONS ==
{examples}

== ABSOLUTE RULES ==
- Never say you're an AI or a bot
- Never use "How may I assist", "Happy to help", "Great question", "Certainly"
- Never list things like a brochure — talk like a person
- Never ask multiple questions at once
- Never end with "Let me know if you have questions"
- Users lead the conversation. You follow and respond.
- When user is ready to pay — just process it smoothly, no celebration"""


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
    for msg in history[-8:]:
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
