import logging
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database import db
from tasks import task_manager

logger = logging.getLogger(__name__)
admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_bulk_tasks = State()
    waiting_for_min_withdraw = State()
    waiting_for_ref_commission = State()
    waiting_for_daily_bonus = State()
    waiting_for_proof_channel = State()
    waiting_for_broadcast_msg = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Tasks (Bulk)", callback_data="admin_add_bulk")],
        [InlineKeyboardButton(text="📂 Manage Task Categories", callback_data="admin_categories")],
        [InlineKeyboardButton(text="👥 User List & Ban Control", callback_data="admin_users_page_1")],
        [InlineKeyboardButton(text="📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="⚙️ Bot Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="💳 Pending Withdrawals", callback_data="admin_withdrawals")]
    ])
    return keyboard

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    total_users = await db.get_all_users_count()
    available_tasks = await db.get_stock_count()
    
    text = (
        "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n\n"
        f"👥 মোট রেজিস্টার্ড ইউজার: <b>{total_users} জন</b>\n"
        f"📦 স্টকে টাস্ক আছে: <b>{available_tasks} টি</b>\n\n"
        "নিচের অপশনগুলো থেকে আপনার পছন্দ নির্বাচন করুন:"
    )
    kb = await get_admin_keyboard()
    
    # নীরবে ইউজার কিবোর্ড রিমুভ করার জন্য ট্রিক (কোনো বাড়তি টেক্সট দেখাবে না)
    try:
        temp = await message.answer("...", reply_markup=ReplyKeyboardRemove())
        await temp.delete()
    except Exception:
        pass

    await message.answer(text, reply_markup=kb, parse_mode="HTML")

# --- CATEGORY MANAGEMENT ---
@admin_router.callback_query(F.data == "admin_categories")
async def handle_admin_categories(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    categories = await db.get_categories()
    keyboard_buttons = []
    
    for cat in categories:
        status_icon = "🟢 চালু" if cat["is_enabled"] else "🔴 বন্ধ"
        btn_text = f"{cat['category_name']} ({status_icon})"
        keyboard_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"toggle_cat_{cat['category_key']}")])

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    
    await callback.message.edit_text("📂 <b>টাস্ক ক্যাটাগরি ম্যানেজমেন্ট:</b>\nযে ক্যাটাগরি অন বা অফ করতে চান তাতে ক্লিক করুন:", reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(F.data.startswith("toggle_cat_"))
async def handle_toggle_category(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    cat_key = callback.data.replace("toggle_cat_", "")
    new_status = await db.toggle_category(cat_key)
    
    status_msg = "চালু" if new_status else "বন্ধ"
    await callback.answer(f"⚠️ ক্যাটাগরি সফলভাবে {status_msg} করা হয়েছে!", show_alert=True)
    
    categories = await db.get_categories()
    keyboard_buttons = []
    for cat in categories:
        status_icon = "🟢 চালু" if cat["is_enabled"] else "🔴 বন্ধ"
        btn_text = f"{cat['category_name']} ({status_icon})"
        keyboard_buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"toggle_cat_{cat['category_key']}")])

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")])
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await callback.message.edit_reply_markup(reply_markup=kb)

