import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import get_main_keyboard, get_cancel_keyboard
from config import ADMIN_IDS, CATEGORY_REWARDS

logger = logging.getLogger(__name__)
social_router = Router()

# সোশ্যাল টাস্কের জন্য আলাদা স্টেট
class SocialTaskStates(StatesGroup):
    waiting_for_fb_uid = State()
    waiting_for_fb_cookies = State()
    waiting_for_insta_2fa = State()

# --- ফেসবুক টাস্ক হ্যান্ডলার ---
@social_router.callback_query(F.data == "prompt_fb_uid")
async def handle_prompt_fb_uid(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SocialTaskStates.waiting_for_fb_uid)
    await callback.message.answer("📘 <b>Enter your Facebook account 14-16 digit UID:</b>", parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()

@social_router.message(SocialTaskStates.waiting_for_fb_uid)
async def process_fb_uid(message: Message, state: FSMContext):
    uid_text = message.text.strip()
    if uid_text.isdigit() and 10 <= len(uid_text) <= 18:
        await state.update_data(fb_uid=uid_text)
        await state.set_state(SocialTaskStates.waiting_for_fb_cookies)
        await message.answer("🍪 <b>Now enter your Facebook account Cookies:</b>", parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await message.answer("⚠️ সঠিক 14-16 ডিজিটের Facebook UID প্রদান করুন।", reply_markup=get_cancel_keyboard())

@social_router.message(SocialTaskStates.waiting_for_fb_cookies)
async def process_fb_cookies(message: Message, state: FSMContext):
    cookies_text = message.text.strip()
    if len(cookies_text) > 10:
        data = await state.get_data()
        fb_uid = data.get("fb_uid")
        user_id = message.from_user.id
        
        details_str = f"UID: {fb_uid} | Cookies: {cookies_text}"
        
        # ডাটাবেজে সাবমিশন সেভ করা (db.client ব্যবহার করে)
        sub_id = None
        try:
            res = await db.client.table("user_submissions").insert({
                "user_id": user_id,
                "category": "facebook",
                "details": details_str,
                "status": "pending"
            }).execute()
            if res.data:
                sub_id = res.data[0]["id"]
        except Exception as e:
            logger.error(f"Error saving FB submission: {e}")

        await state.clear()
        await message.answer("✅ <b>Facebook Task Submitted Successfully!</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

        # এডমিনদের কাছে রিভিউ নোটিফিকেশন পাঠানো
        fb_reward = CATEGORY_REWARDS.get("facebook", 4.0)
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Accept", callback_data=f"app_sub_{sub_id}_{user_id}_fb"),
             InlineKeyboardButton(text="❌ Reject", callback_data=f"rej_sub_{sub_id}_{user_id}_fb")]
        ])
        admin_msg = (
            "📥 <b>নতুন টাস্ক সাবমিশন (Facebook)</b>\n\n"
            f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
            f"🏷️ <b>UID:</b> <code>{fb_uid}</code>\n"
            f"🍪 <b>Cookies:</b> <code>{cookies_text[:40]}...</code>\n"
            f"💰 <b>Reward:</b> <code>{fb_reward:.2f} BDT</code>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await message.bot.send_message(admin_id, admin_msg, reply_markup=admin_kb)
            except Exception:
                pass
    else:
        await message.answer("⚠️ <b>Invalid Cookies!</b> সঠিক কুকিজ প্রদান করুন।", parse_mode="HTML", reply_markup=get_cancel_keyboard())

# --- ইনস্টাগ্রাম টাস্ক হ্যান্ডলার ---
@social_router.callback_query(F.data == "prompt_insta_2fa")
async def handle_prompt_insta_2fa(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SocialTaskStates.waiting_for_insta_2fa)
    await callback.message.answer("🔑 <b>Enter 2FA Key:</b> ⤵️", parse_mode="HTML", reply_markup=get_cancel_keyboard())
    await callback.answer()

@social_router.message(SocialTaskStates.waiting_for_insta_2fa)
async def process_insta_2fa(message: Message, state: FSMContext):
    key_text = message.text.strip()
    if len(key_text) >= 6:
        user_id = message.from_user.id
        data = await state.get_data()
        username = data.get("insta_user", "N/A")
        password = data.get("insta_pass", "N/A")
        
        details_str = f"Username: {username} | Pass: {password} | 2FA: {key_text}"
        
        sub_id = None
        try:
            res = await db.client.table("user_submissions").insert({
                "user_id": user_id,
                "category": "instagram",
                "details": details_str,
                "status": "pending"
            }).execute()
            if res.data:
                sub_id = res.data[0]["id"]
        except Exception as e:
            logger.error(f"Error saving Insta submission: {e}")

        await state.clear()
        await message.answer("⏳ <b>আপনার ইনস্টাগ্রাম টাস্ক সফলভাবে সাবমিট হয়েছে। এডমিন যাচাই করে পেমেন্ট করবে।</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")

        # এডমিনদের কাছে ইনস্টাগ্রাম সাবমিশনের নোটিফিকেশন পাঠানো
        insta_reward = CATEGORY_REWARDS.get("instagram", 5.0)
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Accept", callback_data=f"app_sub_{sub_id}_{user_id}_insta"),
             InlineKeyboardButton(text="❌ Reject", callback_data=f"rej_sub_{sub_id}_{user_id}_insta")]
        ])
        admin_msg = (
            "📥 <b>নতুন টাস্ক সাবমিশন (Instagram)</b>\n\n"
            f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
            f"🏷️ <b>Username:</b> <code>{username}</code>\n"
            f"🔐 <b>Password:</b> <code>{password}</code>\n"
            f"🔑 <b>2FA Key:</b> <code>{key_text}</code>\n"
            f"💰 <b>Reward:</b> <code>{insta_reward:.2f} BDT</code>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await message.bot.send_message(admin_id, admin_msg, reply_markup=admin_kb)
            except Exception:
                pass
    else:
        await message.answer("⚠️ সঠিক 2FA Key প্রদান করুন।", reply_markup=get_cancel_keyboard())

@social_router.callback_query(F.data == "insta_created_confirm")
async def handle_insta_confirm(callback: CallbackQuery):
    await callback.message.edit_text("⏳ <b>আপনার ইনস্টাগ্রাম টাস্ক সফলভাবে সাবমিট হয়েছে।</b>", parse_mode="HTML")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()
