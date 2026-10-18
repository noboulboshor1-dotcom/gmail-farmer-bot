import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiohttp import web

from config import BOT_TOKEN
from keyboards import get_reply_main_menu, get_task_action_keyboard, get_back_button
from database import db
from tasks import task_manager
from admin import admin_router

# প্রফেশনাল লগিং সেটআপ
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    try:
        await db.get_or_create_user(message.from_user.id, message.from_user.username or "NoUsername")
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
async def handle_register_btn(message: Message):
    try:
        # প্রথমে সুপাবেজ ডাটাবেজ স্টক থেকে টাস্ক খোঁজা
        db_task = await db.get_available_task()
        
        if db_task:
            task = db_task
        else:
            # স্টকে টাস্ক না থাকলে ফলব্যাক জেনারেটর ব্যবহার করা
            task = task_manager.generate_random_gmail()

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
        "👥 <b>রেফারেল প্রোগ্রাম:</b>\n\n"
        "আপনার বন্ধুদের আমাদের বোটে আমন্ত্রণ জানান এবং প্রতি রেফারে আকর্ষণীয় বোনাস অর্জন করুন!\n\n"
        f"🔗 আপনার রেফারেল লিংক:\n<code>{ref_link}</code>"
    )
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.message(F.text == "⚙️ Help")
async def handle_help_btn(message: Message):
    text = (
        "⚙️ <b>সাহায্য ও নিয়মাবলী:</b>\n\n"
        "১. সঠিক তথ্য দিয়ে জিমেইল অ্যাকাউন্ট তৈরি করুন।\n"
        "২. কাজ শেষ করে 'Done' বাটনে ক্লিক করুন।\n"
        "৩. কোনো সমস্যা হলে এডমিনের সাথে যোগাযোগ করুন।"
    )
    await message.answer(text, reply_markup=get_back_button(), parse_mode="HTML")

@router.callback_query(F.data == "task_done")
async def task_done_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    try:
        user = await db.get_or_create_user(user_id, callback.from_user.username or "")
        reward_amount = 10.0
        
        new_balance = float(user.get('balance', 0.0)) + reward_amount
        new_tasks = int(user.get('completed_tasks', 0)) + 1
        
        await db.supabase.table("users").update({
            "balance": new_balance, 
            "completed_tasks": new_tasks
        }).eq("user_id", user_id).execute()
        
        await callback.message.edit_text(
            "✅ <b>অভিনন্দন! আপনার টাস্ক সফলভাবে জমা হয়েছে এবং ১০ টাকা আপনার ব্যালেন্সে যোগ করা হয়েছে।</b>",
            parse_mode="HTML"
        )
        await callback.answer("টাস্ক সফল!")
    except Exception as e:
        logger.error(f"Error completing task callback: {e}")
        await callback.answer("⚠️ টাস্ক সাবমিট করতে সমস্যা হয়েছে।", show_alert=True)

@router.callback_query(F.data == "task_cancel")
async def task_cancel_callback(callback: CallbackQuery):
    await callback.message.edit_text("❌ টাস্কটি বাতিল করা হয়েছে। নতুন টাস্ক নিতে নিচের মেনু ব্যবহার করুন স্টক থেকে।", parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def back_to_main_callback(callback: CallbackQuery):
    await callback.message.answer("🤖 প্রধান মেনুতে ফিরে এসেছেন:", reply_markup=get_reply_main_menu())
    await callback.answer()

# Render Web Service-এর জন্য ব্যাকগ্রাউন্ড ডামি সার্ভার (24/7 সচল রাখার জন্য)
async def handle(request):
    return web.Response(text="Gmail Farmer Bot Pro is running 24/7!")

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
    
    # প্রথমে এডমিন রাউটার এবং তারপর সাধারণ ইউজার রাউটার রেজিস্টার করা
    dp.include_router(admin_router)
    dp.include_router(router)
    
    # ব্যাকগ্রাউন্ডে ডামি ওয়েব সার্ভার চালু রাখা
    asyncio.create_task(start_dummy_server())
    
    logger.info("Starting bot polling...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
