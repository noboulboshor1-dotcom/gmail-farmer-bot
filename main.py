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
    """স্ক্রিনশটের আদলে প্রিমিয়াম মেইন মেনু কিবোর্ড"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Tasks ▸"), KeyboardButton(text="💰 Balance")],
            [KeyboardButton(text="💵 Withdraw"), KeyboardButton(text="🎁 My Referrals")],
            [KeyboardButton(text="🎧 Support"), KeyboardButton(text="💡 I am New")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_task_category_keyboard():
    """টাস্ক ক্যাটাগরি ইনলাইন কিবোর্ড"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📧 Gmail Tasks", callback_data="start_gmail_task")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_task")]
    ])
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

    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    await db.get_or_create_user(user_id=user_id, username=username, referred_by=referred_by)

    welcome_text = (
        f"👋 স্বাগতম <b>{message.from_user.first_name}</b>!\n\n"
        "🤖 এটি আপনার প্রিমিয়াম জিমেইল ফার্মিং এবং টাস্ক আর্নিং বট।\n"
        "নিচের প্রিমিয়াম মেনু থেকে টাস্ক সম্পন্ন করুন, রেফার করে আয় করুন এবং সহজে উইথড্রো করুন!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "📋 Tasks ▸")
async def handle_tasks_menu(message: Message):
    """টাস্ক ক্যাটাগরি মেনু (এডমিন প্যানেল থেকে টাস্ক বন্ধ থাকলে চেক করবে)"""
    tasks_enabled = (await db.get_setting("tasks_enabled", "true")) == "true"
    if not tasks_enabled:
        await message.answer("⚠️ বর্তমান সময়ে টাস্ক সার্ভিস সাময়িকভাবে বন্ধ রয়েছে। দয়া করে পরে চেষ্টা করুন।")
        return

    text = "🎯 <b>কাজের ক্যাটাগরি নির্বাচন করুন:</b>"
    await message.answer(text, reply_markup=get_task_category_keyboard(), parse_mode="HTML")

@router.callback_query(F.data == "start_gmail_task")
async def handle_gmail_task(callback: CallbackQuery, state: FSMContext):
    """জিমেইল টাস্ক জেনারেট বা স্টক থেকে দেওয়া"""
    tasks_enabled = (await db.get_setting("tasks_enabled", "true")) == "true"
    if not tasks_enabled:
        await callback.answer("⚠️ টাস্ক সার্ভিস বর্তমানে বন্ধ আছে।", show_alert=True)
        return

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
        await callback.message.edit_text(text, reply_markup=get_task_action_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error generating task: {e}")
        await callback.message.answer("⚠️ টাস্ক লোড করতে সমস্যা হয়েছে। দয়া করে একটু পর আবার চেষ্টা করুন।")

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

@router.message(F.text == "💰 Balance")
async def handle_balance_btn(message: Message):
    """ইউজার ব্যালেন্স ও সম্পন্ন টাস্ক ইনফো"""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    balance = user.get("balance", 0.0)
    completed = user.get("completed_tasks", 0)

    text = (
        "💰 <b>আপনার ব্যালেন্স একাউন্ট ইনফো:</b>\n\n"
        f"🆔 ইউজার আইডি: <code>{user_id}</code>\n"
        f"💵 মূল ব্যালেন্স: <b>{balance} BDT</b>\n"
        f"✅ সফল টাস্ক সম্পন্ন: <b>{completed} টি</b>"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "🎁 My Referrals")
async def handle_referral(message: Message):
    """রেফারেল স্ট্যাটাস ও শেয়ার বাটন (স্ক্রিনশটের ডিজাইনে)"""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    
    total_ref = user.get("referral_count", 0)
    ref_income = user.get("referral_income", 0.0)
    
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    comm_pct = await db.get_setting("referral_commission", "10.0")

    text = (
        "🎁 <b>My Referrals</b>\n"
        f"👥 Total Refer: <b>{total_ref}</b>\n"
        f"💰 Total Refer Income: <b>{ref_income:.4f} BDT</b>\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>\n\n"
        f"ℹ️ You will receive <b>{comm_pct}% commission</b> on earnings from each task completed by your referrals."
    )
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=Join%20this%20amazing%20earning%20bot%20and%20start%20earning%20money!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Share Now", url=share_url)]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🎧 Support")
async def handle_support(message: Message):
    """সাপোর্ট মেনু"""
    text = (
        "🎧 <b>সাপোর্ট ও হেল্প সেন্টার</b>\n\n"
        "বট ব্যবহারে কোনো সমস্যা হলে বা পেমেন্ট সংক্রান্ত যেকোনো প্রয়োজনে আমাদের সাথে যোগাযোগ করুন:\n"
        "👉 এডমিন সাপোর্ট: @AdminSupport\n"
        "📖 কাজের নিয়মাবলী জানতে আমাদের ব্লগ ভিজিট করতে পারেন।"
    )
    await message.answer(text, parse_mode="HTML")

@router.message(F.text == "💡 I am New")
async def handle_iam_new(message: Message):
    """নতুনদের জন্য গাইডলাইন"""
    text = (
        "💡 <b>নতুনদের জন্য নির্দেশিকা:</b>\n\n"
        "১. <b>Tasks ▸</b> এ ক্লিক করে জিমেইল টাস্ক নিন।\n"
        "২. বোটের দেওয়া নাম ও পাসওয়ার্ড দিয়ে একটি নতুন জিমেইল অ্যাকাউন্ট খুলুন এবং রিকভারি মেইলে বোটের দেওয়া 1secmail বসান।\n"
        "৩. অ্যাকাউন্ট খোলা শেষ হলে <b>Verify Task</b> এ ক্লিক করুন।\n"
        "৪. ইনবক্স ভেরিফাই হওয়ার সাথে সাথে আপনার অ্যাকাউন্টে টাকা যোগ হয়ে যাবে!\n"
        "৫. সর্বনিম্ন টাকা হলে <b>Withdraw</b> থেকে বিকাশ/নগদে তুলে নিন।"
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

    # সমস্ত রাউটার রেজিস্টার করা
    dp.include_router(admin_router)
    dp.include_router(withdraw_router)
    dp.include_router(router)

    # ব্যাকগ্রাউন্ড ওয়েব সার্ভার চালু
    await start_web_server()

    logger.info("🚀 Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
