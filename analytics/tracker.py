import json
import db


async def track(user_id: int, event: str, **kwargs):
    meta = json.dumps(kwargs) if kwargs else ""
    await db.track_event(user_id, event, meta)


# event constants
CHAT_START = "chat_start"
PRICE_REQUEST = "price_request"
DETAILS_REQUEST = "details_request"
PAYMENT_ATTEMPT = "payment_attempt"
PAYMENT_SUCCESS = "payment_success"
PAYMENT_REJECTED = "payment_rejected"
ACCESS_GRANTED = "access_granted"
RENEWAL = "renewal"
SUBSCRIPTION_EXPIRED = "subscription_expired"
