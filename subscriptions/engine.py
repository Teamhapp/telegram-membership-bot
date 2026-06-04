import db


class State:
    NEW = "NEW"
    BROWSING = "BROWSING"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAYMENT_SUBMITTED = "PAYMENT_SUBMITTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    BLOCKED = "BLOCKED"


async def activate(user_id: int, channel_id: str, days: int):
    await db.create_subscription(user_id, channel_id, days)
    await db.set_state(user_id, State.ACTIVE)
    await db.set_pending_channel(user_id, "")


async def set_pending(user_id: int, channel_id: str):
    await db.set_state(user_id, State.PAYMENT_PENDING)
    await db.set_pending_channel(user_id, channel_id)


async def set_submitted(user_id: int):
    await db.set_state(user_id, State.PAYMENT_SUBMITTED)


async def set_blocked(user_id: int):
    await db.set_state(user_id, State.BLOCKED)
