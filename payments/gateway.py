import os
import channels as ch_registry


async def create_payment(bot, chat_id: int, channel: dict):
    """Send payment instructions for a specific channel."""
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

    caption = (
        f"*{name}*\n"
        f"UPI: `{upi}`\n"
        f"Amount: {price}\n\n"
        "Send screenshot after payment."
    )
    if qr_image and os.path.exists(qr_image):
        with open(qr_image, "rb") as f:
            await bot.send_photo(chat_id=chat_id, photo=f, caption=caption, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id=chat_id, text=caption, parse_mode="Markdown")


async def _send_link(bot, chat_id: int, channel: dict):
    link = channel.get("payment_link", "")
    name = channel.get("name", "")
    await bot.send_message(
        chat_id=chat_id,
        text=f"*{name}*\nPay here: {link}\n\nSend screenshot after payment.",
        parse_mode="Markdown",
    )
