import logging
from datetime import date
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

    # --- SETTINGS & CATEGORIES ---
    async def get_setting(self, key: str, default_value: str = "") -> str:
        try:
            res = self.supabase.table("settings").select("value").eq("key", key).execute()
            if res.data:
                return res.data[0]["value"]
            return default_value
        except Exception as e:
            logger.error(f"Error fetching setting {key}: {e}")
            return default_value

    async def update_setting(self, key: str, value: str) -> bool:
        try:
            self.supabase.table("settings").upsert({"key": key, "value": value}).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating setting {key}: {e}")
            return False

    async def get_categories(self) -> list:
        try:
            res = self.supabase.table("task_categories").select("*").execute()
            return res.data if res.data else []
        except Exception as e:
            logger.error(f"Error fetching categories: {e}")
            return []

    async def toggle_category(self, cat_key: str) -> bool:
        try:
            res = self.supabase.table("task_categories").select("is_enabled").eq("category_key", cat_key).execute()
            if res.data:
                current = res.data[0]["is_enabled"]
                new_val = not current
                self.supabase.table("task_categories").update({"is_enabled": new_val}).eq("category_key", cat_key).execute()
                return new_val
            return False
        except Exception as e:
            logger.error(f"Error toggling category: {e}")
            return False

    # --- SMART USER MANAGEMENT (स्मार्ट রেফারেল হ্যান্ডলিং) ---
    async def get_or_create_user(self, user_id: int, username: str, referred_by: int = None) -> dict:
        try:
            res = self.supabase.table("users").select("*").eq("user_id", user_id).execute()
            if not res.data:
                # একদম নতুন ইউজার হলে ডাটাবেজে ইনসার্ট হবে
                user_data = {
                    "user_id": user_id,
                    "username": username or f"User_{user_id}",
                    "balance": 0.0,
                    "completed_tasks": 0,
                    "referred_by": referred_by if referred_by != user_id else None,
                    "referral_count": 0,
                    "referral_income": 0.0,
                    "is_banned": False
                }
                inserted = self.supabase.table("users").insert(user_data).execute()
                
                # যদি রেফারার থাকে, তবে তার রেফার কাউন্ট বাড়িয়ে দেওয়া
                if referred_by and referred_by != user_id:
                    ref_res = self.supabase.table("users").select("referral_count").eq("user_id", referred_by).execute()
                    if ref_res.data:
                        current_count = int(ref_res.data[0].get("referral_count", 0))
                        self.supabase.table("users").update({"referral_count": current_count + 1}).eq("user_id", referred_by).execute()

                return inserted.data[0] if inserted.data else user_data
            else:
                # ইউজার যদি আগে থেকেই থাকে কিন্তু তার কোনো `referred_by` না থাকে এবং সে এখন নতুন কোনো রেফারেল লিংকে ক্লিক করে
                user = res.data[0]
                if not user.get("referred_by") and referred_by and referred_by != user_id:
                    # নিজের নিজেকে রেফার করতে পারবে না
                    self.supabase.table("users").update({"referred_by": referred_by}).eq("user_id", user_id).execute()
                    
                    # রেফারারের কাউন্ট আপডেট করা
                    ref_res = self.supabase.table("users").select("referral_count").eq("user_id", referred_by).execute()
                    if ref_res.data:
                        current_count = int(ref_res.data[0].get("referral_count", 0))
                        self.supabase.table("users").update({"referral_count": current_count + 1}).eq("user_id", referred_by).execute()
                        
                    user["referred_by"] = referred_by
                
                return user
        except Exception as e:
            logger.error(f"Error in get_or_create_user: {e}")
            return {"user_id": user_id, "balance": 0.0, "completed_tasks": 0, "is_banned": False}

    async def get_users_paginated(self, page: int = 1, limit: int = 6) -> list:
        start = (page - 1) * limit
        end = start + limit - 1
        try:
            res = self.supabase.table("users").select("user_id, username, balance, is_banned, completed_tasks").range(start, end).execute()
            return res.data if res.data else []
        except Exception as e:
            logger.error(f"Error fetching paginated users: {e}")
            return []

    async def claim_daily_bonus(self, user_id: int) -> tuple[bool, str, float]:
        try:
            user = await self.get_or_create_user(user_id, "")
            today_str = date.today().isoformat()
            
            if user.get("last_checkin") == today_str:
                return False, "⚠️ আপনি আজকের বোনাস ইতিমধ্যেই দাবি করেছেন! আগামীকাল আবার চেষ্টা করুন।", 0.0

            bonus_amount = float(await self.get_setting("daily_bonus", "1.0"))
            new_balance = float(user.get("balance", 0.0)) + bonus_amount

            self.supabase.table("users").update({
                "balance": new_balance,
                "last_checkin": today_str
            }).eq("user_id", user_id).execute()

            return True, f"🎉 আপনি সফলভাবে <b>+{bonus_amount} BDT</b> ডেইলি বোনাস পেয়েছেন!", bonus_amount
        except Exception as e:
            logger.error(f"Error claiming daily bonus: {e}")
            return False, "⚠️ বোনাস ক্লেইম করতে সমস্যা হয়েছে।", 0.0

    async def get_all_user_ids(self) -> list:
        try:
            res = self.supabase.table("users").select("user_id").execute()
            return [r["user_id"] for r in res.data] if res.data else []
        except Exception as e:
            logger.error(f"Error fetching user ids: {e}")
            return []

    async def set_user_ban_status(self, user_id: int, ban: bool) -> bool:
        try:
            self.supabase.table("users").update({"is_banned": ban}).eq("user_id", user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error updating ban status: {e}")
            return False

    # --- TASK MANAGEMENT ---
    async def add_bulk_tasks(self, task_list: list) -> int:
        try:
            res = self.supabase.table("tasks").insert(task_list).execute()
            return len(res.data) if res.data else 0
        except Exception as e:
            logger.error(f"Error adding bulk tasks: {e}")
            return 0

    async def get_available_task(self) -> dict | None:
        try:
            res = self.supabase.table("tasks").select("*").eq("status", "available").limit(1).execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Error fetching available task: {e}")
            return None

    async def complete_task(self, task_id: int, user_id: int, reward: float) -> bool:
        try:
            if task_id != 0:
                self.supabase.table("tasks").update({
                    "status": "completed", 
                    "assigned_to": user_id
                }).eq("id", task_id).execute()
            
            user = await self.get_or_create_user(user_id, "")
            new_balance = float(user.get("balance", 0.0)) + reward
            new_completed = int(user.get("completed_tasks", 0)) + 1
            
            self.supabase.table("users").update({
                "balance": new_balance,
                "completed_tasks": new_completed
            }).eq("user_id", user_id).execute()
            
            referred_by = user.get("referred_by")
            if referred_by:
                commission_pct = float(await self.get_setting("referral_commission", "10.0")) / 100.0
                referrer_res = self.supabase.table("users").select("*").eq("user_id", referred_by).execute()
                if referrer_res.data:
                    referrer = referrer_res.data[0]
                    commission = reward * commission_pct
                    new_ref_balance = float(referrer.get("balance", 0.0)) + commission
                    new_ref_income = float(referrer.get("referral_income", 0.0)) + commission
                    
                    self.supabase.table("users").update({
                        "balance": new_ref_balance,
                        "referral_income": new_ref_income
                    }).eq("user_id", referred_by).execute()
            
            return True
        except Exception as e:
            logger.error(f"Error completing task: {e}")
            return False

    # --- WITHDRAWAL MANAGEMENT ---
    async def create_withdrawal(self, user_id: int, amount: float, method: str, account_no: str) -> bool:
        try:
            user = await self.get_or_create_user(user_id, "")
            current_balance = float(user.get("balance", 0.0))
            
            if current_balance < amount:
                return False

            new_balance = current_balance - amount
            self.supabase.table("users").update({"balance": new_balance}).eq("user_id", user_id).execute()

            withdrawal_data = {
                "user_id": user_id,
                "amount": amount,
                "method": method,
                "account_no": account_no,
                "status": "pending"
            }
            self.supabase.table("withdrawals").insert(withdrawal_data).execute()
            return True
        except Exception as e:
            logger.error(f"Error creating withdrawal: {e}")
            return False

    async def get_pending_withdrawals(self) -> list:
        try:
            res = self.supabase.table("withdrawals").select("*").eq("status", "pending").execute()
            return res.data if res.data else []
        except Exception as e:
            logger.error(f"Error fetching withdrawals: {e}")
            return []

    async def update_withdrawal_status(self, withdrawal_id: int, status: str) -> tuple[bool, dict | None]:
        try:
            res = self.supabase.table("withdrawals").select("*").eq("id", withdrawal_id).execute()
            if not res.data:
                return False, None
            
            req = res.data[0]
            if req["status"] != "pending":
                return False, None

            self.supabase.table("withdrawals").update({"status": status}).eq("id", withdrawal_id).execute()

            if status == "rejected":
                user_id = req["user_id"]
                amount = float(req["amount"])
                user = await self.get_or_create_user(user_id, "")
                refund_balance = float(user.get("balance", 0.0)) + amount
                self.supabase.table("users").update({"balance": refund_balance}).eq("user_id", user_id).execute()

            return True, req
        except Exception as e:
            logger.error(f"Error updating withdrawal status: {e}")
            return False, None

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
