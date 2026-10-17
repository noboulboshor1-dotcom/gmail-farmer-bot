import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiohttp import web
from config import BOT_TOKEN
from keyboards import get_main_menu, get_back_button
from database import db
from tasks import task_manager

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    # ইউজারের ডেটাবেজ এন্ট্রি চেক বা তৈরি করা
    await db.get_or_create_user(message.from_user.id, message.from_user.username or "NoUsername")
    
    welcome_text = (
        f"👋 **স্বাগতম {message.from_user.first_name}!**\n\n"
        f"🤖 **Gmail Hunt Bot**-এ আপনাকে স্বাগতম।\n"
        f"নিচের মেনু থেকে আপনার পছন্দমত অপশন বেছে নিন:"
    )
    await message.answer(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    welcome_text = "🤖 **প্রধান মেনু:**\nনিচের অপশনগুলো থেকে একটি সিলেক্ট করুন:"
    await callback.message.edit_text(welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "get_task")
async def task_callback(callback: CallbackQuery):
    # র্যান্ডম জিমেইল টাস্ক জেনারেট করা
    task = task_manager.generate_random_gmail()
    text = (
        "📥 **নতুন জিমেইল টাস্ক:**\n\n"
        f"📧 **ইমেইল:** `{task['email']}`\n"
        f"🔑 **পাসওয়ার্ড:** `{task['password']}`\n"
        f"📬 **রিকভারি মেইল:** `{task['recovery']}`\n"
        f"💵 **রিওয়ার্ড:** `{task['reward']} টাকা`\n\n"
        "⚠️ উপরের তথ্যগুলো দিয়ে জিমেইল অ্যাকাউন্ট তৈরি করুন।"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "my_balance")
async def balance_callback(callback: CallbackQuery):
    user = await db.get_or_create_user(callback.from_user.id, callback.from_user.username or "")
    text = (
        f"💰 **আপনার অ্যাকাউন্ট ব্যালেন্স:**\n\n"
        f"👤 ইউজার আইডি: `{callback.from_user.id}`\n"
        f"💵 বর্তমান ব্যালেন্স: `{user.get('balance', 0.0)}` টাকা\n"
        f"📊 সম্পন্ন টাস্ক: `{user.get('completed_tasks', 0)}` টি"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "help_info")
async def help_callback(callback: CallbackQuery):
    text = (
        "⚙️ **ফার্মিং নিয়মাবলী:**\n\n"
        "১. দেওয়া তথ্য দিয়ে সঠিকভাকে জিমেইল একাউন্ট তৈরি করতে হবে।\n"
        "২. রিকভারি মেইল যুক্ত করা বাধ্যতামূলক।\n"
        "৩. কোনো সমস্যা হলে এডমিনের সাথে যোগাযোগ করুন।"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="Markdown")
    await callback.answer()

# Render Web Service-এর জন্য ডামি সার্ভার লজিক
async def handle(request):
    return web.Response(text="Gmail Farmer Bot is running 24/7!")

async def start_dummy_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    
    # ব্যাকগ্রাউন্ডে ডামি সার্ভার চালু রাখা
    asyncio.create_task(start_dummy_server())
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
