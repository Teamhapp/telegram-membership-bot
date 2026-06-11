import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
import aiosqlite
from config import DB_PATH
from subscriptions.engine import State
from analytics import tracker
from access.telegram import revoke_access
from admin import notifications as notify
import channels as ch_registry
import db as db_module

logger = logging.getLogger(__name__)


async def _get_expiring(days: int, flag_col: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            f"""SELECT s.id as sub_id, s.user_id, s.channel_id, s.expires_at
                FROM subscriptions s
                WHERE s.status='active'
                AND {flag_col}=0
                AND datetime(s.expires_at) <= datetime('now', '+{days} days')
                AND datetime(s.expires_at) > datetime('now')"""
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def _set_flag(sub_id: int, flag_col: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE subscriptions SET {flag_col}=1 WHERE id=?", (sub_id,))
        await db.commit()


async def _get_expired() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT s.user_id, s.id as sub_id, s.channel_id
               FROM subscriptions s
               WHERE s.status='active'
               AND datetime(s.expires_at) <= datetime('now')"""
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def _mark_expired(sub_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (sub_id,))
        # only set user state to EXPIRED if no other active subscriptions remain
        async with db.execute(
            "SELECT COUNT(*) FROM subscriptions WHERE user_id=? AND status='active'", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            remaining = row[0] if row else 0
        if remaining == 0:
            await db.execute(
                "UPDATE users SET subscription_state=? WHERE user_id=?", (State.EXPIRED, user_id)
            )
        await db.commit()


async def check_expiries(bot: Bot):
    # 3-day reminder
    for row in await _get_expiring(days=3, flag_col="reminded_3d"):
        ch = ch_registry.get(row["channel_id"])
        ch_name = ch["name"] if ch else row["channel_id"]
        try:
            await bot.send_message(
                chat_id=row["user_id"],
                text=f"Your *{ch_name}* subscription expires in 3 days. Reply 'renew' to continue.",
                parse_mode="Markdown",
            )
            await _set_flag(row["sub_id"], "reminded_3d")
        except Exception as e:
            logger.warning(f"3d reminder failed uid={row['user_id']}: {e}")

    # 1-day reminder
    for row in await _get_expiring(days=1, flag_col="reminded_1d"):
        ch = ch_registry.get(row["channel_id"])
        ch_name = ch["name"] if ch else row["channel_id"]
        try:
            await bot.send_message(
                chat_id=row["user_id"],
                text=f"Your *{ch_name}* subscription expires tomorrow. Reply 'renew' to continue.",
                parse_mode="Markdown",
            )
            await _set_flag(row["sub_id"], "reminded_1d")
        except Exception as e:
            logger.warning(f"1d reminder failed uid={row['user_id']}: {e}")

    # expire and kick
    for row in await _get_expired():
        user_id = row["user_id"]
        channel_id = row["channel_id"]
        ch = ch_registry.get(channel_id)
        ch_name = ch["name"] if ch else channel_id

        try:
            if ch and ch.get("telegram_id"):
                await revoke_access(bot, user_id, ch["telegram_id"])
            await _mark_expired(row["sub_id"], user_id)
            await bot.send_message(
                chat_id=user_id,
                text=f"Your *{ch_name}* subscription has expired. Reply 'renew' to rejoin.",
                parse_mode="Markdown",
            )
            await tracker.track(user_id, tracker.SUBSCRIPTION_EXPIRED, channel=channel_id)
            await notify.subscription_expired(user_id, str(user_id), ch_name)
            logger.info(f"Expired uid={user_id} channel={channel_id}")
        except Exception as e:
            logger.warning(f"Expiry failed uid={user_id} channel={channel_id}: {e}")
            await _mark_expired(row["sub_id"], user_id)


async def send_daily_summary(bot: Bot):
    try:
        active = await db_module.get_active_subscription_count()
        total = await db_module.get_total_user_count()
        await notify.daily_summary({
            "new_users": 0,
            "payments": 0,
            "active_subs": active,
            "expired": 0,
            "suspicious": 0,
        })
    except Exception as e:
        logger.warning(f"Daily summary failed: {e}")


def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_expiries,
        trigger="interval",
        hours=1,
        args=[bot],
        id="expiry_check",
        replace_existing=True,
    )
    scheduler.add_job(
        send_daily_summary,
        trigger="cron",
        hour=9,
        minute=0,
        args=[bot],
        id="daily_summary",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started.")
    return scheduler
