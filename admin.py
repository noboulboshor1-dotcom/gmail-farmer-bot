import os
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from config import ADMIN_ID

logger = logging.getLogger(__name__)
admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_tasks = State()

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add Gmail Tasks (Bulk)", callback_data="admin_add_tasks")],
            [InlineKeyboardButton(text="📊 Bot Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🧹 Clear Completed Tasks", callback_data="admin_clear_stock")]
        ]
    )

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "🛠️ <b>Admin Control Panel</b>\n\n"
        "নিচের অপশনগুলো ব্যবহার করে বোটের টাস্ক ও ডাটা ম্যানেজ করুন:",
        reply_markup=get_admin_keyboard(),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    users_count = await db.get_all_users_count()
    stock_count = await db.get_stock_count()
    
    text = (
        "📊 <b>বোটের লাইভ স্ট্যাটিস্টিকস:</b>\n\n"
        f"👥 মোট রেজিস্টার্ড ইউজার: <code>{users_count}</code> জন\n"
        f"📦 স্টকে খালি জিমেইল টাস্ক আছে: <code>{stock_count}</code> টি"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_keyboard(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "admin_add_tasks")
async def start_add_tasks(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await state.set_state(AdminStates.waiting_for_tasks)
    text = (
        "📥 <b>বাল্ক জিমেইল টাস্ক আপলোড:</b>\n\n"
        "নিচের ফরম্যাটে মেসেজ পাঠান (প্রতি লাইনে ১টি করে):\n"
        "<code>email|password|recovery</code>\n\n"
        "<b>উদাহরণ:</b>\n"
        "<code>user1@gmail.com|pass123|rec1@mail.com</code>\n"
        "<code>user2@gmail.com|pass456|rec2@mail.com</code>"
    )
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_tasks)
async def process_bulk_tasks(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    lines = message.text.strip().split("\n")
    task_list = []
    
    for line in lines:
        parts = line.split("|")
        if len(parts) == 3:
            task_list.append({
                "email": parts[0].strip(),
                "password": parts[1].strip(),
                "recovery": parts[2].strip(),
                "reward": 10.0,
                "status": "available"
            })

    if task_list:
        added_count = await db.add_bulk_tasks(task_list)
        await message.answer(f"✅ সফলভাবে <b>{added_count}</b> টি জিমেইল টাস্ক স্টকে যোগ করা হয়েছে!", parse_mode="HTML")
    else:
        await message.answer("❌ ফরম্যাট সঠিক হয়নি! <code>email|password|recovery</code> ফরম্যাটে আবার চেষ্টা করুন।", parse_mode="HTML")
    
    await state.clear()
