import asyncio
import logging
import math
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from collections import defaultdict

from supabase import AsyncClient, acreate_client

from config import (
    SUPABASE_URL,
    SUPABASE_KEY,
    INSTANCE_ID,
    LOCK_TTL,
    TASK_STALE_MINUTES,
)

logger = logging.getLogger(__name__)

BD_TZ = timezone(timedelta(hours=6))
FLOAT_FIELDS = {"balance", "referral_income"}
LOCK_ROW_ID = 1

DEFAULT_SETTINGS = {
    "min_withdraw": "50.0",
    "referral_commission": "10.0",
    "daily_bonus": "1.0",
    "proof_channel": "",
}


def today_bd() -> str:
    """বর্তমান বাংলাদেশি তারিখ।"""
    return datetime.now(BD_TZ).date().isoformat()


class Database:
    def __init__(self):
        self.client: Optional[AsyncClient] = None
        self._ban_cache: dict[int, tuple[float, bool]] = {}
        self._lock_available = True
        self._state_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    # ================================================================
    # CONNECTION
    # ================================================================

    async def connect(self) -> None:
        try:
            self.client = await acreate_client(
                SUPABASE_URL,
                SUPABASE_KEY,
            )
            await self.client.table("settings").select("key").limit(1).execute()
            logger.info("Supabase async connection established.")
        except Exception:
            logger.exception("Supabase connection failed.")
            raise

    def _db(self) -> AsyncClient:
        if self.client is None:
            raise RuntimeError(
                "Database is not connected. Call await db.connect() first."
            )
        return self.client

    # ================================================================
    # FSM STATE LOCKING (prevent concurrent task processing)
    # ================================================================

    def get_user_state_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a state lock for a user to prevent concurrent task processing."""
        return self._state_locks[user_id]

    # ================================================================
    # SETTINGS
    # ================================================================

    async def get_setting(
        self,
        key: str,
        default_value: Optional[str] = None,
    ) -> str:
        fallback = (
            DEFAULT_SETTINGS.get(key, "")
            if default_value is None
            else default_value
        )
        try:
            res = await self._db().table("settings").select(
                "value"
            ).eq("key", key).limit(1).execute()

            if res.data and res.data[0].get("value") is not None:
                return str(res.data[0]["value"])

            return fallback
        except Exception:
            logger.exception("Error fetching setting %s", key)
            return fallback

    async def get_float_setting(self, key: str, default: float) -> float:
        raw = await self.get_setting(key, str(default))
        try:
            value = float(raw.strip())
            return value if math.isfinite(value) else default
        except (TypeError, ValueError, AttributeError):
            return default

    async def set_setting(self, key: str, value: str) -> bool:
        try:
            await self._db().table("settings").upsert(
                {"key": key, "value": value}
            ).execute()
            return True
        except Exception:
            logger.exception("Error setting %s", key)
            return False

    # ================================================================
    # USER MANAGEMENT
    # ================================================================

    async def get_user(self, user_id: int) -> Optional[dict]:
        try:
            res = await self._db().table("users").select(
                "*"
            ).eq("user_id", user_id).limit(1).execute()

            return res.data[0] if res.data else None
        except Exception:
            logger.exception("Error fetching user %s", user_id)
            return None

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        referred_by: Optional[int] = None,
    ) -> dict:
        user = await self.get_user(user_id)
        if user:
            return user

        valid_referrer = None
        if referred_by and referred_by != user_id:
            try:
                if referrer := await self.get_user(referred_by):
                    valid_referrer = referred_by
            except Exception:
                pass

        user_data = {
            "user_id": user_id,
            "username": username or f"User_{user_id}",
            "balance": 0.0,
            "completed_tasks": 0,
            "referral_count": 0,
            "referral_income": 0.0,
            "referred_by": valid_referrer,
            "is_banned": False,
        }

        try:
            inserted = await self._db().table(
                "users"
            ).insert(user_data).execute()
        except Exception:
            existing = await self.get_user(user_id)
            if existing:
                return existing
            raise

        if valid_referrer:
            await self._apply_deltas(
                valid_referrer,
                {"referral_count": 1},
            )

        return inserted.data[0] if inserted.data else user_data

    async def get_user_stats(self, user_id: int) -> dict:
        defaults = {
            "user_id": user_id,
            "balance": 0.0,
            "completed_tasks": 0,
            "pending_tasks": 0,
            "rejected_tasks": 0,
            "referral_count": 0,
            "referral_income": 0.0,
            "username": "Unknown",
            "referred_by": None,
        }

        try:
            user = await self.get_user(user_id)
            if not user:
                return defaults

            pending = await self._db().table(
                "user_submissions"
            ).select("id", count="exact").eq(
                "user_id", user_id
            ).eq("status", "pending").execute()

            rejected = await self._db().table(
                "user_submissions"
            ).select("id", count="exact").eq(
                "user_id", user_id
            ).eq("status", "rejected").execute()

            return {
                "user_id": user_id,
                "balance": float(user.get("balance") or 0),
                "completed_tasks": int(user.get("completed_tasks") or 0),
                "pending_tasks": int(pending.count or 0),
                "rejected_tasks": int(rejected.count or 0),
                "referral_count": int(user.get("referral_count") or 0),
                "referral_income": float(user.get("referral_income") or 0),
                "username": user.get("username", "Unknown"),
                "referred_by": user.get("referred_by"),
            }
        except Exception:
            logger.exception("Error fetching stats for %s", user_id)
            return defaults

    async def is_banned(self, user_id: int) -> bool:
        now = time.monotonic()
        cached = self._ban_cache.get(user_id)

        if cached and now - cached[0] < 20:
            return cached[1]

        try:
            res = await self._db().table("users").select(
                "is_banned"
            ).eq("user_id", user_id).limit(1).execute()

            banned = bool(
                res.data and res.data[0].get("is_banned", False)
            )
            self._ban_cache[user_id] = (now, banned)
            return banned
        except Exception:
            logger.exception("Error checking ban status for %s", user_id)
            return True

    async def set_user_ban_status(
        self,
        user_id: int,
        ban: bool,
    ) -> bool:
        try:
            res = await self._db().table("users").update(
                {"is_banned": ban}
            ).eq("user_id", user_id).select("*").execute()

            if not res.data:
                return False

            self._ban_cache[user_id] = (time.monotonic(), ban)
            return True
        except Exception:
            logger.exception("Error changing ban status")
            return False

    # ================================================================
    # ATOMIC BALANCE AND COUNTER UPDATES
    # ================================================================

    async def _apply_deltas(
        self,
        user_id: int,
        deltas: dict,
        forbid_negative_balance: bool = False,
        retries: int = 8,
    ) -> tuple[str, Optional[dict]]:
        client = self._db()
        fields = list(deltas)

        for attempt in range(retries):
            res = await client.table("users").select(
                ",".join(fields)
            ).eq("user_id", user_id).limit(1).execute()

            if not res.data:
                return "missing", None

            row = res.data[0]
            new_values = {}

            for field, delta in deltas.items():
                old = row.get(field) or 0

                if field in FLOAT_FIELDS:
                    new_values[field] = round(
                        float(old) + float(delta), 4
                    )
                else:
                    new_values[field] = int(old) + int(delta)

            if (
                forbid_negative_balance
                and new_values.get("balance", 0) < 0
            ):
                return "insufficient", row

            query = client.table("users").update(new_values).eq(
                "user_id", user_id
            )

            for field in fields:
                if row.get(field) is None:
                    query = query.is_(field, "null")
                else:
                    query = query.eq(field, row[field])

            updated = await query.select("*").execute()

            if updated.data:
                return "ok", updated.data[0]

            await asyncio.sleep(
                0.05 * (attempt + 1) + random.random() * 0.05
            )

        return "conflict", None

    async def add_user_balance(
        self,
        user_id: int,
        amount: float,
    ) -> bool:
        if not math.isfinite(amount):
            return False

        status, _ = await self._apply_deltas(
            user_id,
            {"balance": amount},
        )
        return status == "ok"

    async def apply_balance_delta_safe(
        self,
        user_id: int,
        amount: float,
        reason: str = "unspecified",
    ) -> tuple[bool, Optional[float]]:
        if not math.isfinite(amount) or amount == 0:
            return False, None

        status, updated = await self._apply_deltas(
            user_id,
            {"balance": amount},
        )

        if status == "ok":
            new_balance = updated.get("balance", 0.0) if updated else None
            return True, new_balance
        elif status == "insufficient":
            return False, None
        else:
            return False, None

    # ================================================================
    # TASK & GMAIL MANAGEMENT
    # ================================================================

    async def get_categories(self) -> list[dict]:
        try:
            res = await self._db().table("categories").select("*").execute()
            return res.data or []
        except Exception:
            logger.exception("Error getting categories")
            return []

    async def is_category_enabled(self, cat_key: str) -> bool:
        try:
            res = await self._db().table("categories").select("is_enabled").eq("category_key", cat_key).limit(1).execute()
            if res.data:
                return bool(res.data[0].get("is_enabled", False))
            return False
        except Exception:
            return False

    async def claim_task(self, user_id: int, fallback_task: dict) -> Optional[dict]:
        try:
            # Check existing assigned task
            existing = await self.get_user_assigned_task(user_id)
            if existing:
                return existing

            # Try to get from database tasks table if available, else use fallback
            res = await self._db().table("tasks").select("*").eq("status", "available").limit(1).execute()
            if res.data:
                task = res.data[0]
                await self._db().table("tasks").update({"status": "assigned", "assigned_to": user_id}).eq("id", task["id"]).execute()
                return task
            
            # Use fallback dictionary if no stock table row exists
            return fallback_task
        except Exception:
            logger.exception("Error claiming task")
            return fallback_task

    async def get_user_assigned_task(self, user_id: int) -> Optional[dict]:
        try:
            res = await self._db().table("tasks").select("*").eq("assigned_to", user_id).eq("status", "assigned").limit(1).execute()
            return res.data[0] if res.data else {"email": "test@gmail.com", "password": "pass", "recovery": "rec@gmail.com", "id": 1}
        except Exception:
            return None

    async def release_user_task(self, user_id: int) -> None:
        try:
            await self._db().table("tasks").update({"status": "available", "assigned_to": None}).eq("assigned_to", user_id).execute()
        except Exception:
            pass

    async def complete_task(self, task_id: int, user_id: int) -> Optional[dict]:
        try:
            reward = 10.0  # Default Gmail reward
            commission = reward * 0.10
            referrer_id = None

            user = await self.get_user(user_id)
            if user and user.get("referred_by"):
                referrer_id = user["referred_by"]
                await self.apply_balance_delta_safe(referrer_id, commission, reason="referral_commission")
                await self._apply_deltas(referrer_id, {"referral_income": commission})

            await self._apply_deltas(user_id, {"completed_tasks": 1})
            
            try:
                await self._db().table("tasks").update({"status": "completed"}).eq("id", task_id).execute()
            except Exception:
                pass

            return {
                "reward": reward,
                "referrer_id": referrer_id,
                "commission": commission
            }
        except Exception:
            logger.exception("Error completing task")
            return None

    # ================================================================
    # STOCK & SUBMISSIONS (Facebook, Instagram)
    # ================================================================

    async def get_unused_stock(self, category: str) -> Optional[dict]:
        try:
            res = await self._db().table("stock_accounts").select("*").eq("category", category).eq("is_used", False).limit(1).execute()
            return res.data[0] if res.data else None
        except Exception:
            return None

    async def mark_stock_as_used(self, stock_id: int, user_id: int) -> None:
        try:
            await self._db().table("stock_accounts").update({"is_used": True, "used_by": user_id}).eq("id", stock_id).execute()
        except Exception:
            pass

    async def add_stock_account(self, category: str, account_data: str) -> None:
        try:
            await self._db().table("stock_accounts").insert({
                "category": category,
                "account_data": account_data,
                "is_used": False
            }).execute()
        except Exception:
            logger.exception("Error adding stock account")

    async def add_submission(self, user_id: int, category: str, data: str, status: str = "pending") -> str:
        try:
            res = await self._db().table("user_submissions").insert({
                "user_id": user_id,
                "category": category,
                "details": data,
                "status": status
            }).execute()
            return str(res.data[0]["id"]) if res.data else "0"
        except Exception:
            logger.exception("Error adding submission")
            return "0"

    async def update_submission_status(self, sub_id: str, status: str) -> None:
        try:
            await self._db().table("user_submissions").update({"status": status}).eq("id", sub_id).execute()
        except Exception:
            logger.exception("Error updating submission status")

    async def get_accepted_submissions(self) -> list[dict]:
        try:
            res = await self._db().table("user_submissions").select("*").eq("status", "accepted").execute()
            return res.data or []
        except Exception:
            return []

    # ================================================================
    # GIFT CODES
    # ================================================================

    async def create_gift_code(
        self,
        code: str,
        reward: float,
        quantity: int = 1,
        expires_days: int = 30,
    ) -> bool:
        try:
            expire_date = datetime.now(BD_TZ) + timedelta(days=expires_days)
            
            for _ in range(quantity):
                await self._db().table("gift_codes").insert({
                    "code": code,
                    "reward": reward,
                    "redeemed_by": None,
                    "redeemed_at": None,
                    "expires_at": expire_date.isoformat(),
                    "is_active": True,
                }).execute()
            return True
        except Exception:
            logger.exception(f"Error creating gift code {code}")
            return False

    async def redeem_gift_code(self, user_id: int, code: str) -> tuple[bool, str, float]:
        try:
            res = await self._db().table("gift_codes").select(
                "*"
            ).eq("code", code).eq(
                "is_active", True
            ).is_("redeemed_by", "null").limit(1).execute()

            if not res.data:
                return False, "❌ এই কোড বৈধ নয় বা ইতিমধ্যে ব্যবহৃত হয়েছে।", 0.0

            gift_code = res.data[0]
            expires_at = datetime.fromisoformat(gift_code["expires_at"])
            
            if datetime.now(BD_TZ) > expires_at:
                await self._db().table("gift_codes").update(
                    {"is_active": False}
                ).eq("id", gift_code["id"]).execute()
                return False, "❌ এই কোডের মেয়াদ শেষ হয়ে গেছে।", 0.0

            reward = float(gift_code["reward"])
            await self._db().table("gift_codes").update({
                "redeemed_by": user_id,
                "redeemed_at": datetime.now(BD_TZ).isoformat(),
            }).eq("id", gift_code["id"]).execute()

            success, _ = await self.apply_balance_delta_safe(
                user_id,
                reward,
                reason=f"gift_code_redemption:{code}"
            )

            if success:
                return True, f"✅ গিফট কোড রিডিম হয়েছে! আপনার অ্যাকাউন্টে {reward:.2f} যোগ হয়েছে।", reward
            else:
                await self._db().table("gift_codes").update({
                    "redeemed_by": None,
                    "redeemed_at": None,
                }).eq("id", gift_code["id"]).execute()
                return False, "❌ পুরস্কার যুক্ত করতে ব্যর্থ হয়েছে। পুনরায় চেষ্টা করুন।", 0.0

        except Exception:
            logger.exception(f"Error redeeming gift code {code}")
            return False, "⚠️ একটি ত্রুটি ঘটেছে। পরে চেষ্টা করুন।", 0.0

    async def get_active_gift_codes_count(self) -> int:
        try:
            res = await self._db().table("gift_codes").select(
                "id", count="exact"
            ).eq("is_active", True).is_(
                "redeemed_by", "null"
            ).execute()
            return int(res.count or 0)
        except Exception:
            logger.exception("Error counting active gift codes")
            return 0

    # ================================================================
    # LEADER ELECTION (Polling Lease)
    # ================================================================

    async def acquire_leader(self) -> bool:
        try:
            res = await self._db().table("bot_locks").select("*").eq("id", LOCK_ROW_ID).limit(1).execute()
            now = datetime.now(BD_TZ)
            if not res.data:
                await self._db().table("bot_locks").insert({"id": LOCK_ROW_ID, "instance_id": INSTANCE_ID, "updated_at": now.isoformat()}).execute()
                return True
            row = res.data[0]
            inst = row.get("instance_id")
            updated_at = row.get("updated_at")
            if inst == INSTANCE_ID:
                await self.renew_leader()
                return True
            if updated_at:
                dt = datetime.fromisoformat(updated_at)
                if (now - dt).total_seconds() > LOCK_TTL:
                    up = await self._db().table("bot_locks").update({"instance_id": INSTANCE_ID, "updated_at": now.isoformat()}).eq("id", LOCK_ROW_ID).eq("instance_id", inst).execute()
                    return bool(up.data)
            return False
        except Exception:
            return True

    async def renew_leader(self) -> str:
        try:
            now = datetime.now(BD_TZ)
            up = await self._db().table("bot_locks").update({"updated_at": now.isoformat()}).eq("id", LOCK_ROW_ID).eq("instance_id", INSTANCE_ID).execute()
            return "ok" if up.data else "lost"
        except Exception:
            return "ok"

    async def release_leader(self) -> None:
        try:
            await self._db().table("bot_locks").update({"instance_id": None}).eq("id", LOCK_ROW_ID).eq("instance_id", INSTANCE_ID).execute()
        except Exception:
            pass

    # ================================================================
    # CSV & OTHER ADMIN HELPERS
    # ================================================================

    async def bulk_update_balances(
        self,
        updates: list[tuple[int, float, str]],
    ) -> dict:
        stats = {"success_count": 0, "failed_count": 0, "errors": []}
        for user_id, delta, reason in updates:
            try:
                success, _ = await self.apply_balance_delta_safe(user_id, float(delta), reason=reason)
                if success:
                    stats["success_count"] += 1
                else:
                    stats["failed_count"] += 1
            except Exception as e:
                stats["failed_count"] += 1
                stats["errors"].append(str(e))
        return stats

    async def bulk_distribute_referral_commissions(
        self,
        commissions: dict[int, float],
    ) -> dict:
        updates = [(uid, comm, "referral_commission") for uid, comm in commissions.items()]
        return await self.bulk_update_balances(updates)

    async def get_pending_submissions_for_csv(self, limit: int = 1000) -> list[dict]:
        try:
            res = await self._db().table("user_submissions").select("*").eq("status", "pending").limit(limit).execute()
            return res.data or []
        except Exception:
            return []

    async def claim_daily_bonus(self, user_id: int) -> tuple[bool, str, float]:
        try:
            user = await self.get_user(user_id)
            if not user:
                return False, "⚠️ ইউজার পাওয়া যায়নি।", 0.0

            today = today_bd()
            bonus = await self.get_float_setting("daily_bonus", 1.0)
            if bonus <= 0:
                return False, "⚠️ ডেইলি বোনাস বর্তমানে বন্ধ আছে।", 0.0

            old_checkin = user.get("last_checkin")
            marked = await self._db().table("users").update(
                {"last_checkin": today}
            ).eq("user_id", user_id).or_(
                f"last_checkin.is.null,last_checkin.neq.{today}"
            ).select("*").execute()

            if not marked.data:
                return False, "⚠️ আজকের বোনাস ইতিমধ্যে দাবি করা হয়েছে।", 0.0

            status, _ = await self._apply_deltas(user_id, {"balance": bonus})
            if status != "ok":
                await self._db().table("users").update({"last_checkin": old_checkin}).eq("user_id", user_id).execute()
                return False, "⚠️ বোনাস যোগ করতে ব্যর্থ।", 0.0

            return True, f"✅ আপনি {_fmt(bonus)} পেয়েছেন!", bonus
        except Exception:
            return False, "⚠️ একটি ত্রুটি ঘটেছে।", 0.0

    async def get_stock_count(self) -> int:
        try:
            res = await self._db().table("tasks").select("id", count="exact").eq("status", "available").execute()
            return int(res.count or 0)
        except Exception:
            return 0


db = Database()

def _fmt(x) -> str:
    return f"{float(x):.2f}"
