import logging
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        try:
            self.supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Supabase connected successfully.")
        except Exception as e:
            logger.error(f"❌ Supabase connection failed: {e}")
            raise e

    async def get_or_create_user(self, user_id: int, username: str) -> dict:
        """ইউজার ডেটাবেজে না থাকলে তৈরি করবে, থাকলে রিটার্ন করবে"""
        try:
            res = self.supabase.table("users").select("*").eq("user_id", user_id).execute()
            if not res.data:
                user_data = {
                    "user_id": user_id,
                    "username": username,
                    "balance": 0.0,
                    "completed_tasks": 0
                }
                inserted = self.supabase.table("users").insert(user_data).execute()
                return inserted.data[0] if inserted.data else user_data
            return res.data[0]
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return {"user_id": user_id, "balance": 0.0, "completed_tasks": 0}

    async def add_bulk_tasks(self, task_list: list) -> int:
        """এডমিন প্যানেল থেকে একসাথে একাধিক টাস্ক যুক্ত করা"""
        try:
            res = self.supabase.table("tasks").insert(task_list).execute()
            return len(res.data) if res.data else 0
        except Exception as e:
            logger.error(f"Error adding bulk tasks: {e}")
            return 0

    async def get_available_task(self) -> dict | None:
        """স্টক থেকে একটি খালি টাস্ক ফেচ করা"""
        try:
            res = self.supabase.table("tasks").select("*").eq("status", "available").limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Error fetching available task: {e}")
            return None

    async def complete_task(self, task_id: int, user_id: int, reward: float) -> bool:
        """টাস্ক কমপ্লিট হলে স্ট্যাটাস আপডেট এবং ইউজারের ব্যালেন্স যোগ করা"""
        try:
            # ১. টাস্ক স্ট্যাটাস আপডেট
            self.supabase.table("tasks").update({
                "status": "completed", 
                "assigned_to": user_id
            }).eq("id", task_id).execute()
            
            # ২. ইউজারের ব্যালেন্স ও টাস্ক কাউন্ট আপডেট
            user = await self.get_or_create_user(user_id, "")
            new_balance = float(user.get("balance", 0.0)) + reward
            new_completed = int(user.get("completed_tasks", 0)) + 1
            
            self.supabase.table("users").update({
                "balance": new_balance,
                "completed_tasks": new_completed
            }).eq("user_id", user_id).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            return False

    async def get_all_users_count(self) -> int:
        try:
            res = self.supabase.table("users").select("user_id", count="exact").execute()
            return res.count if hasattr(res, 'count') and res.count is not None else 0
        except Exception:
            return 0

    async def get_stock_count(self) -> int:
        try:
            res = self.supabase.table("tasks").select("id", count="exact").eq("status", "available").execute()
            return res.count if hasattr(res, 'count') and res.count is not None else 0
        except Exception:
            return 0

db = Database()
