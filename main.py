import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web

from config import BOT_TOKEN
from keyboards import get_reply_main_menu, get_task_action_keyboard, get_back_button
from database import db
from tasks import task_manager
from admin import admin_router
from verifier import check_recovery_email_received

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

router = Router()

# ইউজারের একটিভ টাস্ক স্টোর করার জন্য State
class TaskStates(StatesGroup):
    working_on_task = State()

@router.message(CommandStart())
async def cmd_start(message: Message):
    try:
        args = message.text.split()
        referred_by = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

        await db.get_or_create_user(
            message.from_user.id, 
            message.from_user.username or "NoUsername", 
            referred_by=referred_by
        )
        
        welcome_text = (
            "<b>Register Gmail accounts and get paid for it.</b>\n\n"
            "For each Normal account you will receive <b>0.15$</b> (or 10 BDT)\n"
            "For each 2FA account you will receive <b>0.25$</b>\n\n"
            "Everything is very simple. The bot provides you with data for registering a Gmail account, you copy it and go to Google. Create a Gmail account there, then return to the bot."
        )
        await message.answer(welcome_text, reply_markup=get_reply_main_menu(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await message.answer("⚠️ একটি প্রযুক্তিগত ত্রুটি ঘটেছে। কিছুক্ষণ পর আবার চেষ্টা করুন।")

@router.message(F.text == "➕ Register a new Gmail")
async def handle_register_btn(message: Message, state: FSMContext):
    try:
        db_task = await db.get_available_task()
        if db_task:
            task = db_task
        else:
            task = task_manager.generate_random_gmail()

        # ইউজারের স্টেট ডাটাতে টাস্ক ইনফো সেভ রাখা
        await state.set_state(TaskStates.working_on_task)
        await state.update_data(current_task=task)

        text = (
            "✏️ <b>Register Gmail account using the specified data</b>\n\n"
            f"👤 <b>First Name:</b> {task['email'].split('@')[0].capitalize()}\n"
            f"👤 <b>Last Name:</b> ❌\n"
            f"📧 <b>Email:</b> <code>{task['email']}</code>\n"
            f"🔑 <b>Password:</b> <code>{task['password']}</code>\n\n"
            "⚠️ <i>Be sure to use the exact specified data.</i>\n\n"
            f"🛡️ <b>Recovery Email:</b>\n<code>{task['recovery']}</code>"
        )
        await message.answer(text, reply_markup=get_task_action_keyboard(), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error generating task: {e}")
        await message.answer("⚠️ টাস্ক লোড করতে সমস্যা হয়েছে। দয়া করে একটু পর আবার চেষ্টা করুন।")

@router.callback_query(F.data == "task_done")
async def task_done_callback(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    task = user_data.get("current_task")

    if not task:
        await callback.answer("⚠️ আপনার কোনো সক্রিয় টাস্ক পাওয়া যায়নি! নতুন টাস্ক নিন।", show_alert=True)
        return

    await callback.message.edit_text("⏳ <b>ভেরিফাই করা হচ্ছে... অনুগ্রহ করে ১০-১৫ সেকেন্ড অপেক্ষা করুন!</b>\n<i>গুগল থেকে রিকভারি মেইলে কনফার্মেশন পাঠানো হয়েছে কি না তা চেক করা হচ্ছে।</i>", parse_mode="HTML")

    # অটোমেটিক ইনবক্স ভেরিফিকেশন সিস্টেম
    is_verified = await check_recovery_email_received(task["recovery"])

    if is_verified:
        task_id = task.get("id", 0)
        success = await db.complete_task(task_id=task_id, user_id=user_id, reward=10.0)
        
        if success:
            await callback.message.edit_text(
                "✅ <b>অভিনন্দন! আপনার জিমেইল তৈরি সফলভাবে ভেরিফাই হয়েছে।</b>\n\n💵 ১০ টাকা আপনার ব্যালেন্সে যোগ করা হয়েছে।",
                parse_mode="HTML"
            )
            await state.clear()
        else:
            await callback.message.edit_text("⚠️ ডাটাবেজ অপাডেশনে ত্রুটি হয়েছে। এডমিনের সাথে যোগাযোগ করুন।", parse_mode="HTML")
    else:
        await callback.message.edit_text(
            "❌ <b>কাজটি সঠিক হয়নি!</b>\n\n"
            "আমরা রিকভারি মেইলে গুগলের কোনো কনফার্মেশন মেইল পাইনি।\n"
            "দয়া করে নিশ্চিত করুন যে আপনি দেওয়া রিকভারি মেইলটি সঠিকভাবে যুক্ত করেছেন এবং আবার চেষ্টা করুন।",
            reply_markup=get_task_action_keyboard(),
            parse_mode="HTML"
        )

@router.callback_query(F.data == "task_cancel")
async def task_cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ টাস্কটি বাতিল করা হয়েছে। নতুন টাস্ক নিতে নিচের মেনু ব্যবহার করুন।", parse_mode="HTML")
    await callback.answer()

@router.message(F.text == "💰 My Balance")
async def handle_balance_btn(message: Message):
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username or "")
    text = (
        f"💰 <b>আপনার অ্যাকাউন্ট ব্যালেন্স:</b>\n\n"
        f"👤 ইউজার আইডি: <code>{message.from_user.id}</code>\n"
        f"💵 বর্তমান ব্যালেন্স: <b>{user.get('balance', 0.0)} টাকা</b>\n"
        f"📊 সম্পন্ন টাস্ক: <b>{user.get('completed_tasks', 0)} টি</b>"
    )
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.message(F.text == "📦 My Accounts")
async def handle_accounts_btn(message: Message):
    user = await db.get_or_create_user(message.from_user.id, message.from_user.username or "")
    text = f"📦 আপনার জমা দেওয়া মোট সফল অ্যাকাউন্ট: <b>{user.get('completed_tasks', 0)} টি</b>"
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.message(F.text == "👥 Referrals")
async def handle_referral_btn(message: Message):
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    text = (
        "👥 <b>রেফারেল প্রোগ্রাম (১০% কমিশন):</b>\n\n"
        "আপনার বন্ধুদের আমাদের বোটে আমন্ত্রণ জানান! আপনার রেফার করা কোনো ইউজার যখনই কোনো টাস্ক কমপ্লিট করবে, তার আয়ের **১০% কমিশন** আপনি লাইফটাইম পেতে থাকবেন!\n\n"
        f"🔗 আপনার রেফারেল লিংক:\n<code>{ref_link}</code>"
    )
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.message(F.text == "⚙️ Help")
async def handle_help_btn(message: Message):
    text = (
        "⚙️ <b>সাহায্য ও নিয়মাবলী:</b>\n\n"
        "১. সঠিক তথ্য ও রিকভারি ইমেইল দিয়ে জিমেইল অ্যাকাউন্ট তৈরি করুন।\n"
        "২. রিকভারি ইমেইল যোগ না করলে কাজটি অটো-ভেরিফাই হবে না।\n"
        "৩. কাজ শেষ করে 'Done' বাটনে চাপলে অটো-ভেরিফিকেশন সম্পন্ন হবে।"
    )
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.callback_query(F.data == "main_menu")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.answer("🤖 প্রধান মেনুতে ফিরে এসেছেন:", reply_markup=get_reply_main_menu())
    await callback.answer()

async def handle(request):
    return web.Response(text="Gmail Farmer Bot Pro with Auto Verification is running 24/7!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Dummy web server started on port {port}")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    dp.include_router(admin_router)
    dp.include_router(router)
    
    asyncio.create_task(start_dummy_server())
    
    logger.info("Starting bot polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
