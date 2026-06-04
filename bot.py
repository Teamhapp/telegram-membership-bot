import logging
import os
import asyncio
import threading
import uvicorn
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes,
)

import config
import db
import api as api_module
import channels as ch_registry
from engine.conversation import (
    detect_intent, generate_reply, detect_language,
    summarize_conversation, detect_channel,
)
from engine.learning import analyze_for_faq
from engine.ratelimit import is_allowed
from payments.gateway import create_payment
from payments.screenshot import analyze as analyze_screenshot
from access.telegram import grant_access
from subscriptions.engine import State, activate, set_pending, set_submitted
from analytics import tracker
from admin import notifications as notify
from scheduler import start_scheduler

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = "screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────

async def _load_user(update: Update) -> dict:
    u = update.effective_user
    await db.upsert_user(u.id, u.username or "", u.first_name or "")
    return await db.get_user(u.id)


async def _update_language(user_id: int, message: str, current_lang: str | None):
    if not current_lang:
        lang = await detect_language(message)
        await db.set_language(user_id, lang)


async def _refresh_summary(user_id: int):
    history = await db.get_recent_messages(user_id, limit=20)
    if len(history) >= 10 and len(history) % 10 == 0:
        summary = await summarize_conversation(history)
        if summary:
            await db.update_summary(user_id, summary)


async def _prune_history(user_id: int):
    await db.prune_history(user_id, keep=config.CONVERSATION_MAX_MESSAGES)


async def _resolve_channel(user_id: int, message: str, pending_channel_id: str) -> dict | None:
    """
    Resolve which channel to use.
    Priority: pending_channel_id → detect from message → ask if still unclear.
    """
    channels = ch_registry.load_all()

    # already selected
    if pending_channel_id:
        ch = ch_registry.get(pending_channel_id)
        if ch:
            return ch

    # single channel — no need to ask
    if len(channels) == 1:
        return channels[0]

    # detect from conversation
    history = await db.get_recent_messages(user_id, limit=6)
    channel_id = await detect_channel(message, history)
    if channel_id:
        return ch_registry.get(channel_id)

    return None  # still unclear — bot will ask naturally


async def _grant_channel_access(bot, user_id: int, chat_id: int, channel: dict):
    await activate(user_id, channel["id"], channel["subscription_days"])
    await tracker.track(user_id, tracker.PAYMENT_SUCCESS, channel=channel["id"])
    try:
        link = await grant_access(bot, user_id, channel["telegram_id"])
        await bot.send_message(
            chat_id=chat_id,
            text=f"Payment received 👍\n\nHere's your {channel['name']} access link:\n{link}",
        )
        await tracker.track(user_id, tracker.ACCESS_GRANTED, channel=channel["id"])
        await notify.access_granted(user_id, str(user_id))
    except Exception as e:
        logger.error(f"Invite link error uid={user_id} channel={channel['id']}: {e}")
        await bot.send_message(chat_id=chat_id, text="Payment received 👍\n\nSending access shortly.")


# ── handlers ──────────────────────────────────────────────────────────────────

