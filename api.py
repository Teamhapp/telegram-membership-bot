"""
REST API
- External payment gateway webhooks
- Admin grant/revoke
- Prompt Studio (knowledge, rules, personality, examples)
- FAQ approval
- Analytics
"""
import json
import logging
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

import db
from access.telegram import grant_access, revoke_access
from subscriptions.engine import activate, set_blocked
from analytics import tracker
from config import API_SECRET, SUBSCRIPTION_DAYS, RAZORPAY_KEY_SECRET

logger = logging.getLogger(__name__)

app = FastAPI(title="Community Admin API", version="2.0")

_bot = None
DATA_DIR = Path(__file__).parent / "data"


def set_bot(bot):
    global _bot
    _bot = bot


def _auth(secret: str | None):
    if not API_SECRET:
        return
    if secret != API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── models ────────────────────────────────────────────────────────────────────

class GrantRequest(BaseModel):
    user_id: int
    channel_id: str
    days: int = SUBSCRIPTION_DAYS


class RevokeRequest(BaseModel):
    user_id: int
    channel_id: str


class WebhookPayload(BaseModel):
    user_id: int
    channel_id: str
    amount: str
    utr: str
    status: str


class FAQApproveRequest(BaseModel):
    candidate_id: int
    answer: str


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── user ──────────────────────────────────────────────────────────────────────

