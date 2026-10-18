import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

from config import BOT_TOKEN
from database import db
from admin import admin_router
from withdraw import withdraw_router
from tasks import task_manager
from verifier import inbox_verifier

# লোগিং কনফিগারেশন
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class TaskStates(StatesGroup):
    working_on_task = State()

def get_main_keyboard():
    """মূল মেনু কিবোর্ড (উইথড্রো বাটন সহ)"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Register a new Gmail")],
            [KeyboardButton(text="👤 My Profile"), KeyboardButton(text="🔗 Referral Link")],
            [KeyboardButton(text="💵 Withdraw")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_task_action_keyboard():
    """টাস্ক ভেরিফাই বা ক্যানসেল করার ইনলাইন কিবোর্ড"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Verify Task", callback_data="verify_task")],
        [InlineKeyboardButton(text="❌ Cancel Task", callback_data="cancel_task")]
    ])
    return keyboard

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """স্টার্ট কমান্ড এবং রেফারেল ট্র্যাকিং"""
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    # রেফারেল আইডি হ্যান্ডেল করা (/start <ref_id>)
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    # ইউজার ডাটাবেজে রেজিস্টার বা ফেচ করা
    await db.get_or_create_user(user_id=user_id, username=username, referred_by=referred_by)

    welcome_text = (
        f"👋 স্বাগতম <b>{message.from_user.first_name}</b>!\n\n"
        "🤖 এটি আপনার অটোমেটেড জিমেইল ফার্মিং এবং টাস্ক আর্নিং বট।\n"
        "নিচের বাটন থেকে নতুন টাস্ক নিয়ে কাজ শুরু করুন, রেফার করে কমিশন পান এবং সহজে উইথড্রো করুন!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "➕ Register a new Gmail")
async def handle_register_btn(message: Message, state: FSMContext):
    """নতুন জিমেইল টাস্ক জেনারেট বা স্টক থেকে দেওয়া"""
    try:
        db_task = await db.get_available_task()
        if db_task:
            task = db_task
        else:
            task = task_manager.generate_random_gmail()

        await state.set_state(TaskStates.working_on_task)
        await state.update_data(current_task=task)

        first_name = task.get("first_name") or task['email'].split('@')[0].capitalize()
        last_name = task.get("last_name") or "❌"

        text = (
            "✏️ <b>নিচে দেওয়া তথ্য দিয়ে জিমেইল একাউন্ট তৈরি করুন:</b>\n\n"
            f"👤 <b>First Name:</b> <code>{first_name}</code>\n"
            f"👤 <b>Last Name:</b> <code>{last_name}</code>\n"
            f"📧 <b>Email:</b> <code>{task['email']}</code>\n"
            f"🔑 <b>Password:</b> <code>{task['password']}</code>\n\n"
            "⚠️ <i>অবশ্যই হুবহু এই তথ্যগুলো ব্যবহার করবেন।</i>\n\n"
            f"🛡️ <b>Recovery Email:</b>\n<code>{task['recovery']}</code>"
        )
        await message.answer(text, reply_markup=get_task_action_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error generating task: {e}")
        await message.answer("⚠️ টাস্ক লোড করতে সমস্যা হয়েছে। দয়া করে একটু পর আবার চেষ্টা করুন।")

@router.callback_query(F.data == "cancel_task")
async def handle_cancel_task(callback: CallbackQuery, state: FSMContext):
    """টাস্ক বাতিল করার হ্যান্ডলার"""
    await state.clear()
    await callback.message.edit_text("❌ টাস্কটি বাতিল করা হয়েছে।")
    await callback.answer()

@router.callback_query(TaskStates.working_on_task, F.data == "verify_task")
async def handle_verify_task(callback: CallbackQuery, state: FSMContext):
    """টাস্ক সম্পূর্ণ হয়েছে কি না ইনবক্স চেক করে ভেরিফাই করা"""
    data = await state.get_data()
    task = data.get("current_task")

    if not task:
        await callback.answer("⚠️ কোনো ভুল বা মেয়াদোত্তীর্ণ টাস্ক। আবার চেষ্টা করুন।", show_alert=True)
        await state.clear()
        return

    email = task["email"]
    await callback.message.edit_text("🔍 ইনবক্স চেক করা হচ্ছে... দয়া করে অপেক্ষা করুন ⏳")

    # অটোমেটেড ইনবক্স চেকিং
    is_verified = await inbox_verifier.check_inbox(email)

    if is_verified:
        reward = float(task.get("reward", 10.0))
        task_id = task.get("id", 0)

        success = await db.complete_task(task_id=task_id, user_id=callback.from_user.id, reward=reward)
        if success:
            await callback.message.edit_text(
                f"🎉 <b>অভিনন্দন! আপনার টাস্ক সফলভাবে ভেরিফাই হয়েছে।</b>\n\n"
                f"💰 ব্যালেন্সে যোগ হয়েছে: <b>+{reward} BDT</b>",
                parse_mode="HTML"
            )
        else:
            await callback.message.edit_text("⚠️ টাস্ক কমপ্লিট করতে ডাটাবেজে সমস্যা হয়েছে। এডমিনের সাথে যোগাযোগ করুন।")
    else:
        await callback.message.edit_text(
            "❌ <b>ভেরিফিকেশন ব্যর্থ হয়েছে!</b>\n\n"
            "এখনো গুগল থেকে কোনো কনফার্মেশন মেইল আসেনি। একাউন্ট তৈরি করে রিকভারি মেইল ঠিকমতো বসিয়েছেন তো?\n\n"
            "চেষ্টা চালিয়ে যান অথবা চাইলে আবার ভেরিফাই করতে পারেন:",
            reply_markup=get_task_action_keyboard(),
            parse_mode="HTML"
        )
        return

    await state.clear()

@router.message(F.text == "👤 My Profile")
async def handle_profile(message: Message):
    """ইউজার প্রোফাইল ও ব্যালেন্স চেক"""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    balance = user.get("balance", 0.0)
    completed = user.get("completed_tasks", 0)

    text = (
        "👤 <b>আপনার প্রোফাইল:</b>\n\n"
        f"🆔 ইউজার আইডি: <code>{user_id}</code>\n"
        f"💰 মূল ব্যালেন্স: <b>{balance} BDT</b>\n"
        f"✅ সফল টাস্ক: <b>{completed} টি</b>"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🔗 Referral Link")
async def handle_referral(message: Message):
    """রেফারেল লিংক জেনারেট করা"""
    user_id = message.from_user.id
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        "🔗 <b>রেফারেল প্রোগ্রাম (১০% কমিশন):</b>\n\n"
        "আপনার বন্ধুদের আমাদের বোটে আমন্ত্রণ জানান। তারা জিমেইল টাস্ক সম্পন্ন করে যে পেমেন্ট পাবে, তার ওপর আপনি আজীবন <b>১০% কমিশন</b> পাবেন!\n\n"
        "আপনার রেফারেল লিংক:\n"
        f"<code>{ref_link}</code>"
    )
    await message.answer(text, parse_mode="HTML")

async def handle_web(request):
    """রেন্ডার সার্ভারের জন্য ডামি ওয়েব রেসপন্স"""
    return web.Response(text="Gmail Farmer Bot is running live 24/7! 🚀")

async def start_web_server():
    """রেন্ডার পোর্ট বাইন্ডিং হ্যান্ডেল করার ওয়েব সার্ভার"""
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Dummy web server started on port {port}")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # সমস্ত রাউটার রেজিস্টার করা (এডমিন, উইথড্রো এবং মেইন ইউজার)
    dp.include_router(admin_router)
    dp.include_router(withdraw_router)
    dp.include_router(router)

    # রেন্ডারের জন্য ব্যাকগ্রাউন্ড ওয়েব সার্ভার চালু করা
    await start_web_server()

    logger.info("🚀 Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
