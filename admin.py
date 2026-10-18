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
    """এডমিন প্যানেলের ইনলাইন কীবোর্ড"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Tasks (Bulk)", callback_data="admin_add_bulk")],
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
    """স্ট্যাটিস্টিক্স দেখার হ্যান্ডলার"""
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

@admin_router.callback_query(F.data == "admin_add_bulk")
async def handle_add_bulk_click(callback: CallbackQuery, state: FSMContext):
    """বাল্ক টাস্ক যোগ করার প্রম্পট"""
    if not is_admin(callback.from_user.id):
        return
    
    await state.set_state(AdminStates.waiting_for_bulk_tasks)
    text = (
        "📥 <b>বাল্ক জিমেইল টাস্ক আপলোড:</b>\n\n"
        "নিচের যেকোনো একটি ফরম্যাটে মেসেজ পাঠান (প্রতি লাইনে ১টি করে):\n\n"
        "<b>১. শুধু ইমেইল ও পাসওয়ার্ড (রিকভারি, ফার্স্ট ও লাস্ট নেম অটো তৈরি হবে):</b>\n"
        "<code>email|password</code>\n\n"
        "<b>২. কাস্টম রিকভারি মেইল সহ:</b>\n"
        "<code>email|password|recovery</code>\n\n"
        "<b>৩. সম্পূর্ণ কাস্টম তথ্য সহ:</b>\n"
        "<code>email|password|recovery|first_name|last_name</code>\n\n"
        "<i>উদাহরণ:</i>\n"
        "<code>user1@gmail.com|pass123</code>\n"
        "<code>user2@gmail.com|pass456|rec2@1secmail.com</code>"
    )
    await callback.message.edit_text(text, parse_mode="HTML")

@admin_router.message(AdminStates.waiting_for_bulk_tasks)
async def process_bulk_tasks_input(message: Message, state: FSMContext):
    """এডমিনের পাঠানো ডাটা প্রসেস করে ডাটাবেজে স্টোর করা"""
    if not is_admin(message.from_user.id):
        return

    lines = message.text.strip().split("\n")
    task_list = []

    for line in lines:
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) >= 2:
            email = parts[0]
            password = parts[1]
            
            # ৩ নম্বর পার্ট: রিকভারি মেইল (না থাকলে অটোমেটিক জেনারেট)
            if len(parts) >= 3:
                recovery = parts[2]
            else:
                gen = task_manager.generate_random_gmail()
                recovery = gen["recovery"]

            # ৪ নম্বর পার্ট: First Name (না থাকলে ইমেইলের ১ম অংশ ইউজারনেম হিসেবে)
            first_name = parts[3] if len(parts) >= 4 else email.split("@")[0].capitalize()
            
            # ৫ নম্বর পার্ট: Last Name (না থাকলে খালি বা ডিফল্ট চিহ্ন)
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
        await message.answer(f"✅ সফলভাবে <b>{inserted_count}</b> টি জিমেইল টাস্ক আপলোড করা হয়েছে!", parse_mode="HTML")
    else:
        await message.answer("⚠️ কোনো সঠিক ফরম্যাটের ডাটা পাওয়া যায়নি। দয়া করে আবার সঠিকভাবে পাঠাল।")

    await state.clear()

@admin_router.callback_query(F.data == "admin_clear_tasks")
async def handle_clear_tasks(callback: CallbackQuery):
    """কমপ্লিট টাস্ক ক্লিয়ার করার অ্যালার্ট"""
    if not is_admin(callback.from_user.id):
        return
    await callback.answer("🧹 সম্পন্ন হওয়া টাস্কগুলো ক্লিয়ার করা হয়েছে।", show_alert=True)