@app.get("/user/{user_id}")
async def get_user(user_id: int, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sub = await db.get_subscription(user_id)
    return {"user": user, "subscription": sub}


# ── access ────────────────────────────────────────────────────────────────────

@app.post("/grant")
async def grant(req: GrantRequest, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    if not _bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    user = await db.get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found — they must /start the bot first.")
    import channels as ch_registry
    channel = ch_registry.get(req.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")
    await activate(req.user_id, req.channel_id, req.days)
    try:
        link = await grant_access(_bot, req.user_id, channel["telegram_id"])
        await _bot.send_message(
            chat_id=req.user_id,
            text=f"Payment received 👍\n\n*{channel['name']}* access link:\n{link}",
            parse_mode="Markdown",
        )
        await tracker.track(req.user_id, tracker.ACCESS_GRANTED, source="api", channel=req.channel_id)
        return {"status": "granted", "invite_link": link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/revoke")
async def revoke(req: RevokeRequest, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    if not _bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    import channels as ch_registry
    channel = ch_registry.get(req.channel_id)
    if channel:
        await revoke_access(_bot, req.user_id, channel["telegram_id"])
    await set_blocked(req.user_id)
    try:
        await _bot.send_message(
            chat_id=req.user_id,
            text="Your access has been revoked. Contact us if this is a mistake.",
        )
    except Exception:
        pass
    await tracker.track(req.user_id, tracker.SUBSCRIPTION_EXPIRED, source="api", channel=req.channel_id)
    return {"status": "revoked"}


# ── payment webhooks ──────────────────────────────────────────────────────────

@app.post("/webhook/payment")
async def payment_webhook(payload: WebhookPayload, x_api_secret: str | None = Header(default=None)):
    """Generic payment gateway webhook."""
    _auth(x_api_secret)
    if not _bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")
    if payload.status.lower() != "success":
        return {"status": "ignored"}
    if await db.is_duplicate_utr(payload.utr):
        raise HTTPException(status_code=409, detail="Duplicate UTR.")
    user = await db.get_user(payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    import channels as ch_registry
    channel = ch_registry.get(payload.channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")
    payment_id = await db.save_payment(payload.user_id, payload.channel_id, payload.amount, payload.utr, "webhook")
    await db.approve_payment(payment_id)
    await activate(payload.user_id, payload.channel_id, channel["subscription_days"])
    await tracker.track(payload.user_id, tracker.PAYMENT_SUCCESS, amount=payload.amount, source="webhook", channel=payload.channel_id)
    try:
        link = await grant_access(_bot, payload.user_id, channel["telegram_id"])
        await _bot.send_message(
            chat_id=payload.user_id,
            text=f"Payment received 👍\n\n*{channel['name']}* access link:\n{link}",
            parse_mode="Markdown",
        )
        await tracker.track(payload.user_id, tracker.ACCESS_GRANTED, source="webhook", channel=payload.channel_id)
        return {"status": "granted", "invite_link": link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request):
    """Razorpay webhook — verifies signature and grants access."""
    if not _bot:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")

    from payments.razorpay_provider import verify_webhook
    if not await verify_webhook(body, signature):
        raise HTTPException(status_code=400, detail="Invalid signature")

    event = json.loads(body)
    if event.get("event") != "payment.captured":
        return {"status": "ignored"}

    payment = event["payload"]["payment"]["entity"]
    notes = payment.get("notes", {})
    user_id = int(notes.get("user_id", 0))
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id missing in notes")

    amount = f"₹{payment['amount'] // 100}"
    utr = payment.get("id", "")

    if await db.is_duplicate_utr(utr):
        return {"status": "duplicate"}

    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    payment_id = await db.save_payment(user_id, amount, utr, "razorpay")
    await db.approve_payment(payment_id)
    await activate(user_id)
    await tracker.track(user_id, tracker.PAYMENT_SUCCESS, amount=amount, source="razorpay")

    link = await grant_access(_bot, user_id)
    await _bot.send_message(
        chat_id=user_id,
        text=f"Payment received 👍\n\nHere's your access link:\n{link}",
    )
    await tracker.track(user_id, tracker.ACCESS_GRANTED, source="razorpay")
    return {"status": "granted"}


# ── prompt studio ─────────────────────────────────────────────────────────────

@app.get("/admin/knowledge")
async def get_knowledge(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    return json.loads((DATA_DIR / "knowledge.json").read_text(encoding="utf-8"))


@app.put("/admin/knowledge")
async def update_knowledge(data: dict, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    (DATA_DIR / "knowledge.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "updated"}


@app.get("/admin/rules")
async def get_rules(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    return json.loads((DATA_DIR / "rules.json").read_text(encoding="utf-8"))


@app.put("/admin/rules")
async def update_rules(data: dict, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    (DATA_DIR / "rules.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "updated"}


@app.get("/admin/personality")
async def get_personality(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    return json.loads((DATA_DIR / "personality.json").read_text(encoding="utf-8"))


@app.put("/admin/personality")
async def update_personality(data: dict, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    (DATA_DIR / "personality.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "updated"}


@app.get("/admin/examples")
async def get_examples(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    return json.loads((DATA_DIR / "examples.json").read_text(encoding="utf-8"))


@app.put("/admin/examples")
async def update_examples(data: dict, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    (DATA_DIR / "examples.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"status": "updated"}


# ── faq management ────────────────────────────────────────────────────────────

@app.get("/admin/faq/candidates")
async def faq_candidates(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    return {"candidates": await db.get_faq_candidates(min_count=2)}


@app.post("/admin/faq/approve")
async def approve_faq(req: FAQApproveRequest, x_api_secret: str | None = Header(default=None)):
    """Approve a FAQ candidate and add it to knowledge.json."""
    _auth(x_api_secret)
    candidates = await db.get_faq_candidates(min_count=0)
    match = next((c for c in candidates if c["id"] == req.candidate_id), None)
    if not match:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # add to knowledge.json
    kb_path = DATA_DIR / "knowledge.json"
    kb = json.loads(kb_path.read_text(encoding="utf-8"))
    kb.setdefault("faqs", []).append({"question": match["question"], "answer": req.answer})
    kb_path.write_text(json.dumps(kb, indent=2, ensure_ascii=False), encoding="utf-8")

    await db.approve_faq_candidate(req.candidate_id)
    return {"status": "approved", "added_to_knowledge_base": True}


@app.delete("/admin/faq/candidate/{candidate_id}")
async def dismiss_faq(candidate_id: int, x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    await db.approve_faq_candidate(candidate_id)
    return {"status": "dismissed"}


# ── analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
async def analytics_summary(x_api_secret: str | None = Header(default=None)):
    _auth(x_api_secret)
    events = await db.get_analytics_events()
    total_users = await db.get_total_user_count()
    active_subs = await db.get_active_subscription_count()
    faq_candidates = await db.get_faq_candidates(min_count=2)

    chat_starts = events.get(tracker.CHAT_START, 0)
    price_requests = events.get(tracker.PRICE_REQUEST, 0)
    payment_attempts = events.get(tracker.PAYMENT_ATTEMPT, 0)
    payment_success = events.get(tracker.PAYMENT_SUCCESS, 0)

    funnel = {
        "total_users": total_users,
        "chat_starts": chat_starts,
        "price_requests": price_requests,
        "payment_attempts": payment_attempts,
        "payment_success": payment_success,
        "active_subscriptions": active_subs,
        "conversion_rate": f"{round(payment_success / chat_starts * 100, 1)}%" if chat_starts else "0%",
        "price_to_payment_rate": f"{round(payment_attempts / price_requests * 100, 1)}%" if price_requests else "0%",
    }

    return {"funnel": funnel, "all_events": events, "faq_candidates": faq_candidates}
