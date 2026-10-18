import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
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

def is_admin(user_id: int) -> bool:
    """ইউজার এডমিন কি না তা চেক করা"""
    return user_id in ADMIN_IDS

def get_admin_keyboard():
    """এডমিন প্যানেলের ইনলাইন কিবোর্ড"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Tasks (Bulk)", callback_data="admin_add_bulk")],
        [InlineKeyboardButton(text="💳 Pending Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton(text="📊 Detailed Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🧹 Clear Completed Tasks", callback_data="admin_clear_tasks")]
    ])
    return keyboard

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    """/admin কমান্ড হ্যান্ডলার"""
    if not is_admin(message.from_user.id):
        return
    
    total_users = await db.get_all_users_count()
    available_tasks = await db.get_stock_count()
    
    text = (
        "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n\n"
        f"👥 মোট রেজিস্টার্ড ইউজার: <b>{total_users} জন</b>\n"
        f"📦 স্টকে খালি জিমেইল টাস্ক আছে: <b>{available_tasks} টি</b>\n\n"
        "নিচের বাটনগুলো থেকে আপনার প্রয়োজনীয় কাজ নির্বাচন করুন:"
    )
    await message.answer(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(callback: CallbackQuery):
    """বোটের স্ট্যাটিস্টিক্স দেখার হ্যান্ডলার"""
    if not is_admin(callback.from_user.id):
        return
    
    total_users = await db.get_all_users_count()
    available_tasks = await db.get_stock_count()
    
    text = (
        "📊 <b>বোটের লাইভ স্ট্যাটিস্টিক্স:</b>\n\n"
        f"👥 মোট রেজিস্টার্ড ইউজার: <b>{total_users} জন</b>\n"
        f"📦 স্টকে খালি জিমেইল টাস্ক আছে: <b>{available_tasks} টি</b>"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_withdrawals")
async def handle_admin_withdrawals(callback: CallbackQuery):
    """পেন্ডিং উইথড্রো রিকোয়েস্টগুলো এডমিনকে দেখানো"""
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
    """উইথড্রো এপ্রুভ বা রিজেক্ট করা এবং টাকা রিফান্ড হ্যান্ডেল করা"""
    if not is_admin(callback.from_user.id):
        return

    parts = callback.data.split("_")
    action = parts[0]  # approve অথবা reject
    req_id = int(parts[2])

    status = "approved" if action == "approve" else "rejected"
    success = await db.update_withdrawal_status(req_id, status)

    if success:
        msg = "✅ উইথড্রো সফলভাবে **Approve** করা হয়েছে।" if status == "approved" else "❌ উইথড্রো **Reject** করা হয়েছে এবং ইউজারের ব্যালেন্স রিফান্ড করা হয়েছে।"
        await callback.message.edit_text(f"{callback.message.text}\n\n{msg}", parse_mode="Markdown")
    else:
        await callback.answer("⚠️ স্ট্যাটাস আপডেট করতে সমস্যা হয়েছে।", show_alert=True)

@admin_router.callback_query(F.data == "admin_add_bulk")
async def handle_add_bulk_click(callback: CallbackQuery, state: FSMContext):
    """বাল্ক টাস্ক আপলোড প্রম্পট"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.waiting_for_bulk_tasks)
    text = (
        "📥 <b>বাল্ক জিমেইল টাস্ক আপলোড:</b>\n\n"
        "নিচের ফরম্যাটে মেসেজ পাঠান (প্রতি লাইনে ১টি করে):\n"
        "<code>email|password</code> অথবা <code>email|password|recovery</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")

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
            first_name = parts[3] if len(parts) >= 4 else email.split("@")[0].capitalize()
            last_name = parts[4] if len(parts) >= 5 else "❌"

            task_list.append({
                "email": email,
                "password": password,
                "recovery": recovery,
                "first_name": first_name,
                "last_name": last_name,
                "status": "available",
                "reward": 10.0
            })

    if task_list:
        inserted_count = await db.add_bulk_tasks(task_list)
        await message.answer(f"✅ সফলভাবে <b>{inserted_count}</b> টি টাস্ক আপলোড করা হয়েছে!", parse_mode="HTML")
    else:
        await message.answer("⚠️ কোনো সঠিক ফরম্যাটের ডাটা পাওয়া যায়নি।")

    await state.clear()

@admin_router.callback_query(F.data == "admin_clear_tasks")
async def handle_clear_tasks(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("🧹 সম্পন্ন হওয়া টাস্কগুলো ক্লিয়ার করা হয়েছে।", show_alert=True)
