import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

class TaskStates(StatesGroup):
    working_on_gmail = State()
    waiting_for_fb_uid = State()
    waiting_for_fb_cookies = State()
    waiting_for_insta_2fa = State()

@router.message.outer_middleware()
async def check_banned_user(handler, event, data):
    if hasattr(event, "from_user") and event.from_user:
        user = await db.get_or_create_user(event.from_user.id, "")
        if user.get("is_banned"):
            if isinstance(event, Message):
                await event.answer("🚫 <b>আপনার অ্যাকাউন্টটি ব্যান করা হয়েছে!</b>", parse_mode="HTML")
            return
    return await handler(event, data)

def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Tasks ▸"), KeyboardButton(text="💰 Balance")],
            [KeyboardButton(text="💵 Withdraw"), KeyboardButton(text="🎁 My Referrals")],
            [KeyboardButton(text="🎁 Daily Bonus"), KeyboardButton(text="🎧 Support")],
            [KeyboardButton(text="💡 I am New")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Cancel")]
        ],
        resize_keyboard=True
    )
    return keyboard

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
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
        "🤖 এটি আপনার অল-ইন-ওয়ান প্রিমিয়াম ফার্মিং এবং আর্নিং বট।"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "❌ Cancel")
async def handle_cancel_button(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ কাজ বাতিল করা হয়েছে।", reply_markup=get_main_keyboard())

@router.message(F.text == "🎁 Daily Bonus")
async def handle_daily_bonus(message: Message):
    success, msg, amount = await db.claim_daily_bonus(message.from_user.id)
    await message.answer(msg, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "📋 Tasks ▸")
async def handle_tasks_menu(message: Message):
    categories = await db.get_categories()
    keyboard_buttons = []
    
    for cat in categories:
        if cat["is_enabled"]:
            keyboard_buttons.append([InlineKeyboardButton(text=cat["category_name"], callback_data=f"cat_task_{cat['category_key']}")])
    
    keyboard_buttons.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_task")])
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    if not keyboard_buttons or len(keyboard_buttons) <= 1:
        await message.answer("⚠️ বর্তমানে সকল টাস্ক ক্যাটাগরি সাময়িকভাবে বন্ধ রয়েছে。", reply_markup=get_main_keyboard())
        return

    await message.answer("🎯 <b>কাজের ক্যাটাগরি নির্বাচন করুন:</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("cat_task_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    cat_key = callback.data.replace("cat_task_", "")
    
    if cat_key == "gmail":
        try:
            db_task = await db.get_available_task()
            task = db_task if db_task else task_manager.generate_random_gmail()

            await state.set_state(TaskStates.working_on_gmail)
            await state.update_data(current_task=task)

            first_name = task.get("first_name") or task['email'].split('@')[0].capitalize()
            last_name = task.get("last_name") or "❌"

            text = (
                "✏️ <b>নিচে দেওয়া তথ্য দিয়ে জিমেইল একাউন্ট তৈরি করুন:</b>\n\n"
                f"👤 <b>First Name:</b> <code>{first_name}</code>\n"
                f"👤 <b>Last Name:</b> <code>{last_name}</code>\n"
                f"📧 <b>Email:</b> <code>{task['email']}</code>\n"
                f"🔑 <b>Password:</b> <code>{task['password']}</code>\n\n"
                f"🛡️ <b>Recovery Email:</b>\n<code>{task['recovery']}</code>"
            )
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Verify Task", callback_data="verify_task")],
                [InlineKeyboardButton(text="❌ Cancel Task", callback_data="cancel_task")]
            ])
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            await callback.message.answer("⚠️ কাজ চলাকালীন যেকোনো সময় নিচে '❌ Cancel' চাপুন:", reply_markup=get_cancel_keyboard())
        except Exception as e:
            logger.error(f"Error generating task: {e}")
            await callback.message.answer("⚠️ টাস্ক লোড করতে সমস্যা হয়েছে।", reply_markup=get_main_keyboard())

    elif cat_key == "facebook":
        await state.set_state(TaskStates.waiting_for_fb_uid)
        text = (
            "👤 <b>First name:</b> Sem\n"
            "👤 <b>Last name:</b> De Jong\n"
            "🔑 <b>Password:</b> nbbd@18\n\n"
            "📘 Create an account with the information above and click <b>Send UID</b> below:"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Send UID", callback_data="prompt_fb_uid")]
        ])
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.message.answer("⚠️ ইউআইডি টাইপ করে পাঠাতে পারেন অথবা নিচে ক্যানসেল করতে পারেন:", reply_markup=get_cancel_keyboard())

    elif cat_key == "instagram":
        await state.set_state(TaskStates.waiting_for_insta_2fa)
        text = "🔑 <b>Enter 2FA Key:</b> ⤵️"
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.message.answer("⚠️ আপনার 2FA Key পেস্ট করে সেন্ড করুন:", reply_markup=get_cancel_keyboard())

    else:
        await callback.answer("⚠️ এই ক্যাটাগরির কাজ বর্তমানে স্টকে নেই।", show_alert=True)

@router.callback_query(F.data == "prompt_fb_uid")
async def handle_prompt_fb_uid(callback: CallbackQuery):
    await callback.message.answer("🏷️ <b>Enter your Facebook account 14-16 digit UID:</b>", parse_mode="HTML")
    await callback.answer()

