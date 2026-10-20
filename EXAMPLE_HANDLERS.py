"""
Production-Ready Handler Examples
Demonstrates safe task submission, validation, and balance updates
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database_enhanced import db
from validators import validate_task_submission, TaskValidator
from keyboards_enhanced import get_main_keyboard

router = Router(name="example_handlers")


class TaskSubmissionStates(StatesGroup):
    """FSM states for task submissions."""
    waiting_for_gmail = State()
    waiting_for_fb_uid = State()
    waiting_for_fb_cookies = State()
    waiting_for_insta_username = State()
    waiting_for_insta_2fa = State()


# ================================================================
# EXAMPLE 1: GMAIL TASK WITH VALIDATION & ATOMIC UPDATE
# ================================================================

async def handle_gmail_task_submission(message: Message, state: FSMContext):
    """
    Complete example of safe Gmail task submission:
    1. Validate input strictly
    2. Acquire state lock to prevent race conditions
    3. Apply atomic balance update
    4. Clear state
    """
    user_id = message.from_user.id
    email_input = message.text.strip()
    
    # STEP 1: Validate input (strict format checking)
    is_valid, error_msg, cleaned_data = await validate_task_submission(
        task_category="gmail",
        submission_data={"email": email_input},
    )
    
    if not is_valid:
        # Show validation error to user
        await message.answer(error_msg)
        return  # Stay in current state for retry
    
    # Extract cleaned email
    email = cleaned_data["email"]
    
    # STEP 2: Acquire state lock (prevent concurrent submissions)
    lock = db.get_user_state_lock(user_id)
    
    async with lock:  # Only one submission per user at a time
        # STEP 3: Check if user is banned
        is_banned = await db.is_banned(user_id)
        if is_banned:
            await message.answer("🚫 আপনার অ্যাকাউন্ট নিষিদ্ধ।")
            await state.clear()
            return
        
        # STEP 4: Store submission in database
        try:
            result = await db._db().table("user_submissions").insert({
                "user_id": user_id,
                "task_category": "gmail",
                "submission_data": {"email": email},
                "status": "pending",
            }).execute()
            
            submission_id = result.data[0]["id"] if result.data else None
            
        except Exception as e:
            await message.answer("❌ সাবমিশন সংরক্ষণ ব্যর্থ। পুনরায় চেষ্টা করুন।")
            return
        
        # STEP 5: Apply atomic balance update (SAFE)
        # Use apply_balance_delta_safe() for production safety
        reward = 10.00  # From CATEGORY_REWARDS config
        
        success, new_balance = await db.apply_balance_delta_safe(
            user_id=user_id,
            amount=reward,
            reason=f"gmail_task_completion_submission_id_{submission_id}"
        )
        
        if success:
            # STEP 6: Update task counters
            await db._apply_deltas(
                user_id,
                {"completed_tasks": 1}
            )
            
            # STEP 7: Clear state and show success
            await state.clear()
            await message.answer(
                f"✅ সাবমিশন সফল!\n\n"
                f"💰 আপনি {reward:.2f} টাকা অর্জন করেছেন।\n"
                f"নতুন ব্যালেন্স: ৳ {new_balance:.2f}",
                reply_markup=get_main_keyboard()
            )
        else:
            # Rollback: mark submission as failed
            try:
                await db._db().table("user_submissions").update(
                    {"status": "failed"}
                ).eq("id", submission_id).execute()
            except:
                pass
            
            await message.answer(
                "❌ পুরস্কার যোগ করতে ব্যর্থ। সাপোর্টে যোগাযোগ করুন।"
            )
            await state.clear()


# ================================================================
# EXAMPLE 2: FACEBOOK TASK WITH VALIDATION
# ================================================================

async def handle_facebook_uid_submission(message: Message, state: FSMContext):
    """
    Facebook UID submission with validation.
    """
    user_id = message.from_user.id
    uid_input = message.text.strip()
    
    # Validate UID format
    is_valid, error_msg, cleaned_data = await validate_task_submission(
        task_category="facebook",
        submission_data={"uid": uid_input, "cookies": ""},  # Cookies in next step
    )
    
    if not is_valid:
        await message.answer(error_msg)
        return
    
    # Store validated UID in context
    await state.update_data(fb_uid=cleaned_data["uid"])
    
    # Move to next step
    await state.set_state(TaskSubmissionStates.waiting_for_fb_cookies)
    await message.answer(
        "✅ UID গৃহীত।\n\n"
        "এখন Facebook কুকিজ প্রদান করুন:"
    )


async def handle_facebook_cookies_submission(message: Message, state: FSMContext):
    """
    Facebook cookies submission with validation.
    """
    user_id = message.from_user.id
    cookies_input = message.text.strip()
    
    # Get stored UID
    data = await state.get_data()
    fb_uid = data.get("fb_uid", "")
    
    # Validate cookies
    is_valid, error_msg, cleaned_data = await validate_task_submission(
        task_category="facebook",
        submission_data={
            "uid": fb_uid,
            "cookies": cookies_input,
        },
    )
    
    if not is_valid:
        await message.answer(error_msg)
        return
    
    # Both validated, proceed with submission
    lock = db.get_user_state_lock(user_id)
    
    async with lock:
        is_banned = await db.is_banned(user_id)
        if is_banned:
            await message.answer("🚫 আপনার অ্যাকাউন্ট নিষিদ্ধ।")
            await state.clear()
            return
        
        # Store submission
        submission_data = {
            "uid": cleaned_data["uid"],
            "cookies": cleaned_data["cookies"],
        }
        
        try:
            result = await db._db().table("user_submissions").insert({
                "user_id": user_id,
                "task_category": "facebook",
                "submission_data": submission_data,
                "status": "pending",
            }).execute()
            
            submission_id = result.data[0]["id"] if result.data else None
            
        except Exception as e:
            await message.answer("❌ সাবমিশন সংরক্ষণ ব্যর্থ।")
            await state.clear()
            return
        
        # Apply reward
        reward = 4.00  # From config
        success, new_balance = await db.apply_balance_delta_safe(
            user_id=user_id,
            amount=reward,
            reason=f"facebook_task_completion_{submission_id}"
        )
        
        if success:
            await db._apply_deltas(user_id, {"completed_tasks": 1})
            await state.clear()
            await message.answer(
                f"✅ সাবমিশন সফল!\n💰 ৳ {reward:.2f} অর্জিত।",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("❌ পুরস্কার যোগ করতে ব্যর্থ।")
            await state.clear()


# ================================================================
# EXAMPLE 3: INSTAGRAM TASK WITH MULTI-STEP VALIDATION
# ================================================================

async def handle_instagram_username_submission(message: Message, state: FSMContext):
    """First step: validate Instagram username."""
    username_input = message.text.strip()
    
    # Validate username format
    is_valid, error_msg, cleaned_data = await validate_task_submission(
        task_category="instagram",
        submission_data={
            "username": username_input,
            "2fa_code": "000000",  # Placeholder
        },
    )
    
    if not is_valid:
        await message.answer(error_msg)
        return
    
    # Store in context
    await state.update_data(insta_username=cleaned_data["username"])
    await state.set_state(TaskSubmissionStates.waiting_for_insta_2fa)
    
    await message.answer("✅ ইউজারনেম গৃহীত।\n\n2FA কোড প্রদান করুন (6 ডিজিট):")


async def handle_instagram_2fa_submission(message: Message, state: FSMContext):
    """Second step: validate 2FA code and complete submission."""
    user_id = message.from_user.id
    code_input = message.text.strip()
    
    # Get stored username
    data = await state.get_data()
    username = data.get("insta_username", "")
    
    # Validate 2FA code
    is_valid, error_msg, cleaned_data = await validate_task_submission(
        task_category="instagram",
        submission_data={
            "username": username,
            "2fa_code": code_input,
        },
    )
    
    if not is_valid:
        await message.answer(error_msg)
        return
    
    # Both validated, acquire lock and submit
    lock = db.get_user_state_lock(user_id)
    
    async with lock:
        is_banned = await db.is_banned(user_id)
        if is_banned:
            await message.answer("🚫 অ্যাকাউন্ট নিষিদ্ধ।")
            await state.clear()
            return
        
        submission_data = {
            "username": cleaned_data["username"],
            "2fa_code": cleaned_data["2fa_code"],
        }
        
        try:
            result = await db._db().table("user_submissions").insert({
                "user_id": user_id,
                "task_category": "instagram",
                "submission_data": submission_data,
                "status": "pending",
            }).execute()
            
            submission_id = result.data[0]["id"] if result.data else None
            
        except Exception as e:
            await message.answer("❌ সাবমিশন ব্যর্থ।")
            await state.clear()
            return
        
        # Award
        reward = 5.00
        success, new_balance = await db.apply_balance_delta_safe(
            user_id=user_id,
            amount=reward,
            reason=f"instagram_task_{submission_id}"
        )
        
        if success:
            await db._apply_deltas(user_id, {"completed_tasks": 1})
            await state.clear()
            await message.answer(
                f"✅ সম্পন্ন!\n💰 ৳ {reward:.2f} অর্জিত।",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer("❌ পুরস্কার ব্যর্থ।")
            await state.clear()


# ================================================================
# EXAMPLE 4: BULK BALANCE UPDATES (ADMIN)
# ================================================================

async def admin_bulk_distribute_earnings(admin_message: Message):
    """
    Example: Admin distributes earnings to multiple users safely.
    Uses atomic delta updates to prevent race conditions.
    """
    updates = [
        (user_id_1, 100.00, "manual_reward_batch_1"),
        (user_id_2, 50.00, "manual_reward_batch_1"),
        (user_id_3, 75.50, "manual_reward_batch_1"),
    ]
    
    stats = await db.bulk_update_balances(updates)
    
    result_text = (
        f"✅ বাল্ক আপডেট সম্পন্ন:\n\n"
        f"সফল: {stats['success_count']}\n"
        f"ব্যর্থ: {stats['failed_count']}\n"
    )
    
    if stats['errors']:
        result_text += "\nত্রুটি:\n"
        for err in stats['errors'][:5]:
            result_text += f"  • {err}\n"
    
    await admin_message.answer(result_text)


# ================================================================
# EXAMPLE 5: GIFT CODE REDEMPTION
# ================================================================

async def handle_gift_code_redemption(message: Message, state: FSMContext):
    """
    User redeems a gift code.
    Uses atomic delta updates for safe balance modification.
    """
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    # Validate format
    if not code or len(code) < 3 or len(code) > 50:
        await message.answer("❌ অবৈধ কোড ফর্ম্যাট।")
        return
    
    # Redeem (includes atomic balance update)
    success, message_text, reward = await db.redeem_gift_code(user_id, code)
    
    await message.answer(message_text)
    
    if success:
        await state.clear()
        await message.answer("মূল মেনুতে ফিরছি...", reply_markup=get_main_keyboard())


# ================================================================
# KEY PRODUCTION SAFETY PRINCIPLES
# ================================================================

"""
1. INPUT VALIDATION
   - Always validate user input with validators.py
   - Sanitize before storing
   - Set length limits
   
2. STATE LOCKING
   - Use db.get_user_state_lock(user_id) to prevent concurrent submissions
   - Wrap critical sections in: async with lock:
   
3. ATOMIC UPDATES
   - Use apply_balance_delta_safe() for balance changes
   - Never: manually read balance, modify, write back
   - Atomic operations handle race conditions automatically
   
4. BAN CHECKS
   - Check is_banned() before processing
   - Use caching (20-second TTL) for performance
   
5. ERROR HANDLING
   - Wrap DB operations in try/except
   - Log all errors for debugging
   - Rollback on failure (update submission status)
   - Always clear FSM state after completion
   
6. LOGGING
   - Log all balance changes with reason
   - Log validation failures
   - Log submission IDs for tracking
   
7. IDEMPOTENCY
   - If user resubmits same task, detect duplicates
   - Don't award twice
   - Mark with unique submission_id
"""
