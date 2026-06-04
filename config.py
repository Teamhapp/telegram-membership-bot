import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# Community info — edit these
COMMUNITY_NAME = os.getenv("COMMUNITY_NAME", "Premium Community")
COMMUNITY_DESCRIPTION = os.getenv("COMMUNITY_DESCRIPTION", "Daily updates, community access and premium content.")

# Pricing
PRICE_MONTHLY = os.getenv("PRICE_MONTHLY", "₹999")
PRICE_LABEL = os.getenv("PRICE_LABEL", "month")

# Payment
PAYMENT_MODE = os.getenv("PAYMENT_MODE", "qr")  # "qr" or "link"
PAYMENT_UPI_ID = os.getenv("PAYMENT_UPI_ID", "")
PAYMENT_QR_IMAGE = os.getenv("PAYMENT_QR_IMAGE", "")  # path to QR image file
PAYMENT_LINK = os.getenv("PAYMENT_LINK", "")
PAYMENT_NAME = os.getenv("PAYMENT_NAME", "")  # merchant name shown in UPI

# Access
CHANNEL_ID = os.getenv("CHANNEL_ID", "")  # e.g. -1001234567890
INVITE_LINK_EXPIRE_HOURS = int(os.getenv("INVITE_LINK_EXPIRE_HOURS", "24"))
SUBSCRIPTION_DAYS = int(os.getenv("SUBSCRIPTION_DAYS", "30"))

# DB
DB_PATH = os.getenv("DB_PATH", "bot.db")

# API
API_SECRET = os.getenv("API_SECRET", "")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Razorpay
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

# Rate limiting
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "15"))

# Conversation pruning — keep last N messages per user
CONVERSATION_MAX_MESSAGES = int(os.getenv("CONVERSATION_MAX_MESSAGES", "100"))

# FAQ notification threshold
FAQ_NOTIFY_THRESHOLD = int(os.getenv("FAQ_NOTIFY_THRESHOLD", "5"))

# Webhook mode (production) vs polling (development)
# Set WEBHOOK_URL to enable webhook mode e.g. https://yourdomain.com
WEBHOOK_MODE = os.getenv("WEBHOOK_URL", "") != ""
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