@router.message(TaskStates.waiting_for_fb_uid)
async def process_fb_uid_submission(message: Message, state: FSMContext):
    uid_text = message.text.strip()
    if uid_text.isdigit() and len(uid_text) >= 10:
        await state.update_data(fb_uid=uid_text)
        await state.set_state(TaskStates.waiting_for_fb_cookies)
        await message.answer("📘 <b>Now enter your Facebook account Cookies:</b>", parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await message.answer("⚠️ সঠিক 14-16 ডিজিটের Facebook UID দিন।", reply_markup=get_cancel_keyboard())

@router.message(TaskStates.waiting_for_fb_cookies)
async def process_fb_cookies_submission(message: Message, state: FSMContext):
    cookies_text = message.text.strip()
    if len(cookies_text) > 10:
        data = await state.get_data()
        fb_uid = data.get("fb_uid")
        
        try:
            db.supabase.table("user_submissions").insert({
                "user_id": message.from_user.id,
                "category": "facebook",
                "submission_data": f"UID: {fb_uid} | Cookies: {cookies_text}",
                "status": "pending"
            }).execute()
        except Exception as e:
            logger.error(f"Error saving FB submission: {e}")

        await state.clear()
        await message.answer(
            "✅ <b>Submitted successfully!</b>\n\n"
            "Your Facebook Account has been submitted to the buyer. Payment will be credited once verified.",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ <b>Invalid Cookies!</b> Please paste complete cookies.", parse_mode="HTML", reply_markup=get_cancel_keyboard())

@router.message(TaskStates.waiting_for_insta_2fa)
async def process_insta_2fa_submission(message: Message, state: FSMContext):
    key_text = message.text.strip()
    if len(key_text) >= 8:
        try:
            db.supabase.table("user_submissions").insert({
                "user_id": message.from_user.id,
                "category": "instagram",
                "submission_data": f"2FA Key: {key_text}",
                "status": "pending"
            }).execute()
        except Exception as e:
            logger.error(f"Error saving Insta submission: {e}")

        fake_code = "164226"
        text = (
            "Click the button below after opening account:\n"
            "Click the button below to copy the code ⤵️\n\n"
            f"📋 <code>{fake_code}</code>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Account Created", callback_data="insta_created_confirm")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML", reply_markup_remove=True)
        await state.clear()
    else:
        await message.answer("⚠️ সঠিক 2FA Key প্রদান করুন।", reply_markup=get_cancel_keyboard())

@router.callback_query(F.data == "insta_created_confirm")
async def handle_insta_confirm(callback: CallbackQuery):
    await callback.message.edit_text("⏳ <b>Payment will be processed within 2 to 72 hours.</b>", parse_mode="HTML")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(F.data == "cancel_task")
async def handle_cancel_task(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ টাস্কটি বাতিল করা হয়েছে।")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()

@router.callback_query(TaskStates.working_on_gmail, F.data == "verify_task")
async def handle_verify_task(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    task = data.get("current_task")

    if not task:
        await callback.answer("⚠️ মেয়াদোত্তীর্ণ টাস্ক।", show_alert=True)
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
            await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
        else:
            await callback.message.edit_text("⚠️ টাস্ক কমপ্লিট করতে সমস্যা হয়েছে।")
            await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Verify Task", callback_data="verify_task")],
            [InlineKeyboardButton(text="❌ Cancel Task", callback_data="cancel_task")]
        ])
        await callback.message.edit_text(
            "❌ <b>ভেরিফিকেশন ব্যর্থ হয়েছে!</b>\n\n"
            "গুগল থেকে রিকভারি মেইলে কনফার্মেশন মেসেজ আসেনি। আবার চেষ্টা করুন:",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    await state.clear()

@router.message(F.text == "💰 Balance")
async def handle_balance_btn(message: Message):
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
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "🎁 My Referrals")
async def handle_referral(message: Message):
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
    
    share_url = f"https://t.me/share/url?url={ref_link}&text=Join%20this%20amazing%20earning%20bot!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Share Now", url=share_url)]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.message(F.text == "🎧 Support")
async def handle_support(message: Message):
    text = (
        "🎧 <b>সাপোর্ট ও হেল্প সেন্টার</b>\n\n"
        "যেকোনো প্রয়োজনে আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন:\n"
        "👉 এডমিন সাপোর্ট: @AdminSupport"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(F.text == "💡 I am New")
async def handle_iam_new(message: Message):
    text = (
        "💡 <b>নতুনদের জন্য নির্দেশিকা:</b>\n\n"
        "১. <b>Tasks ▸</b> থেকে পছন্দের টাস্ক নিন।\n"
        "২. জিমেইল টাস্কে রিকভারি মেইল বসিয়ে অটোভেরিফাই করুন।\n"
        "৩. ফেসবুক ও ইনস্টাগ্রাম টাস্কে আইডি/2FA কী সাবমিট করুন।\n"
        "৪. প্রতিদিন <b>Daily Bonus</b> দাবি করুন!"
    )
    await message.answer(text, reply_markup=get_main_keyboard(), parse_mode="HTML")

async def handle_web(request):
    return web.Response(text="Super Premium Farmer Bot Live! 🚀")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"🌐 Server running on port {port}")

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(admin_router)
    dp.include_router(withdraw_router)
    dp.include_router(router)

    await start_web_server()
    logger.info("🚀 Starting bot polling...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
