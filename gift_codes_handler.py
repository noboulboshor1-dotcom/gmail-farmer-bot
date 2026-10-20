"""
Gift Code Redemption Handler
Allows users to redeem gift codes for rewards
Admin can create and manage gift codes
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database_enhanced import db

logger = logging.getLogger(__name__)

gift_router = Router(name="gifts")


class GiftStates(StatesGroup):
    """FSM states for gift code operations."""
    waiting_for_code = State()
    admin_waiting_for_code_creation = State()
    admin_waiting_for_reward = State()
    admin_waiting_for_quantity = State()


# ================================================================
# USER GIFT CODE REDEMPTION
# ================================================================

def get_gift_keyboard() -> InlineKeyboardMarkup:
    """Get gift code redemption keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 কোড রিডিম করুন", callback_data="gift_redeem")],
        [InlineKeyboardButton(text="📊 সক্রিয় কোড দেখুন", callback_data="gift_view_active")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="gift_back")],
    ])


@gift_router.message(Command("gift"))
async def cmd_gift(message: Message, state: FSMContext):
    """Main gift code menu."""
    await state.clear()
    
    text = (
        "🎁 <b>গিফট কোড সিস্টেম</b>\n\n"
        "আমাদের বিশেষ গিফট কোডগুলি রিডিম করুন এবং বোনাস পান!\n\n"
        "• প্রতিটি কোড একবার ব্যবহার করা যায়\n"
        "• কোডের মেয়াদ ৩০ দিন\n"
        "• যেকোনো সময় রিডিম করতে পারেন"
    )
    
    try:
        await message.answer(text, reply_markup=get_gift_keyboard())
    except Exception as e:
        logger.exception(f"Error showing gift menu: {e}")
        await message.answer("⚠️ মেনু লোড করতে ত্রুটি।")


