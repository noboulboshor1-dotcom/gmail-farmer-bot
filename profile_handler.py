"""
User Profile Dashboard Handler
Displays comprehensive user profile statistics and account information
"""

import html
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database_enhanced import db

logger = logging.getLogger(__name__)

profile_router = Router(name="profile")


def format_profile_text(stats: dict) -> str:
    """
    Format profile statistics into readable Bengali text.
    
    Args:
        stats: User stats dictionary from db.get_user_stats()
        
    Returns:
        Formatted profile text
    """
    user_id = stats.get("user_id", "N/A")
    balance = stats.get("balance", 0.0)
    completed = stats.get("completed_tasks", 0)
    pending = stats.get("pending_tasks", 0)
    rejected = stats.get("rejected_tasks", 0)
    referral_count = stats.get("referral_count", 0)
    referral_income = stats.get("referral_income", 0.0)
    username = stats.get("username", "Unknown")

    text = (
        "👤 <b>আপনার প্রোফাইল ড্যাশবোর্ড</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>👤 ইউজার আইডি:</b> <code>{user_id}</code>\n"
        f"<b>📝 ইউজারনেম:</b> {html.escape(username)}\n\n"
        "💰 <b>আর্নিং এবং ব্যালেন্স</b>\n"
        f"  • <b>বর্তমান ব্যালেন্স:</b> <b>৳ {balance:.2f}</b>\n"
        f"  • <b>রেফারেল আয়:</b> ৳ {referral_income:.2f}\n\n"
        "✅ <b>টাস্ক পরিসংখ্যান</b>\n"
        f"  • <b>সম্পন্ন টাস্ক:</b> {completed} টি\n"
        f"  • <b>পেন্ডিং সাবমিশন:</b> {pending} টি\n"
        f"  • <b>প্রত্যাখ্যাত টাস্ক:</b> {rejected} টি\n\n"
        "👥 <b>রেফারেল</b>\n"
        f"  • <b>মোট রেফার্ড ব্যবহারকারী:</b> {referral_count} জন\n"
        f"  • <b>রেফারেল লিংক:</b> <code>/start {user_id}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "নিচের অপশনগুলো থেকে একটি নির্বাচন করুন:"
    )

    return text


def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Get profile view action buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 রিফ্রেশ", callback_data="profile_refresh")],
        [InlineKeyboardButton(text="💳 উইথড্রো", callback_data="profile_withdraw")],
        [InlineKeyboardButton(text="🎁 রেফারেল শেয়ার", callback_data="profile_referral_share")],
        [InlineKeyboardButton(text="🔐 অ্যাকাউন্ট সেটিংস", callback_data="profile_settings")],
        [InlineKeyboardButton(text="🔙 মূল মেনু", callback_data="profile_back")],
    ])


def get_referral_share_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Get keyboard with shareable referral links."""
    ref_link = f"https://t.me/your_bot?start={user_id}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📲 Telegram এ শেয়ার করুন",
            url=f"tg://msg?url={ref_link}&text=আমার সাথে যোগ দিন এবং আয় করুন!"
        )],
        [InlineKeyboardButton(
            text="📋 লিংক কপি করুন",
            callback_data="profile_copy_referral_link"
        )],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="profile_back")],
    ])


# ================================================================
# PROFILE HANDLERS
# ================================================================

@profile_router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    """Display user profile dashboard."""
    await state.clear()
    
    user_id = message.from_user.id
    stats = await db.get_user_stats(user_id)
    
    text = format_profile_text(stats)
    
    try:
        await message.answer(text, reply_markup=get_profile_keyboard())
    except Exception as e:
        logger.exception(f"Error displaying profile for user {user_id}: {e}")
        await message.answer("⚠️ প্রোফাইল লোড করতে ত্রুটি। পুনরায় চেষ্টা করুন।")


@profile_router.callback_query(F.data == "profile_refresh")
async def handle_profile_refresh(callback: CallbackQuery):
    """Refresh profile statistics."""
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    
    text = format_profile_text(stats)
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_profile_keyboard()
        )
    except Exception as e:
        logger.exception(f"Error refreshing profile for user {user_id}: {e}")
        await callback.answer("⚠️ রিফ্রেশ করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer("✅ রিফ্রেশ করা হয়েছে।")


@profile_router.callback_query(F.data == "profile_referral_share")
async def handle_referral_share(callback: CallbackQuery):
    """Show referral sharing options."""
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    
    referral_link = f"https://t.me/your_bot?start={user_id}"
    
    text = (
        "🎁 <b>আপনার রেফারেল প্রোগ্রাম</b>\n\n"
        f"<b>আপনার রেফারাল লিংক:</b>\n"
        f"<code>{referral_link}</code>\n\n"
        f"<b>মোট রেফার্ড:</b> {stats.get('referral_count', 0)} জন\n"
        f"<b>রেফারেল আয়:</b> ৳ {stats.get('referral_income', 0.0):.2f}\n\n"
        "প্রতিটি সফল রেফারেলের জন্য কমিশন পান!\n"
        "আপনার বন্ধুদের সাথে লিংক শেয়ার করুন।"
    )
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_referral_share_keyboard(user_id)
        )
    except Exception as e:
        logger.exception(f"Error showing referral options: {e}")
        await callback.answer("⚠️ লোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@profile_router.callback_query(F.data == "profile_copy_referral_link")
async def handle_copy_referral_link(callback: CallbackQuery):
    """Send referral link for copying."""
    user_id = callback.from_user.id
    referral_link = f"https://t.me/your_bot?start={user_id}"
    
    text = (
        "📋 <b>আপনার রেফারেল লিংক:</b>\n\n"
        f"<code>{referral_link}</code>\n\n"
        "<i>উপরের লিংকটি কপি করুন এবং আপনার বন্ধুদের সাথে শেয়ার করুন।</i>"
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="profile_back")],
        ]))
    except Exception as e:
        logger.exception(f"Error copying referral link: {e}")
        await callback.answer("⚠️ লিংক কপি করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@profile_router.callback_query(F.data == "profile_settings")
async def handle_account_settings(callback: CallbackQuery):
    """Show account settings."""
    text = (
        "🔐 <b>অ্যাকাউন্ট সেটিংস</b>\n\n"
        "শীঘ্রই আসছে:\n"
        "• পাসওয়ার্ড পরিবর্তন\n"
        "• ইমেইল যাচাইকরণ\n"
        "• নোটিফিকেশন প্রেফারেন্স"
    )
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="profile_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error showing settings: {e}")
        await callback.answer("⚠️ লোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@profile_router.callback_query(F.data == "profile_back")
async def handle_profile_back(callback: CallbackQuery):
    """Return to main profile view."""
    user_id = callback.from_user.id
    stats = await db.get_user_stats(user_id)
    
    text = format_profile_text(stats)
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_profile_keyboard()
        )
    except Exception as e:
        logger.exception(f"Error returning to profile: {e}")
        await callback.answer("⚠️ ফিরতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@profile_router.message(F.text == "👤 আমার প্রোফাইল")
async def handle_profile_button(message: Message, state: FSMContext):
    """Handle profile button from main menu."""
    await state.clear()
    
    user_id = message.from_user.id
    stats = await db.get_user_stats(user_id)
    
    text = format_profile_text(stats)
    
    try:
        await message.answer(text, reply_markup=get_profile_keyboard())
    except Exception as e:
        logger.exception(f"Error displaying profile: {e}")
        await message.answer("⚠️ প্রোফাইল লোড করতে ত্রুটি।")
