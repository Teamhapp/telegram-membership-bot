"""
Admin notification system.
Sends Telegram messages to all configured ADMIN_IDS on key events.
"""
import logging
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


async def payment_received(user_id: int, username: str, amount: str, utr: str):
    await _notify(
        f"✅ *Payment received*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Amount: {amount}\n"
        f"UTR: `{utr}`"
    )


async def payment_suspicious(user_id: int, username: str, note: str):
    await _notify(
        f"⚠️ *Suspicious screenshot*\n"
        f"User: @{username} (`{user_id}`)\n"
        f"Reason: {note}"
    )


async def access_granted(user_id: int, username: str):
    await _notify(
        f"🔓 *Access granted*\n"
        f"User: @{username} (`{user_id}`)"
    )


async def subscription_expired(user_id: int, username: str):
    await _notify(
        f"⏰ *Subscription expired*\n"
        f"User: @{username} (`{user_id}`)"
    )


async def new_faq_candidate(question: str, count: int):
    await _notify(
        f"💡 *FAQ Candidate* (asked {count} times)\n"
        f"_{question}_\n\n"
        f"Approve via: `POST /admin/faq/approve`"
    )
