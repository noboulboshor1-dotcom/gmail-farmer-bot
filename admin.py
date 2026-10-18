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
    waiting_for_min_withdraw = State()
    waiting_for_ref_commission = State()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def get_admin_keyboard():
    """ডায়নামিক টগল বাটন সহ এডমিন প্যানেল কিবোর্ড"""
    tasks_enabled = (await db.get_setting("tasks_enabled", "true")) == "true"
    toggle_text = "🟢 Disable Tasks" if tasks_enabled else "🔴 Enable Tasks"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Tasks (Bulk)", callback_data="admin_add_bulk")],
        [InlineKeyboardButton(text=toggle_text, callback_data="admin_toggle_tasks")],
        [InlineKeyboardButton(text="⚙️ Bot Settings", callback_data="admin_settings")],
        [InlineKeyboardButton(text="💳 Pending Withdrawals", callback_data="admin_withdrawals")],
        [InlineKeyboardButton(text="📊 Detailed Statistics", callback_data="admin_stats")]
    ])
    return keyboard

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    total_users = await db.get_all_users_count()
    available_tasks = await db.get_stock_count()
    tasks_status = "চালু আছে 🟢" if (await db.get_setting("tasks_enabled", "true")) == "true" else "বন্ধ আছে 🔴"
    min_wd = await db.get_setting("min_withdraw", "50.0")
    
    text = (
        "👑 <b>এডমিন কন্ট্রোল প্যানেল</b>\n\n"
        f"👥 মোট রেজিস্টার্ড ইউজার: <b>{total_users} জন</b>\n"
        f"📦 স্টকে টাস্ক আছে: <b>{available_tasks} টি</b>\n"
        f"⚡ টাস্ক সার্ভিস: <b>{tasks_status}</b>\n"
        f"💵 সর্বনিম্ন উইথড্রো: <b>{min_wd} BDT</b>\n\n"
        "নিচের বাটনগুলো থেকে নিয়ন্ত্রণ করুন:"
    )
    kb = await get_admin_keyboard()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(F.data == "admin_toggle_tasks")
async def handle_toggle_tasks(callback: CallbackQuery):
    """টাস্ক সুবিধা অন/অফ করা"""
    if not is_admin(callback.from_user.id):
        return

    current = await db.get_setting("tasks_enabled", "true")
    new_status = "false" if current == "true" else "true"
    await db.update_setting("tasks_enabled", new_status)
    
    status_msg = "বন্ধ" if new_status == "false" else "চালু"
    await callback.answer(f"⚠️ টাস্ক সেকশন এখন {status_msg} করা হয়েছে!", show_alert=True)
    
    kb = await get_admin_keyboard()
    await callback.message.edit_reply_markup(reply_markup=kb)

@admin_router.callback_query(F.data == "admin_settings")
async def handle_admin_settings(callback: CallbackQuery):
    """সেটিংস মেনু"""
    if not is_admin(callback.from_user.id):
        return

    min_wd = await db.get_setting("min_withdraw", "50.0")
    ref_comm = await db.get_setting("referral_commission", "10.0")

    text = (
        "⚙️ <b>বোট কনফিগারেশন সেটিংস:</b>\n\n"
        f"💵 বর্তমানে সর্বনিম্ন উইথড্রো: <b>{min_wd} BDT</b>\n"
        f"🎁 রেফারেল কমিশন: <b>{ref_comm}%</b>\n\n"
        "যা পরিবর্তন করতে চান নির্বাচন করুন:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit Min Withdraw", callback_data="edit_min_withdraw")],
        [InlineKeyboardButton(text="✏️ Edit Ref Commission", callback_data="edit_ref_comm")],
        [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(F.data == "edit_min_withdraw")
async def handle_edit_min_withdraw(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminStates.waiting_for_min_withdraw)
    await callback.message.edit_text("✏️ নতুন **সর্বনিম্ন উইথড্রো পরিমাণ (BDT)** লিখে পাঠান (যেমন: 50, 100):")

@admin_router.message(AdminStates.waiting_for_min_withdraw)
async def process_new_min_withdraw(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    try:
        val = float(message.text.strip())
        await db.update_setting("min_withdraw", str(val))
        await message.answer(f"✅ সর্বনিম্ন উইথড্রো সফলভাবে <b>{val} BDT</b> সেট করা হয়েছে!", parse_mode="HTML")
    except ValueError:
        await message.answer("⚠️ শুধুমাত্র ইংরেজিতে সংখ্যা লিখুন।")
    await state.clear()

@admin_router.callback_query(F.data == "admin_back")
async def handle_admin_back(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    kb = await get_admin_keyboard()
    await callback.message.edit_text("👑 <b>এডমিন কন্ট্রোল প্যানেল</b>", reply_markup=kb, parse_mode="HTML")

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
    success = await db.update_withdrawal_status(req_id, status)

    if success:
        msg = "✅ উইথড্রো এপ্রুভ হয়েছে।" if status == "approved" else "❌ উইথড্রো রিজেক্ট এবং টাকা রিফান্ড করা হয়েছে।"
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
