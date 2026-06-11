"""
Makes the bot feel human:
- Shows "typing..." before every reply
- Delays based on reply length (faster for short, slower for long)
- Small random jitter so timing never feels mechanical
"""
import asyncio
import random
from telegram import Bot
from telegram.constants import ChatAction


async def typing_then_reply(bot: Bot, chat_id: int, text: str):
    """Show typing indicator, wait a human-realistic delay, then send."""
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    # human typing speed: ~40 chars/sec, but capped so it doesn't feel slow
    char_count = len(text)
    base_delay = min(char_count / 40, 3.5)          # max 3.5s
    base_delay = max(base_delay, 0.6)               # min 0.6s
    jitter = random.uniform(-0.2, 0.4)              # slight randomness
    delay = round(base_delay + jitter, 2)

    await asyncio.sleep(delay)
    await bot.send_message(chat_id=chat_id, text=text)


async def typing_then_photo(bot: Bot, chat_id: int, photo, caption: str):
    """Typing indicator before sending a photo (QR code etc.)."""
    await bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_PHOTO)
    await asyncio.sleep(random.uniform(0.8, 1.5))
    await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, parse_mode="Markdown")
