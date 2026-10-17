import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

class Database:
    def __init__(self):
        self.headers = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

    async def get_or_create_user(self, telegram_id: int, username: str):
        if not SUPABASE_URL or not SUPABASE_KEY:
            return {"balance": 0.0, "completed_tasks": 0} # যদি সুপাবেজ কানেক্ট না থাকে

        url = f"{SUPABASE_URL}/rest/v1/users?telegram_id=eq.{telegram_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        return data[0]
                    
        # নতুন ইউজার তৈরি
        insert_url = f"{SUPABASE_URL}/rest/v1/users"
        payload = {"telegram_id": telegram_id, "username": username, "balance": 0.0, "completed_tasks": 0}
        async with aiohttp.ClientSession() as session:
            async with session.post(insert_url, headers=self.headers, json=payload) as resp:
                if resp.status in (200, 201):
                    res = await resp.json()
                    return res[0] if res else payload
                return payload

db = Database()
