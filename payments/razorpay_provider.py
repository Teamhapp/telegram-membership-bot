"""
Razorpay provider.
Set PAYMENT_MODE=razorpay in .env to activate.
Requires: pip install razorpay
"""
import asyncio
import hashlib
import hmac as _hmac
from config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, PRICE_MONTHLY


async def create_order(user_id: int) -> dict:
    import razorpay
    client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
    amount_str = PRICE_MONTHLY.replace("₹", "").replace(",", "").strip()
    amount_paise = int(float(amount_str)) * 100
    order = await asyncio.to_thread(client.order.create, {
        "amount": amount_paise,
        "currency": "INR",
        "notes": {"user_id": str(user_id)},
    })
    return order


def _hmac_sha256(key: bytes, msg: bytes) -> str:
    return _hmac.new(key, msg, hashlib.sha256).hexdigest()


async def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    msg = f"{order_id}|{payment_id}".encode()
    expected = _hmac_sha256(RAZORPAY_KEY_SECRET.encode(), msg)
    return _hmac.compare_digest(expected, signature)


async def verify_webhook(body: bytes, signature: str) -> bool:
    expected = _hmac_sha256(RAZORPAY_KEY_SECRET.encode(), body)
    return _hmac.compare_digest(expected, signature)
