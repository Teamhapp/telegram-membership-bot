import os
import channels as ch_registry
from engine.humanise import typing_then_reply, typing_then_photo


async def create_payment(bot, chat_id: int, channel: dict):
    mode = channel.get("payment_mode", "qr")
    if mode == "qr":
        await _send_qr(bot, chat_id, channel)
    elif mode == "link":
        await _send_link(bot, chat_id, channel)


async def _send_qr(bot, chat_id: int, channel: dict):
    upi = channel.get("upi_id", "")
    price = channel.get("price", "")
    name = channel.get("name", "")
    qr_image = channel.get("qr_image", "")

    caption = f"*{name}* — {price}\nUPI: `{upi}`\n\nSend screenshot after payment 👍"

    if qr_image and os.path.exists(qr_image):
        with open(qr_image, "rb") as f:
            await typing_then_photo(bot, chat_id, f, caption)
    else:
        await typing_then_reply(bot, chat_id, caption)


async def _send_link(bot, chat_id: int, channel: dict):
    link = channel.get("payment_link", "")
    name = channel.get("name", "")
    price = channel.get("price", "")
    text = f"*{name}* — {price}\n{link}\n\nSend screenshot after payment 👍"
    await typing_then_reply(bot, chat_id, text)
