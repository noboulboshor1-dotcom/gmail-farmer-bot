import os
from dotenv import load_dotenv

# .env ফাইল থেকে এনভায়রনমেন্ট ভ্যারিয়েবল লোড করা
load_dotenv()

# টেলিগ্রাম বট টোকেন এবং সুপাবেজ ক্র্যাডেনশিয়াল
BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# একাধিক এডমিন আইডি হ্যান্ডেল করার লজিক
# Render-এর Environment Variable-এ কমা দিয়ে একাধিক আইডি দেওয়া যাবে (যেমন: 12345678,98765432)
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "")

ADMIN_IDS = []
if ADMIN_ID_RAW:
    for item in ADMIN_ID_RAW.split(","):
        clean_item = item.strip()
        if clean_item.isdigit():
            ADMIN_IDS.append(int(clean_item))

# যদি কোনো এডমিন আইডি না থাকে তবে ডিফল্ট খালি লিস্ট থাকবে
# ভ্যালিডেশন চেক
if not BOT_TOKEN:
    raise ValueError("❌ Error: BOT_TOKEN is missing in environment variables!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ Error: Supabase credentials (URL/Key) are missing!")
