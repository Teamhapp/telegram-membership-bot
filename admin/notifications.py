"""
Admin notification system.
Sends Telegram DMs to all ADMIN_IDS on key events.
"""
import logging
from datetime import datetime
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

_bot = None


def set_bot(bot):
    global _bot
    _bot = bot


async def _notify(text: str):
    if not _bot or not ADMIN_IDS:
        return
    for admin_id in ADMIN_IDS:
        try:
            await _bot.send_message(chat_id=admin_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Admin notify failed for {admin_id}: {e}")


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

async def bot_started(mode: str, channel_names: list[str]):
    ch = ", ".join(channel_names) if channel_names else "none"
    await _notify(
        f"🟢 *Bot started*\n"
        f"Mode: `{mode}`\n"
        f"Channels: {ch}\n"
        f"Time: {_now()}"
    )


async def bot_error(error: str, context: str = ""):
    await _notify(
        f"🔴 *Bot error*\n"
        f"{'Context: ' + context + chr(10) if context else ''}"
        f"```\n{error[:400]}\n```"
    )


# ── User activity ─────────────────────────────────────────────────────────────

async def new_user(user_id: int, username: str, first_name: str):
    await _notify(
        f"👤 *New user started*\n"
        f"Name: {first_name}\n"
        f"Username: @{username}\n"
        f"ID: `{user_id}`"
    )


async def user_wants_to_join(user_id: int, username: str, channel_name: str):
    await _notify(
        f"🙋 *Join intent*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Channel: {channel_name}"
    )


# ── Payments ─────────────────────────────────────────────────────────────────

async def payment_received(user_id: int, username: str, amount: str, utr: str, channel_name: str = ""):
    ch_line = f"\nChannel: {channel_name}" if channel_name else ""
    await _notify(
        f"✅ *Payment received*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Amount: {amount}\n"
        f"UTR: `{utr}`{ch_line}\n"
        f"Time: {_now()}"
    )


async def payment_suspicious(user_id: int, username: str, note: str):
    await _notify(
        f"⚠️ *Suspicious screenshot*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Reason: {note}\n"
        f"Action needed: verify manually"
    )


async def payment_failed(user_id: int, username: str, reason: str):
    await _notify(
        f"❌ *Payment rejected*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Reason: {reason}"
    )


# ── Access ────────────────────────────────────────────────────────────────────

async def access_granted(user_id: int, username: str, channel_name: str = ""):
    ch_line = f"\nChannel: {channel_name}" if channel_name else ""
    await _notify(
        f"🔓 *Access granted*\n"
        f"User: @{username} (`{user_id}`){ch_line}"
    )


async def access_revoked(user_id: int, username: str, channel_name: str = ""):
    ch_line = f"\nChannel: {channel_name}" if channel_name else ""
    await _notify(
        f"🚫 *Access revoked*\n"
        f"User: @{username} (`{user_id}`){ch_line}"
    )


# ── Subscriptions ─────────────────────────────────────────────────────────────

async def subscription_expiring_soon(user_id: int, username: str, days: int, channel_name: str = ""):
    ch_line = f" ({channel_name})" if channel_name else ""
    await _notify(
        f"⏳ *Expiring in {days}d*{ch_line}\n"
        f"User: @{username} (`{user_id}`)"
    )


async def subscription_expired(user_id: int, username: str, channel_name: str = ""):
    ch_line = f"\nChannel: {channel_name}" if channel_name else ""
    await _notify(
        f"⏰ *Subscription expired*\n"
        f"User: @{username} (`{user_id}`){ch_line}"
    )


async def renewal_requested(user_id: int, username: str, channel_name: str = ""):
    ch_line = f"\nChannel: {channel_name}" if channel_name else ""
    await _notify(
        f"🔄 *Renewal requested*\n"
        f"User: @{username} (`{user_id}`){ch_line}"
    )


# ── FAQ ───────────────────────────────────────────────────────────────────────

async def new_faq_candidate(question: str, count: int):
    await _notify(
        f"💡 *FAQ Candidate* (asked {count}×)\n"
        f"_{question}_\n\n"
        f"Approve: `POST /admin/faq/approve`"
    )


# ── Daily summary ─────────────────────────────────────────────────────────────

async def daily_summary(stats: dict):
    await _notify(
        f"📊 *Daily Summary — {_today()}*\n"
        f"New users: {stats.get('new_users', 0)}\n"
        f"Payments received: {stats.get('payments', 0)}\n"
        f"Active subscriptions: {stats.get('active_subs', 0)}\n"
        f"Expired today: {stats.get('expired', 0)}\n"
        f"Suspicious screenshots: {stats.get('suspicious', 0)}"
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now().strftime("%d %b %Y, %I:%M %p")


def _today() -> str:
    return datetime.now().strftime("%d %b %Y")
