import logging
import os
import re
import uuid

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# --- Core credentials -------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
# Must be the service_role key (server side only) so RLS does not block the bot.
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "").strip()

# Comma / space separated list, e.g. ADMIN_ID=12345678,98765432
ADMIN_IDS: list[int] = [
    int(item)
    for item in re.split(r"[,\s]+", os.getenv("ADMIN_ID", ""))
    if item.strip().isdigit()
]

# --- Validation -------------------------------------------------------------
if not BOT_TOKEN:
    raise ValueError("❌ Error: BOT_TOKEN is missing in environment variables!")
if not re.fullmatch(r"\d{5,}:[\w-]{30,}", BOT_TOKEN):
    raise ValueError("❌ Error: BOT_TOKEN format looks invalid (expected 123456:ABC...).")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Error: Supabase credentials (SUPABASE_URL / SUPABASE_KEY) are missing!")
if not ADMIN_IDS:
    logger.warning("⚠️ ADMIN_ID is empty - the admin panel will be unreachable.")

# --- Runtime / hosting ------------------------------------------------------
PORT = _env_int("PORT", 10000)
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@AdminSupport")

# --- Single-instance (TelegramConflictError protection) ---------------------
# Unique per process; only the instance holding the DB lease may poll Telegram.
INSTANCE_ID = os.getenv("INSTANCE_ID") or uuid.uuid4().hex[:12]
LOCK_TTL = _env_int("LOCK_TTL", 45)                  # seconds before a silent leader is considered dead
LOCK_RENEW_SECONDS = _env_int("LOCK_RENEW_SECONDS", 10)
LOCK_RETRY_SECONDS = _env_int("LOCK_RETRY_SECONDS", 5)

# --- Tasks ------------------------------------------------------------------
TASK_STALE_MINUTES = _env_int("TASK_STALE_MINUTES", 30)   # abandoned tasks return to stock
# Gmail verifier: require the Gmail address to be mentioned in Google's mail.
VERIFY_REQUIRE_ADDRESS = _env_bool("VERIFY_REQUIRE_ADDRESS", True)

# Facebook task template shown to users
FB_FIRST_NAME = os.getenv("FB_FIRST_NAME", "Sem")
FB_LAST_NAME = os.getenv("FB_LAST_NAME", "De Jong")
FB_PASSWORD = os.getenv("FB_PASSWORD", "nbbd@18")
# ক্যাটাগরিভিত্তিক ফিক্সড রিওয়ার্ড (টাকা বা পয়েন্ট)
CATEGORY_REWARDS = {
    "gmail": 10.00,      # জিমেইল টাস্কের জন্য নির্দিষ্ট অ্যামাউন্ট
    "facebook": 4.00,    # ফেসবুক টাস্কের জন্য নির্দিষ্ট অ্যামাউন্ট
    "instagram": 5.00    # ইনস্টাগ্রাম টাস্কের জন্য নির্দিষ্ট অ্যামাউন্ট
}
