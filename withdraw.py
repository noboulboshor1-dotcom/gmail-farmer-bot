import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import db

logger = logging.getLogger(__name__)
withdraw_router = Router()

MIN_WITHDRAW_AMOUNT = 50.0  # সর্বনিম্ন উইথড্রো পরিমাণ (৫০ টাকা)

class WithdrawStates(StatesGroup):
    waiting_for_method = State()
    waiting_for_account = State()
    waiting_for_amount = State()

def get_payment_methods_keyboard():
    """পেমেন্ট মেথড সিলেক্ট করার ইনলাইন কিবোর্ড"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📱 bKash", callback_data="method_bkash"),
            InlineKeyboardButton(text="🟠 Nagad", callback_data="method_nagad")
        ],
        [
            InlineKeyboardButton(text="🚀 Rocket", callback_data="method_rocket"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_withdraw")
        ]
    ])
    return keyboard

@withdraw_router.message(F.text == "💵 Withdraw")
async def handle_withdraw_btn(message: Message, state: FSMContext):
    """ইউজার উইথড্রো বাটনে ক্লিক করলে প্রসেস শুরু"""
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    balance = float(user.get("balance", 0.0))

    if balance < MIN_WITHDRAW_AMOUNT:
        await message.answer(
            f"⚠️ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n\n"
            f"আপনার বর্তমান ব্যালেন্স: <b>{balance} BDT</b>\n"
            f"সর্বনিম্ন উইথড্রো পরিমাণ: <b>{MIN_WITHDRAW_AMOUNT} BDT</b>",
            parse_mode="HTML"
        )
        return

    await state.set_state(WithdrawStates.waiting_for_method)
    text = (
        "💳 <b>উইথড্রো পেমেন্ট মেথড নির্বাচন করুন:</b>\n\n"
        f"আপনার বর্তমান ব্যালেন্স: <b>{balance} BDT</b>\n"
        f"সর্বনিম্ন উইথড্রো: <b>{MIN_WITHDRAW_AMOUNT} BDT</b>"
    )
    await message.answer(text, reply_markup=get_payment_methods_keyboard(), parse_mode="HTML")

@withdraw_router.callback_query(F.data == "cancel_withdraw")
async def handle_cancel_withdraw(callback: CallbackQuery, state: FSMContext):
    """উইথড্রো বাতিল করা"""
    await state.clear()
    await callback.message.edit_text("❌ উইথড্রো আবেদন বাতিল করা হয়েছে।")
    await callback.answer()

@withdraw_router.callback_query(WithdrawStates.waiting_for_method, F.data.startswith("method_"))
async def process_method_choice(callback: CallbackQuery, state: FSMContext):
    """পেমেন্ট মেথড সেভ করা এবং অ্যাকাউন্ট নম্বর চাওয়া"""
    method = callback.data.split("_")[1].capitalize()
    await state.update_data(payment_method=method)
    await state.set_state(WithdrawStates.waiting_for_account)

    await callback.message.edit_text(
        f"📲 আপনি <b>{method}</b> নির্বাচন করেছেন।\n\n"
        f"দয়া করে আপনার <b>{method} Personal/Agent নম্বরটি</b> লিখে পাঠান:",
        parse_mode="HTML"
    )
    await callback.answer()

@withdraw_router.message(WithdrawStates.waiting_for_account)
async def process_account_number(message: Message, state: FSMContext):
    """অ্যাকাউন্ট নম্বর সেভ করা এবং পরিমাণের ইনপুট নেওয়া"""
    account_no = message.text.strip()
    
    if len(account_no) < 11 or not account_no.replace("+", "").isdigit():
        await message.answer("⚠️ একটি সঠিক মোবাইল নম্বর লিখুন (যেমন: 01712345678):")
        return

    await state.update_data(account_no=account_no)
    await state.set_state(WithdrawStates.waiting_for_amount)

    user = await db.get_or_create_user(message.from_user.id, "")
    balance = float(user.get("balance", 0.0))

    await message.answer(
        f"💰 কত টাকা উইথড্রো করতে চান তা লিখুন:\n"
        f"(সর্বনিম্ন <b>{MIN_WITHDRAW_AMOUNT} BDT</b>, সর্বোচ্চ <b>{balance} BDT</b>)",
        parse_mode="HTML"
    )

@withdraw_router.message(WithdrawStates.waiting_for_amount)
async def process_withdraw_amount(message: Message, state: FSMContext):
    """টাকার পরিমাণ চেক করা ও উইথড্রো রিকোয়েস্ট ডাটাবেজে তৈরি করা"""
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("⚠️ শুধুমাত্র ইংরেজিতে সংখ্যা লিখুন (যেমন: 50, 100):")
        return

    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, "")
    balance = float(user.get("balance", 0.0))

    if amount < MIN_WITHDRAW_AMOUNT:
        await message.answer(f"⚠️ সর্বনিম্ন উইথড্রো পরিমাণ {MIN_WITHDRAW_AMOUNT} BDT। আবার চেষ্টা করুন:")
        return

    if amount > balance:
        await message.answer(f"⚠️ আপনার একাউন্টে পর্যাপ্ত টাকা নেই! বর্তমান ব্যালেন্স: {balance} BDT")
        return

    data = await state.get_data()
    method = data.get("payment_method")
    account_no = data.get("account_no")

    # ডাটাবেজে রিকোয়েস্ট তৈরি
    success = await db.create_withdrawal(
        user_id=user_id,
        amount=amount,
        method=method,
        account_no=account_no
    )

    if success:
        await message.answer(
            "✅ <b>আপনার উইথড্রো আবেদন সফলভাবে জমা হয়েছে!</b>\n\n"
            f"💳 মেথড: <b>{method}</b>\n"
            f"📱 নম্বর: <b>{account_no}</b>\n"
            f"💰 পরিমাণ: <b>{amount} BDT</b>\n\n"
            "⏳ এডমিন শীঘ্রই আপনার পেমেন্টটি রিভিউ করে প্রদান করবে।",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ উইথড্রো সাবমিট করতে সমস্যা হয়েছে। দয়া করে আবার চেষ্টা করুন।")

    await state.clear()
