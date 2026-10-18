import os
from dotenv import load_dotenv

# লোকাল ডেভেলপমেন্টের জন্য .dotenv লোড করা (রেন্ডারে অটো এনভায়রনমেন্ট থেকে নেয়)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "0")

# বেসিক ভ্যালিডেশন
if not BOT_TOKEN:
    raise ValueError("❌ Error: BOT_TOKEN is missing in environment variables!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Error: Supabase credentials are missing!")

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0
