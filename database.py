import asyncio
import logging
import math
import random
import time
from datetime import datetime, timedelta, timezone

from supabase import AsyncClient, acreate_client

from config import INSTANCE_ID, LOCK_TTL, SUPABASE_KEY, SUPABASE_URL, TASK_STALE_MINUTES

logger = logging.getLogger(__name__)

BD_TZ = timezone(timedelta(hours=6))          # daily bonus resets at midnight Bangladesh time
FLOAT_FIELDS = {"balance", "referral_income"}
DEFAULT_SETTINGS = {
    "min_withdraw": "50.0",
    "referral_commission": "10.0",
    "daily_bonus": "1.0",
    "proof_channel": "",
}
LOCK_ROW_ID = 1


def today_bd() -> str:
    return datetime.now(BD_TZ).date().isoformat()


class Database:
    def __init__(self):
        self.client: AsyncClient | None = None
        self._ban_cache: dict[int, tuple[float, bool]] = {}
        self._lock_available = True

    async def connect(self) -> None:
        try:
            self.client = await acreate_client(SUPABASE_URL, SUPABASE_KEY)
            await self.client.table("settings").select("key").limit(1).execute()
            logger.info("✅ Supabase (async) connected successfully.")
        except Exception as e:  # noqa: BLE001
            logger.error("❌ Supabase connection failed: %s", e)
            raise

    # ------------------------------------------------------------------
    # SETTINGS & CATEGORIES (always read live from the DB)
    # ------------------------------------------------------------------
    async def get_setting(self, key: str, default_value: str | None = None) -> str:
        fallback = DEFAULT_SETTINGS.get(key, "") if default_value is None else default_value
        try:
            res = await self.client.table("settings").select("value").eq("key", key).limit(1).execute()
            if res.data and res.data[0].get("value") is not None:
                return str(res.data[0]["value"])
            return fallback
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching setting %s: %s", key, e)
            return fallback

    async def get_float_setting(self, key: str, default: float) -> float:
        raw = await self.get_setting(key, str(default))
        try:
            value = float(str(raw).strip())
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    async def update_setting(self, key: str, value: str) -> bool:
        try:
            await self.client.table("settings").upsert({"key": key, "value": str(value)}, on_conflict="key").execute()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Error updating setting %s: %s", key, e)
            return False

    async def get_categories(self) -> list:
        try:
            res = await self.client.table("task_categories").select("*").order("category_key").execute()
            return res.data or []
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching categories: %s", e)
            return []

    async def is_category_enabled(self, cat_key: str) -> bool:
        try:
            res = await self.client.table("task_categories").select("is_enabled").eq("category_key", cat_key).limit(1).execute()
            return bool(res.data and res.data[0].get("is_enabled"))
        except Exception as e:  # noqa: BLE001
            logger.error("Error checking category %s: %s", cat_key, e)
            return False

    async def toggle_category(self, cat_key: str) -> bool:
        try:
            res = await self.client.table("task_categories").select("is_enabled").eq("category_key", cat_key).limit(1).execute()
            if not res.data:
                return False
            new_val = not bool(res.data[0]["is_enabled"])
            await self.client.table("task_categories").update({"is_enabled": new_val}).eq("category_key", cat_key).execute()
            return new_val
        except Exception as e:  # noqa: BLE001
            logger.error("Error toggling category: %s", e)
            return False

    # ------------------------------------------------------------------
    # ATOMIC NUMERIC UPDATES (compare-and-swap, no lost updates)
    # ------------------------------------------------------------------
    async def _apply_deltas(
        self,
        user_id: int,
        deltas: dict,
        forbid_negative_balance: bool = False,
        retries: int = 8,
    ) -> tuple[str, dict | None]:
        fields = list(deltas.keys())
        for attempt in range(retries):
            res = await self.client.table("users").select(",".join(fields)).eq("user_id", user_id).limit(1).execute()
            if not res.data:
                return "missing", None
            row = res.data[0]

            new_vals = {}
            for f in fields:
                old = row.get(f) or 0
                if f in FLOAT_FIELDS:
                    new_vals[f] = round(float(old) + float(deltas[f]), 4)
                else:
                    new_vals[f] = int(old) + int(deltas[f])

            if forbid_negative_balance and new_vals.get("balance", 0) < 0:
                return "insufficient", row

            query = self.client.table("users").update(new_vals).eq("user_id", user_id)
            for f in fields:
                query = query.is_(f, "null") if row.get(f) is None else query.eq(f, row[f])
            upd = await query.execute()
            if upd.data:
                return "ok", upd.data[0]

            await asyncio.sleep(0.05 * (attempt + 1) + random.random() * 0.05)
        return "conflict", None

    # ------------------------------------------------------------------
    # USERS
    # ------------------------------------------------------------------
    async def get_user(self, user_id: int) -> dict | None:
        res = await self.client.table("users").select("*").eq("user_id", user_id).limit(1).execute()
        return res.data[0] if res.data else None

    async def get_or_create_user(self, user_id: int, username: str = "", referred_by: int | None = None) -> dict:
        try:
            user = await self.get_user(user_id)
            if user:
                if username and user.get("username") != username:
                    await self.client.table("users").update({"username": username}).eq("user_id", user_id).execute()
                    user["username"] = username
                return user

            valid_ref = None
            if referred_by and referred_by != user_id and await self.get_user(referred_by):
                valid_ref = referred_by

            user_data = {
                "user_id": user_id,
                "username": username or f"User_{user_id}",
                "balance": 0.0,
                "completed_tasks": 0,
                "referred_by": valid_ref,
                "referral_count": 0,
                "referral_income": 0.0,
                "is_banned": False,
            }
            try:
                inserted = await self.client.table("users").insert(user_data).execute()
            except Exception:  # noqa: BLE001
                existing = await self.get_user(user_id)
                if existing:
                    return existing
                raise

            if valid_ref:
                await self._apply_deltas(valid_ref, {"referral_count": 1})
            return inserted.data[0] if inserted.data else user_data
        except Exception as e:  # noqa: BLE001
            logger.error("Error in get_or_create_user(%s): %s", user_id, e)
            return {"user_id": user_id, "username": username, "balance": 0.0, "completed_tasks": 0,
                    "referral_count": 0, "referral_income": 0.0, "is_banned": False}

    async def is_banned(self, user_id: int) -> bool:
        now = time.monotonic()
        cached = self._ban_cache.get(user_id)
        if cached and now - cached[0] < 20:
            return cached[1]
        try:
            res = await self.client.table("users").select("is_banned").eq("user_id", user_id).limit(1).execute()
            banned = bool(res.data and res.data[0].get("is_banned"))
        except Exception as e:  # noqa: BLE001
            logger.error("Error checking ban status: %s", e)
            return False
        self._ban_cache[user_id] = (now, banned)
        return banned

    async def set_user_ban_status(self, user_id: int, ban: bool) -> bool:
        try:
            res = await self.client.table("users").update({"is_banned": ban}).eq("user_id", user_id).execute()
            if not res.data:
                return False
            self._ban_cache[user_id] = (time.monotonic(), ban)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("Error updating ban status: %s", e)
            return False

    async def get_users_paginated(self, page: int = 1, limit: int = 6) -> tuple[list, int]:
        page = max(1, page)
        start = (page - 1) * limit
        try:
            res = (
                await self.client.table("users")
                .select("user_id, username, balance, is_banned, completed_tasks", count="exact")
                .order("user_id")
                .range(start, start + limit - 1)
                .execute()
            )
            return res.data or [], int(res.count or 0)
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching paginated users: %s", e)
            return [], 0

    async def get_all_users_count(self) -> int:
        try:
            res = await self.client.table("users").select("user_id", count="exact").limit(1).execute()
            return int(res.count or 0)
        except Exception:  # noqa: BLE001
            return 0

    async def get_broadcast_user_ids(self) -> list[int]:
        ids: list[int] = []
        start, size = 0, 1000
        try:
            while True:
                res = (
                    await self.client.table("users")
                    .select("user_id")
                    .or_("is_banned.is.null,is_banned.eq.false")
                    .order("user_id")
                    .range(start, start + size - 1)
                    .execute()
                )
                batch = [r["user_id"] for r in (res.data or [])]
                ids.extend(batch)
                if len(batch) < size:
                    break
                start += size
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching broadcast ids: %s", e)
        return ids

    async def claim_daily_bonus(self, user_id: int) -> tuple[bool, str, float]:
        try:
            user = await self.get_or_create_user(user_id, "")
            today = today_bd()
            bonus = await self.get_float_setting("daily_bonus", 1.0)
            if bonus <= 0:
                return False, "⚠️ ডেইলি বোনাস বর্তমানে বন্ধ আছে।", 0.0

            marked = (
                await self.client.table("users")
                .update({"last_checkin": today})
                .eq("user_id", user_id)
                .or_(f"last_checkin.is.null,last_checkin.neq.{today}")
                .execute()
            )
            if not marked.data:
                return False, "⚠️ আপনি আজকের বোনাস ইতিমধ্যেই দাবি করেছেন! আগামীকাল আবার চেষ্টা করুন।", 0.0

            status, _ = await self._apply_deltas(user_id, {"balance": bonus})
            if status != "ok":
                await self.client.table("users").update({"last_checkin": user.get("last_checkin")}).eq("user_id", user_id).execute()
                return False, "⚠️ বোনাস ক্লেইম করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।", 0.0

            return True, f"🎉 আপনি সফলভাবে <b>+{bonus:g} BDT</b> ডেইলি বোনাস পেয়েছেন!", bonus
        except Exception as e:  # noqa: BLE001
            logger.error("Error claiming daily bonus: %s", e)
            return False, "⚠️ বোনাস ক্লেইম করতে সমস্যা হয়েছে।", 0.0

    # ------------------------------------------------------------------
    # TASKS
    # ------------------------------------------------------------------
    async def add_bulk_tasks(self, task_list: list) -> int:
        inserted = 0
        try:
            for i in range(0, len(task_list), 200):
                res = await self.client.table("tasks").insert(task_list[i:i + 200]).execute()
                inserted += len(res.data or [])
        except Exception as e:  # noqa: BLE001
            logger.error("Error adding bulk tasks: %s", e)
        return inserted

    async def get_stock_count(self) -> int:
        try:
            res = await self.client.table("tasks").select("id", count="exact").eq("status", "available").limit(1).execute()
            return int(res.count or 0)
        except Exception:  # noqa: BLE001
            return 0

    async def get_user_assigned_task(self, user_id: int) -> dict | None:
        try:
            res = (
                await self.client.table("tasks").select("*")
                .eq("assigned_to", user_id).eq("status", "assigned")
                .order("id", desc=True).limit(1).execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching assigned task: %s", e)
            return None

    async def _release_stale_tasks(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=TASK_STALE_MINUTES)).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            await (
                self.client.table("tasks")
                .update({"status": "available", "assigned_to": None, "assigned_at": None})
                .eq("status", "assigned").lt("assigned_at", cutoff).execute()
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("Stale task release skipped: %s", e)

    async def claim_task(self, user_id: int, fallback_task: dict | None = None) -> dict | None:
        try:
            existing = await self.get_user_assigned_task(user_id)
            if existing:
                return existing

            await self._release_stale_tasks()
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            for _ in range(5):
                res = await self.client.table("tasks").select("id").eq("status", "available").order("id").limit(1).execute()
                if not res.data:
                    break
                taken = (
                    await self.client.table("tasks")
                    .update({"status": "assigned", "assigned_to": user_id, "assigned_at": now_iso})
                    .eq("id", res.data[0]["id"]).eq("status", "available").execute()
                )
                if taken.data:
                    return taken.data[0]
                await asyncio.sleep(0.05)

            if fallback_task:
                row = dict(fallback_task)
                row.update({"status": "assigned", "assigned_to": user_id, "assigned_at": now_iso})
                created = await self.client.table("tasks").insert(row).execute()
                return created.data[0] if created.data else None
            return None
        except Exception as e:  # noqa: BLE001
            logger.error("Error claiming task: %s", e)
            return None

    async def release_user_task(self, user_id: int) -> None:
        try:
            await (
                self.client.table("tasks")
                .update({"status": "available", "assigned_to": None, "assigned_at": None})
                .eq("assigned_to", user_id).eq("status", "assigned").execute()
            )
        except Exception as e:  # noqa: BLE001
            logger.error("Error releasing task: %s", e)

    async def complete_task(self, task_id: int, user_id: int) -> dict | None:
        try:
            res = (
                await self.client.table("tasks").update({"status": "completed"})
                .eq("id", task_id).eq("assigned_to", user_id).eq("status", "assigned").execute()
            )
            if not res.data:
                return None
            reward = float(res.data[0].get("reward") or 0)

            status, user_row = await self._apply_deltas(user_id, {"balance": reward, "completed_tasks": 1})
            if status != "ok":
                await self.client.table("tasks").update({"status": "assigned"}).eq("id", task_id).execute()
                return None

            result = {"reward": reward, "referrer_id": None, "commission": 0.0}
            referrer_id = (user_row or {}).get("referred_by")
            if referrer_id and referrer_id != user_id:
                pct = await self.get_float_setting("referral_commission", 10.0)
                commission = round(reward * max(pct, 0.0) / 100.0, 4)
                if commission > 0:
                    ref_status, _ = await self._apply_deltas(
                        referrer_id, {"balance": commission, "referral_income": commission}
                    )
                    if ref_status == "ok":
                        result.update({"referrer_id": referrer_id, "commission": commission})
            return result
        except Exception as e:  # noqa: BLE001
            logger.error("Error completing task %s: %s", task_id, e)
            return None

    # ------------------------------------------------------------------
    # NEW STOCK MANAGEMENT METHODS (Facebook & Instagram File Upload)
    # ------------------------------------------------------------------
    async def add_stock_account(self, category: str, account_data: str) -> bool:
        """স্টক টেবিলে নতুন অ্যাকাউন্ট বা টাস্ক যুক্ত করে"""
        try:
            await self.client.table("stock_accounts").insert({
                "category": category,
                "account_data": account_data,
                "is_used": False
            }).execute()
            return True
        except Exception as e:
            logger.error("Error adding stock account: %s", e)
            return False

    async def get_unused_stock(self, category: str) -> dict | None:
        """স্টক থেকে অব্যবহৃত একটি ফ্রেস অ্যাকাউন্ট নিয়ে আসে"""
        try:
            res = await self.client.table("stock_accounts") \
                .select("*") \
                .eq("category", category) \
                .eq("is_used", False) \
                .limit(1) \
                .execute()
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error("Error fetching unused stock for %s: %s", category, e)
            return None

    async def mark_stock_as_used(self, stock_id: int, user_id: int) -> None:
        """স্টক আইটেমটিকে used হিসেবে মার্ক করে যাতে অন্য কেউ না পায়"""
        try:
            await self.client.table("stock_accounts") \
                .update({"is_used": True, "assigned_to": user_id}) \
                .eq("id", stock_id) \
                .execute()
        except Exception as e:
            logger.error("Error marking stock as used: %s", e)

    # ------------------------------------------------------------------
    # SUBMISSIONS & ADMIN REVIEWS
    # ------------------------------------------------------------------
    async def add_submission(self, user_id: int, category: str, data: str, status: str = "pending") -> int | None:
        try:
            res = await self.client.table("user_submissions").insert({
                "user_id": user_id,
                "category": category,
                "details": data,
                "status": status,
            }).execute()
            return res.data[0]["id"] if res.data else None
        except Exception as e:  # noqa: BLE001
            logger.error("Error saving %s submission: %s", category, e)
            return None

    async def update_submission_status(self, sub_id: str, status: str) -> bool:
        try:
            await self.client.table("user_submissions").update({"status": status}).eq("id", sub_id).execute()
            return True
        except Exception as e:
            logger.error("Error updating submission status: %s", e)
            return False

    async def get_accepted_submissions(self) -> list:
        try:
            res = await self.client.table("user_submissions").select("*").eq("status", "accepted").execute()
            return res.data or []
        except Exception as e:
            logger.error("Error fetching accepted submissions: %s", e)
            return []

    async def add_user_balance(self, user_id: int, amount: float) -> bool:
        status, _ = await self._apply_deltas(user_id, {"balance": amount})
        return status == "ok"

    # ------------------------------------------------------------------
    # WITHDRAWALS
    # ------------------------------------------------------------------
    async def create_withdrawal(self, user_id: int, amount: float, method: str, account_no: str) -> tuple[str, dict | None]:
        try:
            min_withdraw = await self.get_float_setting("min_withdraw", 50.0)
            if amount < min_withdraw:
                return "below_min", None

            status, _ = await self._apply_deltas(user_id, {"balance": -amount}, forbid_negative_balance=True)
            if status == "insufficient":
                return "insufficient", None
            if status != "ok":
                return "error", None

            try:
                res = await self.client.table("withdrawals").insert({
                    "user_id": user_id,
                    "amount": amount,
                    "method": method,
                    "account_no": account_no,
                    "status": "pending",
                }).execute()
            except Exception as e:  # noqa: BLE001
                logger.error("Withdrawal insert failed, refunding %s: %s", user_id, e)
                await self._apply_deltas(user_id, {"balance": amount})
                return "error", None
            return "ok", (res.data[0] if res.data else None)
        except Exception as e:  # noqa: BLE001
            logger.error("Error creating withdrawal: %s", e)
            return "error", None

    async def get_pending_withdrawals(self, limit: int = 20) -> tuple[list, int]:
        try:
            res = (
                await self.client.table("withdrawals").select("*", count="exact")
                .eq("status", "pending").order("id").limit(limit).execute()
            )
            return res.data or [], int(res.count or 0)
        except Exception as e:  # noqa: BLE001
            logger.error("Error fetching withdrawals: %s", e)
            return [], 0

    async def count_pending_withdrawals(self) -> int:
        try:
            res = await self.client.table("withdrawals").select("id", count="exact").eq("status", "pending").limit(1).execute()
            return int(res.count or 0)
        except Exception:  # noqa: BLE001
            return 0

    async def update_withdrawal_status(self, withdrawal_id: int, status: str) -> tuple[bool, dict | None]:
        try:
            res = (
                await self.client.table("withdrawals").update({"status": status})
                .eq("id", withdrawal_id).eq("status", "pending").execute()
            )
            if not res.data:
                return False, None
            req = res.data[0]

            if status == "rejected":
                refund_status, _ = await self._apply_deltas(req["user_id"], {"balance": float(req["amount"])})
                if refund_status != "ok":
                    await self.client.table("withdrawals").update({"status": "pending"}).eq("id", withdrawal_id).execute()
                    logger.error("Refund failed for withdrawal %s; reverted to pending", withdrawal_id)
                    return False, None
            return True, req
        except Exception as e:  # noqa: BLE001
            logger.error("Error updating withdrawal status: %s", e)
            return False, None

    # ------------------------------------------------------------------
    # SINGLE-INSTANCE LEASE (prevents TelegramConflictError on deploys)
    # ------------------------------------------------------------------
    async def acquire_leader(self) -> bool | None:
        if not self._lock_available:
            return None
        now = int(time.time())
        try:
            res = (
                await self.client.table("bot_lock")
                .update({"owner": INSTANCE_ID, "heartbeat": now})
                .eq("id", LOCK_ROW_ID)
                .or_(f"owner.eq.{INSTANCE_ID},heartbeat.lt.{now - LOCK_TTL}")
                .execute()
            )
            if res.data:
                return True
            exists = await self.client.table("bot_lock").select("id").eq("id", LOCK_ROW_ID).limit(1).execute()
            if exists.data:
                return False
            try:
                await self.client.table("bot_lock").insert({"id": LOCK_ROW_ID, "owner": INSTANCE_ID, "heartbeat": now}).execute()
                return True
            except Exception:  # noqa: BLE001
                return False
        except Exception as e:  # noqa: BLE001
            logger.warning("⚠️ bot_lock unavailable (%s) - running without single-instance protection.", e)
            self._lock_available = False
            return None

    async def renew_leader(self) -> str:
        try:
            res = (
                await self.client.table("bot_lock")
                .update({"heartbeat": int(time.time())})
                .eq("id", LOCK_ROW_ID).eq("owner", INSTANCE_ID).execute()
            )
            return "ok" if res.data else "lost"
        except Exception as e:  # noqa: BLE001
            logger.warning("Lease renew failed: %s", e)
            return "error"

    async def release_leader(self) -> None:
        if not self._lock_available or self.client is None:
            return
        try:
            await self.client.table("bot_lock").update({"heartbeat": 0}).eq("id", LOCK_ROW_ID).eq("owner", INSTANCE_ID).execute()
        except Exception as e:  # noqa: BLE001
            logger.warning("Lease release failed: %s", e)


db = Database()