@gift_router.callback_query(F.data == "gift_redeem")
async def handle_gift_redeem(callback: CallbackQuery, state: FSMContext):
    """Start gift code redemption process."""
    await state.set_state(GiftStates.waiting_for_code)
    
    text = (
        "🎁 <b>গিফট কোড রিডিম করুন</b>\n\n"
        "আপনার গিফট কোড প্রবেশ করান:\n"
        "(উদাহরণ: GIFT2024001)"
    )
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="gift_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error starting redemption: {e}")
        await callback.answer("⚠️ শুরু করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@gift_router.message(GiftStates.waiting_for_code)
async def handle_gift_code_input(message: Message, state: FSMContext):
    """Process submitted gift code."""
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    if not code or len(code) < 3 or len(code) > 50:
        await message.answer(
            "❌ অবৈধ কোড ফর্ম্যাট।\n"
            "কোডটি 3-50 অক্ষরের মধ্যে হতে হবে।"
        )
        return
    
    # Redeem the code
    success, message_text, reward = await db.redeem_gift_code(user_id, code)
    
    if success:
        await message.answer(
            f"{message_text}\n\n"
            f"🎉 <b>অভিনন্দন!</b> আপনার ব্যালেন্স আপডেট হয়েছে।"
        )
        # Show main menu
        await state.clear()
        await handle_gift_back(message, state)
    else:
        await message.answer(message_text)
        # Stay in waiting state for retry
        await message.answer("পুনরায় চেষ্টা করুন বা /gift বাতিল করুন।")


@gift_router.callback_query(F.data == "gift_view_active")
async def handle_view_active_codes(callback: CallbackQuery):
    """Show count of active gift codes."""
    try:
        count = await db.get_active_gift_codes_count()
        
        text = (
            "📊 <b>সক্রিয় গিফট কোড</b>\n\n"
            f"বর্তমানে {count} টি সক্রিয় গিফট কোড উপলব্ধ।\n\n"
            "আপনার বন্ধুদের থেকে কোড পান বা প্রশাসকদের কাছ থেকে অনুরোধ করুন।"
        )
        
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🎁 কোড রিডিম করুন", callback_data="gift_redeem")],
                [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="gift_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error viewing active codes: {e}")
        await callback.answer("⚠️ লোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@gift_router.callback_query(F.data == "gift_back")
async def handle_gift_back(callback: CallbackQuery, state: FSMContext):
    """Return to gift menu."""
    await state.clear()
    
    text = (
        "🎁 <b>গিফট কোড সিস্টেম</b>\n\n"
        "আমাদের বিশেষ গিফট কোডগুলি রিডিম করুন এবং বোনাস পান!\n\n"
        "• প্রতিটি কোড একবার ব্যবহার করা যায়\n"
        "• কোডের মেয়াদ ৩০ দিন\n"
        "• যেকোনো সময় রিডিম করতে পারেন"
    )
    
    try:
        await callback.message.edit_text(text=text, reply_markup=get_gift_keyboard())
    except Exception as e:
        logger.exception(f"Error returning to gift menu: {e}")
        await callback.answer("⚠️ ফিরতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


# ================================================================
# ADMIN GIFT CODE CREATION
# ================================================================

async def admin_create_gift_codes(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Start gift code creation flow (called from admin panel)."""
    await state.set_state(GiftStates.admin_waiting_for_code_creation)
    
    text = (
        "🎁 <b>গিফট কোড তৈরি করুন</b>\n\n"
        "প্রথমে কোড প্রবেশ করান:\n"
        "(উদাহরণ: GIFT2024001)"
    )
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="admin_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error starting gift code creation: {e}")
        await callback.answer("⚠️ শুরু করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


async def handle_admin_gift_code_submission(message: Message, state: FSMContext):
    """Store gift code and ask for reward."""
    code = message.text.strip().upper()
    
    if not code or len(code) < 3 or len(code) > 50:
        await message.answer(
            "❌ অবৈধ কোড ফর্ম্যাট।\n"
            "কোডটি 3-50 অক্ষরের মধ্যে হতে হবে।"
        )
        return
    
    # Store in FSM context
    await state.update_data(code=code)
    await state.set_state(GiftStates.admin_waiting_for_reward)
    
    await message.answer(
        f"✅ কোড: {code}\n\n"
        "এখন পুরস্কার পরিমাণ প্রবেশ করান (টাকায):\n"
        "(উদাহরণ: 100.50)"
    )


async def handle_admin_reward_submission(message: Message, state: FSMContext):
    """Store reward and ask for quantity."""
    try:
        reward = float(message.text.strip())
        if reward <= 0:
            await message.answer("❌ পুরস্কার ১.০ এর বেশি হতে হবে।")
            return
    except ValueError:
        await message.answer("❌ অবৈধ সংখ্যা। দশমিক ব্যবহার করুন (যেমন: 100.50)")
        return
    
    await state.update_data(reward=reward)
    await state.set_state(GiftStates.admin_waiting_for_quantity)
    
    await message.answer(
        f"✅ পুরস্কার: ৳ {reward:.2f}\n\n"
        "কতটি কোড তৈরি করতে চান?\n"
        "(উদাহরণ: 5)"
    )


async def handle_admin_quantity_submission(message: Message, state: FSMContext):
    """Create gift codes."""
    try:
        quantity = int(message.text.strip())
        if quantity < 1 or quantity > 1000:
            await message.answer("❌ পরিমাণ 1-1000 এর মধ্যে হতে হবে।")
            return
    except ValueError:
        await message.answer("❌ অবৈধ সংখ্যা।")
        return
    
    data = await state.get_data()
    code = data.get("code", "")
    reward = data.get("reward", 0.0)
    
    # Create gift codes
    success = await db.create_gift_code(
        code=code,
        reward=reward,
        quantity=quantity,
        expires_days=30,
    )
    
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ <b>সফল!</b>\n\n"
            f"কোড: {code}\n"
            f"পুরস্কার: ৳ {reward:.2f}\n"
            f"পরিমাণ: {quantity} টি\n\n"
            "গিফট কোড তৈরি হয়েছে।"
        )
    else:
        await message.answer("❌ গিফট কোড তৈরিতে ব্যর্থ। লগ চেক করুন।")