async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _load_user(update)
    if user["subscription_state"] in (State.NEW, "NEW"):
        await db.set_state(update.effective_user.id, State.BROWSING)
    await tracker.track(update.effective_user.id, tracker.CHAT_START)
    await update.message.reply_text("Hey 👋")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _load_user(update)
    user_id = update.effective_user.id
    text = update.message.text or ""
    state = user["subscription_state"]

    if state == State.BLOCKED:
        return

    if not is_allowed(user_id):
        await update.message.reply_text("Slow down a bit.")
        return

    await _update_language(user_id, text, user.get("preferred_language"))

    intent = await detect_intent(text, state)
    logger.info(f"uid={user_id} state={state} intent={intent}")

    await db.save_message(user_id, "user", text, intent)

    # learning
    faq_question = await analyze_for_faq(user_id, text, intent)
    if faq_question:
        candidates = await db.get_faq_candidates(min_count=config.FAQ_NOTIFY_THRESHOLD)
        match = next((c for c in candidates if c["question"] == faq_question), None)
        if match and match["count"] == config.FAQ_NOTIFY_THRESHOLD:
            await notify.new_faq_candidate(faq_question, match["count"])

    # analytics
    if intent == "PRICE":
        await tracker.track(user_id, tracker.PRICE_REQUEST)
    elif intent == "DETAILS":
        await tracker.track(user_id, tracker.DETAILS_REQUEST)

    # join / renewal
    if intent in ("JOIN", "RENEWAL"):
        channel = await _resolve_channel(user_id, text, user.get("pending_channel_id", ""))

        if channel:
            await set_pending(user_id, channel["id"])
            await tracker.track(user_id, tracker.PAYMENT_ATTEMPT, channel=channel["id"])
            await create_payment(context.bot, update.effective_chat.id, channel)
            await db.save_message(user_id, "assistant", "[sent payment info]", intent)
        else:
            # channel unclear — let Gemini ask naturally
            channels = ch_registry.load_all()
            ch_names = " or ".join(c["name"] for c in channels)
            extra = f"User wants to join but hasn't specified which channel. Available: {ch_names}. Ask which one naturally."
            history = await db.get_recent_messages(user_id)
            subs = await db.get_all_subscriptions(user_id)
            sub = subs[0] if subs else None
            reply = await generate_reply(user, sub, history, text, extra_context=extra)
            await update.message.reply_text(reply)
            await db.save_message(user_id, "assistant", reply, intent)
        return

    # subscription status
    if intent == "SUBSCRIPTION":
        subs = await db.get_all_subscriptions(user_id)
        if subs:
            lines = []
            for s in subs:
                ch = ch_registry.get(s["channel_id"])
                name = ch["name"] if ch else s["channel_id"]
                lines.append(f"{name}: {s['status']} (expires {s['expires_at']})")
            extra = "User subscriptions:\n" + "\n".join(lines)
        else:
            extra = "No active subscriptions."
        history = await db.get_recent_messages(user_id)
        sub = await db.get_subscription(user_id)
        reply = await generate_reply(user, sub, history, text, extra_context=extra)
        await update.message.reply_text(reply)
        await db.save_message(user_id, "assistant", reply, intent)
        return

    # general — Gemini handles everything
    subs = await db.get_all_subscriptions(user_id)
    sub = subs[0] if subs else None
    history = await db.get_recent_messages(user_id)

    extra = ""
    if subs:
        lines = [f"{s['channel_id']}: {s['status']} until {s['expires_at']}" for s in subs]
        extra = "Subscriptions: " + ", ".join(lines)

    reply = await generate_reply(user, sub, history, text, extra_context=extra)
    await update.message.reply_text(reply)
    await db.save_message(user_id, "assistant", reply, intent)

    await _refresh_summary(user_id)
    await _prune_history(user_id)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await _load_user(update)
    user_id = update.effective_user.id
    u = update.effective_user

    if user["subscription_state"] == State.BLOCKED:
        return

    if not is_allowed(user_id):
        return

    await update.message.reply_text("Checking...")
    await set_submitted(user_id)

    channel = await _resolve_channel(user_id, "", user.get("pending_channel_id", ""))
    if not channel:
        await update.message.reply_text("Which channel is this payment for?")
        await db.set_state(user_id, State.PAYMENT_PENDING)
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_bytes = bytes(await file.download_as_bytearray())

    save_path = os.path.join(SCREENSHOTS_DIR, f"{user_id}_{photo.file_id}.jpg")
    with open(save_path, "wb") as f:
        f.write(image_bytes)

    result = await analyze_screenshot(image_bytes)
    logger.info(f"Screenshot uid={user_id} channel={channel['id']}: {result}")

    if result.get("suspicious"):
        await db.set_state(user_id, State.PAYMENT_PENDING)
        note = result.get("note", "")
        msg = "Screenshot looks off."
        if note:
            msg += f" {note}"
        msg += "\n\nSend a clear payment screenshot."
        await update.message.reply_text(msg)
        await tracker.track(user_id, tracker.PAYMENT_REJECTED, reason="suspicious", channel=channel["id"])
        await notify.payment_suspicious(user_id, u.username or str(user_id), note)
        return

    if result.get("is_valid"):
        payment_id = await db.save_payment(
            user_id, channel["id"], result.get("amount", ""), result.get("utr", ""), save_path
        )
        await db.approve_payment(payment_id)
        await notify.payment_received(
            user_id, u.username or str(user_id),
            result.get("amount", ""), result.get("utr", "")
        )
        await _grant_channel_access(context.bot, user_id, update.effective_chat.id, channel)
    else:
        await db.set_state(user_id, State.PAYMENT_PENDING)
        status = result.get("status", "unknown")
        await update.message.reply_text(
            f"Payment shows as {status}. Send a successful payment screenshot."
        )
        await tracker.track(user_id, tracker.PAYMENT_REJECTED, status=status, channel=channel["id"])


# ── post-init ─────────────────────────────────────────────────────────────────

async def post_init(application: Application):
    start_scheduler(application.bot)
    api_module.set_bot(application.bot)
    notify.set_bot(application.bot)

    def _run_api():
        uvicorn.run(
            api_module.app,
            host=config.API_HOST,
            port=config.API_PORT,
            log_level="warning",
        )
    t = threading.Thread(target=_run_api, daemon=True)
    t.start()
    logger.info(f"API running on {config.API_HOST}:{config.API_PORT}")
    channels = ch_registry.load_all()
    logger.info(f"Loaded {len(channels)} channel(s): {[c['name'] for c in channels]}")


async def post_shutdown(application: Application):
    logger.info("Bot shutting down cleanly.")


# ── app builder ───────────────────────────────────────────────────────────────

def _build_app() -> Application:
    app = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return app


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    asyncio.run(db.init_db())
    app = _build_app()

    if config.WEBHOOK_MODE:
        app.run_webhook(
            listen="0.0.0.0",
            port=config.WEBHOOK_PORT,
            secret_token=config.WEBHOOK_SECRET or None,
            webhook_url=f"{config.WEBHOOK_URL}/telegram",
            drop_pending_updates=True,
            url_path="/telegram",
        )
    else:
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
