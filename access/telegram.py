from datetime import datetime, timedelta
from telegram import Bot
from config import INVITE_LINK_EXPIRE_HOURS


async def grant_access(bot: Bot, user_id: int, telegram_channel_id: str) -> str:
    """Unban (if needed) and generate a single-use invite link for a specific channel."""
    try:
        await bot.unban_chat_member(chat_id=telegram_channel_id, user_id=user_id, only_if_banned=True)
    except Exception:
        pass
    expire_at = datetime.now() + timedelta(hours=INVITE_LINK_EXPIRE_HOURS)
    link = await bot.create_chat_invite_link(
        chat_id=telegram_channel_id,
        expire_date=expire_at,
        member_limit=1,
        creates_join_request=False,
    )
    return link.invite_link


async def revoke_access(bot: Bot, user_id: int, telegram_channel_id: str):
    """Kick user from a specific channel."""
    try:
        await bot.ban_chat_member(chat_id=telegram_channel_id, user_id=user_id, revoke_messages=False)
        await bot.unban_chat_member(chat_id=telegram_channel_id, user_id=user_id, only_if_banned=True)
    except Exception:
        pass
