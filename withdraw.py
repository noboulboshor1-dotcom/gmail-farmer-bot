import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db

logger = logging.getLogger(__name__)
withdraw_router = Router()

class WithdrawStates(StatesGroup):
    waiting_for_method = State()
    waiting_for_account = State()
    waiting_for_amount = State()

@withdraw_router.message(F.text == "💵 Withdraw")
async def handle_withdraw_btn(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    balance = float(user.get("balance", 0.0))
    
    # ডাটাবেজ থেকে লাইভ মিনিমাম উইথড্র লিমিট আনা
    min_wd_str = await db.get_setting("min_withdraw", "50.0")
    try:
        min_withdraw = float(min_wd_str)
    except ValueError:
        min_withdraw = 50.0

    if balance < min_withdraw:
        await message.answer(
            f"⚠️ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n\n"
            f"আপনার বর্তমান ব্যালেন্স: <b>{balance} BDT</b>\n"
            f"সর্বনিম্ন উইথড্রো লিমিট: <b>{min_withdraw} BDT</b>",
            parse_mode="HTML"
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="bkash", callback_data="wd_method_bkash"), InlineKeyboardButton(text="Nagad", callback_data="wd_method_nagad")],
        [InlineKeyboardButton(text="Binance (USDT)", callback_data="wd_method_binance")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="wd_cancel")]
    ])
    await state.set_state(WithdrawStates.waiting_for_method)
    await message.answer("💳 <b>পেমেন্ট পাওয়ার মাধ্যম (Method) নির্বাচন করুন:</b>", reply_markup=kb, parse_mode="HTML")

@withdraw_router.callback_query(WithdrawStates.waiting_for_method, F.data.startswith("wd_method_"))
async def handle_wd_method(callback: CallbackQuery, state: FSMContext):
    method = callback.data.replace("wd_method_", "").upper()
    await state.update_data(withdraw_method=method)
    await state.set_state(WithdrawStates.waiting_for_account)
    await callback.message.edit_text(f"📱 আপনার <b>{method}</b> অ্যাকাউন্ট নম্বর বা ওয়ালেট অ্যাড্রেস লিখে পাঠান:")
    await callback.answer()

@withdraw_router.message(WithdrawStates.waiting_for_account)
async def handle_wd_account(message: Message, state: FSMContext):
    account_no = message.text.strip()
    if len(account_no) < 4:
        await message.answer("⚠️ সঠিক অ্যাকাউন্ট নম্বর বা অ্যাড্রেস প্রদান করুন।")
        return
    
    await state.update_data(withdraw_account=account_no)
    
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, "")
    balance = float(user.get("balance", 0.0))
    
    min_wd_str = await db.get_setting("min_withdraw", "50.0")
    min_withdraw = float(min_wd_str) if min_wd_str.replace('.','',1).isdigit() else 50.0

    await state.set_state(WithdrawStates.waiting_for_amount)
    await message.answer(
        f"💵 আপনি কত টাকা উইথড্র করতে চান?\n\n"
        f"আপনার ব্যালেন্স: <b>{balance} BDT</b>\n"
        f"সর্বনিম্ন লিমিট: <b>{min_withdraw} BDT</b>\n\n"
        "টাকার পরিমাণ সংখ্যায় লিখে পাঠান:",
        parse_mode="HTML"
    )

@withdraw_router.message(WithdrawStates.waiting_for_amount)
async def handle_wd_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.strip())
    except ValueError:
        await message.answer("⚠️ দয়া করে সঠিক সংখ্যায় পরিমাণ লিখুন।")
        return

    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, "")
    balance = float(user.get("balance", 0.0))
    
    min_wd_str = await db.get_setting("min_withdraw", "50.0")
    min_withdraw = float(min_wd_str) if min_wd_str.replace('.','',1).isdigit() else 50.0

    if amount < min_withdraw:
        await message.answer(f"⚠️ সর্বনিম্ন উইথড্রো <b>{min_withdraw} BDT</b>। এর কম উইথড্রো করা যাবে না।", parse_mode="HTML")
        return

    if amount > balance:
        await message.answer("⚠️ আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই।")
        return

    data = await state.get_data()
    method = data.get("withdraw_method")
    account_no = data.get("withdraw_account")

    success = await db.create_withdrawal_request(user_id, amount, method, account_no)
    if success:
        from main import get_main_keyboard
        await message.answer(
            "✅ <b>উইথড্রো রিকোয়েস্ট সফলভাবে জমা হয়েছে!</b>\n\n"
            f"💰 পরিমাণ: <b>{amount} BDT</b>\n"
            f"💳 মাধ্যম: <b>{method}</b>\n"
            f"📱 নম্বর: <code>{account_no}</code>\n\n"
            "⏳ এডমিন যাচাই করে ২৪ ঘণ্টার মধ্যে পেমেন্ট পাঠিয়ে দেবেন।",
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ উইথড্রো রিকোয়েস্ট সাবমিট করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")

    await state.clear()

@withdraw_router.callback_query(F.data == "wd_cancel")
async def handle_wd_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ উইথড্রো প্রক্রিয়া বাতিল করা হয়েছে।")
    from main import get_main_keyboard
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()