# --- PAGINATED USER LIST & BAN CONTROL ---
@admin_router.callback_query(F.data.startswith("admin_users_page_"))
async def handle_admin_user_list(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    page = int(callback.data.replace("admin_users_page_", ""))
    limit = 6
    users, total_count = await db.get_users_paginated(page, limit) if hasattr(db, 'get_users_paginated') else (await db.get_users_paginated(page, limit), await db.get_all_users_count())
    total_pages = (total_count + limit - 1) // limit if total_count > 0 else 1

    if not users:
        await callback.answer("⚠️ কোনো ইউজার পাওয়া যায়নি।", show_alert=True)
        return

    text = f"👥 <b>বোটের ইউজার ম্যানেজমেন্ট (পেজ {page}/{total_pages}):</b>\n\n"
    
    keyboard_buttons = []
    for u in users:
        uid = u["user_id"]
        uname = u.get("username", "User")
        bal = u.get("balance", 0.0)
        banned = u.get("is_banned", False)
        
        status_str = "🟢 Unban" if banned else "🔴 Ban"
        status_badge = "🚫 [Banned]" if banned else "✅ [Active]"
        
        text += f"• <b>{uname}</b> {status_badge}\n  ID: <code>{uid}</code> | Bal: <b>{bal} BDT</b>\n"
        
        keyboard_buttons.append([
            InlineKeyboardButton(text=f"👤 {uname}", callback_data="none"),
            InlineKeyboardButton(text=status_str, callback_data=f"toggle_ban_{uid}_{page}")
        ])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"admin_users_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="none"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"admin_users_page_{page+1}"))
    
    if nav_buttons:
        keyboard_buttons.append(nav_buttons)
        
    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")])

    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.answer()

@admin_router.callback_query(F.data.startswith("toggle_ban_"))
async def handle_toggle_ban_inline(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    
    parts = callback.data.split("_")
    uid = int(parts[2])
    page = int(parts[3])

    user = await db.get_or_create_user(uid, "")
    current_ban = user.get("is_banned", False)
    new_ban_status = not current_ban
    
    await db.set_user_ban_status(uid, new_ban_status)
    
    action_name = "ব্যান" if new_ban_status else "আনব্যান"
    await callback.answer(f"ইউজার {uid} কে সফলভাবে {action_name} করা হয়েছে!", show_alert=True)

    callback.data = f"admin_users_page_{page}"
    await handle_admin_user_list(callback)

# --- SETTINGS & BROADCAST ---
@admin_router.callback_query(F.data == "admin_settings")
async def handle_admin_settings(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    min_wd = await db.get_setting("min_withdraw", "50.0")
    ref_comm = await db.get_setting("referral_commission", "10.0")
    daily_bonus = await db.get_setting("daily_bonus", "1.0")
    proof_chan = await db.get_setting("proof_channel", "@YourProofChannel")

    text = (
        "⚙️ <b>বোট কনফিগারেশন সেটিংস:</b>\n\n"
        f"💵 সর্বনিম্ন উইথড্রো: <b>{min_wd} BDT</b>\n"
        f"🎁 রেফারেল কমিশন: <b>{ref_comm}%</b>\n"
        f"🎁 ডেইলি বোনাস: <b>{daily_bonus} BDT</b>\n"
        f"📢 পেমেন্ট প্রুফ চ্যানেল: <code>{proof_chan}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit Min Withdraw", callback_data="edit_min_withdraw")],
        [InlineKeyboardButton(text="✏️ Edit Ref Commission", callback_data="edit_ref_comm")],
        [InlineKeyboardButton(text="✏️ Edit Daily Bonus", callback_data="edit_daily_bonus")],
        [InlineKeyboardButton(text="✏️ Edit Proof Channel", callback_data="edit_proof_channel")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(F.data == "edit_min_withdraw")
async def handle_edit_min_withdraw(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_min_withdraw)
    await callback.message.edit_text("✏️ নতুন **সর্বনিম্ন উইথড্রো পরিমাণ (BDT)** লিখে পাঠান:")

@admin_router.message(AdminStates.waiting_for_min_withdraw)
async def process_new_min_withdraw(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        val = float(message.text.strip())
        await db.update_setting("min_withdraw", str(val))
        await message.answer(f"✅ সর্বনিম্ন উইথড্রো সফলভাবে <b>{val} BDT</b> সেট করা হয়েছে!", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ শুধুমাত্র সংখ্যা লিখুন।")
    await state.clear()

@admin_router.callback_query(F.data == "edit_daily_bonus")
async def handle_edit_daily_bonus(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_daily_bonus)
    await callback.message.edit_text("✏️ নতুন **ডেইলি বোনাস পরিমাণ (BDT)** লিখে পাঠান:")

@admin_router.message(AdminStates.waiting_for_daily_bonus)
async def process_new_daily_bonus(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        val = float(message.text.strip())
        await db.update_setting("daily_bonus", str(val))
        await message.answer(f"✅ ডেইলি বোনাস সফলভাবে <b>{val} BDT</b> সেট করা হয়েছে!", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ শুধুমাত্র সংখ্যা লিখুন।")
    await state.clear()

@admin_router.callback_query(F.data == "edit_proof_channel")
async def handle_edit_proof_channel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_proof_channel)
    await callback.message.edit_text("✏️ পেমেন্ট প্রুফ চ্যানেলের ইউজারনেম লিখে পাঠান (যেমন: <code>@Technova_Proof</code>):", parse_mode="HTML")

@admin_router.message(AdminStates.waiting_for_proof_channel)
async def process_new_proof_channel(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    ch_name = message.text.strip()
    if not ch_name.startswith("@"):
        ch_name = "@" + ch_name
    await db.update_setting("proof_channel", ch_name)
    await message.answer(f"✅ পেমেন্ট প্রুফ চ্যানেল সফলভাবে <b>{ch_name}</b> সেট করা হয়েছে!", parse_mode="HTML")
    await state.clear()

@admin_router.callback_query(F.data == "admin_broadcast")
async def handle_broadcast_click(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_broadcast_msg)
    await callback.message.edit_text("📢 সমস্ত ইউজারের কাছে পাঠানোর জন্য আপনার ব্রডকাস্ট মেসেজটি লিখুন:")

@admin_router.message(AdminStates.waiting_for_broadcast_msg)
async def process_broadcast_send(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    
    user_ids = await db.get_all_user_ids()
    sent_count = 0
    await message.answer(f"⏳ মোট <b>{len(user_ids)}</b> জন ইউজারের কাছে মেসেজ পাঠানো শুরু হয়েছে...", parse_mode="HTML")
    
    for uid in user_ids:
        try:
            await message.copy_to(chat_id=uid)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass

    await message.answer(f"✅ সফলভাবে <b>{sent_count}</b> জন ইউজারের কাছে ব্রডকাস্ট মেসেজ পাঠানো হয়েছে!", parse_mode="HTML")
    await state.clear()

@admin_router.callback_query(F.data == "admin_back")
async def handle_admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    kb = await get_admin_keyboard()
    from main import get_main_keyboard
    await callback.message.edit_text("👑 <b>এডমিন কন্ট্রোল প্যানেল</b>", reply_markup=kb, parse_mode="HTML")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())

@admin_router.callback_query(F.data == "admin_withdrawals")
async def handle_admin_withdrawals(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    withdrawals = await db.get_pending_withdrawals()
    if not withdrawals:
        await callback.answer("⚠️ বর্তমানে কোনো পেন্ডিং উইথড্রো রিকোয়েস্ট নেই।", show_alert=True)
        return

    await callback.message.edit_text("💳 <b>পেন্ডিং উইথড্রো রিকোয়েস্টসমূহ:</b>", parse_mode="HTML")
    for req in withdrawals:
        req_id = req["id"]
        user_id = req["user_id"]
        amount = req["amount"]
        method = req["method"]
        account_no = req["account_no"]

        text = (
            f"👤 ইউজার আইডি: <code>{user_id}</code>\n"
            f"💰 পরিমাণ: <b>{amount} BDT</b>\n"
            f"💳 মেথড: <b>{method}</b>\n"
            f"📱 নম্বর: <code>{account_no}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"approve_wd_{req_id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"reject_wd_{req_id}")
            ]
        ])
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data.startswith("approve_wd_") | F.data.startswith("reject_wd_"))
async def handle_withdrawal_action(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split("_")
    action = parts[0]
    req_id = int(parts[2])

    status = "approved" if action == "approve" else "rejected"
    success, req_data = await db.update_withdrawal_status(req_id, status)

    if success and req_data:
        user_id = req_data['user_id']
        amount = req_data['amount']
        method = req_data['method']

        if status == "approved":
            msg = "✅ উইথড্রো এপ্রুভ হয়েছে।"
            try:
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "🎉 <b>আপনার উইথড্রো সফল হয়েছে!</b>\n\n"
                        f"💰 পরিমাণ: <b>{amount} BDT</b>\n"
                        f"💳 মাধ্যম: <b>{method}</b>\n\n"
                        "✅ আপনার পেমেন্ট সফলভাবে পাঠিয়ে দেওয়া হয়েছে। পেমেন্ট প্রুফ চ্যানেল চেক করুন!"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending approval DM: {e}")

            try:
                proof_chan = await db.get_setting("proof_channel", "")
                if proof_chan and proof_chan.startswith("@"):
                    proof_text = (
                        "🎉 <b>New Successful Withdrawal!</b>\n\n"
                        f"👤 User ID: <code>{user_id}</code>\n"
                        f"💰 Amount: <b>{amount} BDT</b>\n"
                        f"💳 Method: <b>{method}</b>\n"
                        "✅ Status: <b>Paid / Approved</b>\n\n"
                        "🤖 Join Bot & Start Earning Now!"
                    )
                    await callback.bot.send_message(chat_id=proof_chan, text=proof_text, parse_mode="HTML")
            except Exception as e:
                logger.error(f"Error posting proof: {e}")
        else:
            msg = "❌ উইথড্রো রিজেক্ট এবং টাকা রিফান্ড করা হয়েছে।"
            
            try:
                user = await db.get_or_create_user(user_id, "")
                current_bal = float(user.get("balance", 0.0))
                new_bal = current_bal + float(amount)
                await db.supabase.table("users").update({"balance": new_bal}).eq("user_id", user_id).execute()
            except Exception as e:
                logger.error(f"Error refunding balance: {e}")

            try:
                await callback.bot.send_message(
                    chat_id=user_id,
                    text=(
                        "❌ <b>আপনার উইথড্রো রিকোয়েস্ট রিজেক্ট করা হয়েছে!</b>\n\n"
                        f"💰 পরিমাণ: <b>{amount} BDT</b> আপনার একাউন্টে ফিরিয়ে দেওয়া হয়েছে।\n\n"
                        "⚠️ ভুল নম্বর বা অন্য কোনো সমস্যার কারণে এটি হতে পারে। দয়া করে সঠিক তথ্য দিয়ে আবার উইথড্রো করুন।"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending rejection DM: {e}")

        await callback.message.edit_text(f"{callback.message.text}\n\n{msg}", parse_mode="HTML")
    else:
        await callback.answer("⚠️ সমস্যা হয়েছে।", show_alert=True)

@admin_router.callback_query(F.data == "admin_add_bulk")
async def handle_add_bulk_click(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_bulk_tasks)
    await callback.message.edit_text("📥 <code>email|password</code> ফরম্যাটে বাল্ক টাস্ক মেসেজ দিন:", parse_mode="HTML")

@admin_router.message(AdminStates.waiting_for_bulk_tasks)
async def process_bulk_tasks_input(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    lines = message.text.strip().split("\n")
    task_list = []

    for line in lines:
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2:
            email = parts[0]
            password = parts[1]
            recovery = parts[2] if len(parts) >= 3 else task_manager.generate_random_gmail()["recovery"]
            task_list.append({
                "email": email,
                "password": password,
                "recovery": recovery,
                "status": "available",
                "reward": 10.0
            })

    if task_list:
        inserted = await db.add_bulk_tasks(task_list)
        await message.answer(f"✅ <b>{inserted}</b> টি টাস্ক আপলোড করা হয়েছে!", parse_mode="HTML")
    else:
        await message.answer("⚠️ সঠিক ফরম্যাটে দিন।")
    await state.clear()
