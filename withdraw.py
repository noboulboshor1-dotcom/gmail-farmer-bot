import html
import logging
import math
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMIN_IDS
from database import db
from keyboards import (
    BTN_WITHDRAW,
    get_cancel_keyboard,
    get_main_keyboard,
    safe_edit,
    withdrawal_review_kb,
)

logger = logging.getLogger(__name__)
withdraw_router = Router(name="withdraw")

METHODS = {"bkash": "bKash", "nagad": "Nagad", "binance": "Binance (USDT)"}

_BD_MOBILE = re.compile(r"^(?:\+?88)?(01[3-9]\d{8})$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TRC20 = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_BEP20 = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BINANCE_ID = re.compile(r"^\d{6,20}$")


class WithdrawStates(StatesGroup):
    waiting_for_method = State()
    waiting_for_account = State()
    waiting_for_amount = State()


def validate_account(method_key: str, raw: str) -> str | None:
    """Return the normalised account string, or None when it is not valid for the method."""
    value = (raw or "").strip().replace(" ", "")
    if method_key in ("bkash", "nagad"):
        m = _BD_MOBILE.match(value)
        return m.group(1) if m else None
    if method_key == "binance":
        if _BINANCE_ID.match(value) or _EMAIL.match(value) or _TRC20.match(value) or _BEP20.match(value):
            return value
    return None


def account_hint(method_key: str) -> str:
    if method_key in ("bkash", "nagad"):
        return "১১ ডিজিটের মোবাইল নম্বর (যেমন: <code>01XXXXXXXXX</code>)"
    return "Binance Pay ID / ইমেইল / TRC20 বা BEP20 ওয়ালেট অ্যাড্রেস"


async def _live_limits(user_id: int) -> tuple[float, float]:
    """(balance, min_withdraw) straight from the DB - no caching."""
    user = await db.get_or_create_user(user_id, "")
    balance = float(user.get("balance") or 0.0)
    min_withdraw = await db.get_float_setting("min_withdraw", 50.0)
    return balance, min_withdraw


def _fmt(x: float) -> str:
    return f"{float(x):.2f}"


async def notify_admins_new_withdrawal(bot, req: dict) -> None:
    text = (
        "🔔 <b>নতুন উইথড্রো রিকোয়েস্ট</b>\n\n"
        f"👤 ইউজার আইডি: <code>{req['user_id']}</code>\n"
        f"💰 পরিমাণ: <b>{_fmt(req['amount'])} BDT</b>\n"
        f"💳 মেথড: <b>{html.escape(str(req['method']))}</b>\n"
        f"📱 অ্যাকাউন্ট: <code>{html.escape(str(req['account_no']))}</code>"
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, text, reply_markup=withdrawal_review_kb(req["id"]))
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not notify admin %s: %s", admin_id, e)


# --- Step 0: entry ----------------------------------------------------------
@withdraw_router.message(F.text == BTN_WITHDRAW)
async def handle_withdraw_btn(message: Message, state: FSMContext):
    await state.clear()
    balance, min_withdraw = await _live_limits(message.from_user.id)

    if balance < min_withdraw:
        await message.answer(
            "⚠️ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n\n"
            f"আপনার বর্তমান ব্যালেন্স: <b>{_fmt(balance)} BDT</b>\n"
            f"সর্বনিম্ন উইথড্রো লিমিট: <b>{_fmt(min_withdraw)} BDT</b>",
            reply_markup=get_main_keyboard(),
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="bKash", callback_data="wd_method_bkash"),
         InlineKeyboardButton(text="Nagad", callback_data="wd_method_nagad")],
        [InlineKeyboardButton(text="Binance (USDT)", callback_data="wd_method_binance")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="wd_cancel")],
    ])
    await state.set_state(WithdrawStates.waiting_for_method)
    await message.answer(
        f"💰 ব্যালেন্স: <b>{_fmt(balance)} BDT</b>\n\n"
        "💳 <b>পেমেন্ট পাওয়ার মাধ্যম (Method) নির্বাচন করুন:</b>",
        reply_markup=kb,
    )


# --- Step 1: method ---------------------------------------------------------
@withdraw_router.callback_query(F.data.startswith("wd_method_"))
async def handle_wd_method(callback: CallbackQuery, state: FSMContext):
    key = callback.data.removeprefix("wd_method_")
    if key not in METHODS:
        await callback.answer("⚠️ অবৈধ মাধ্যম।", show_alert=True)
        return

    balance, min_withdraw = await _live_limits(callback.from_user.id)
    if balance < min_withdraw:
        await state.clear()
        await safe_edit(
            callback.message,
            "⚠️ <b>পর্যাপ্ত ব্যালেন্স নেই!</b>\n"
            f"সর্বনিম্ন উইথড্রো লিমিট এখন <b>{_fmt(min_withdraw)} BDT</b>।",
        )
        await callback.answer()
        return

    await state.update_data(withdraw_method=key)
    await state.set_state(WithdrawStates.waiting_for_account)
    await safe_edit(callback.message, f"✅ নির্বাচিত মাধ্যম: <b>{METHODS[key]}</b>")
    await callback.message.answer(
        f"📱 আপনার <b>{METHODS[key]}</b> অ্যাকাউন্ট পাঠান:\n{account_hint(key)}",
        reply_markup=get_cancel_keyboard(),
    )
    await callback.answer()


# --- Step 2: account --------------------------------------------------------
@withdraw_router.message(WithdrawStates.waiting_for_account, F.text)
async def handle_wd_account(message: Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("withdraw_method")
    if key not in METHODS:
        await state.clear()
        await message.answer("⚠️ সেশন মেয়াদোত্তীর্ণ। আবার <b>Withdraw</b> চাপুন।", reply_markup=get_main_keyboard())
        return

    account = validate_account(key, message.text)
    if not account:
        await message.answer(f"⚠️ সঠিক তথ্য দিন:\n{account_hint(key)}", reply_markup=get_cancel_keyboard())
        return

    balance, min_withdraw = await _live_limits(message.from_user.id)
    await state.update_data(withdraw_account=account)
    await state.set_state(WithdrawStates.waiting_for_amount)
    await message.answer(
        "💵 আপনি কত টাকা উইথড্র করতে চান?\n\n"
        f"আপনার ব্যালেন্স: <b>{_fmt(balance)} BDT</b>\n"
        f"সর্বনিম্ন লিমিট: <b>{_fmt(min_withdraw)} BDT</b>\n\n"
        "টাকার পরিমাণ সংখ্যায় লিখে পাঠান:",
        reply_markup=get_cancel_keyboard(),
    )


# --- Step 3: amount ---------------------------------------------------------
@withdraw_router.message(WithdrawStates.waiting_for_amount, F.text)
async def handle_wd_amount(message: Message, state: FSMContext):
    try:
        amount = round(float(message.text.strip().replace(",", "")), 2)
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ দয়া করে সঠিক সংখ্যায় পরিমাণ লিখুন।", reply_markup=get_cancel_keyboard())
        return

    user_id = message.from_user.id
    balance, min_withdraw = await _live_limits(user_id)

    if amount < min_withdraw:
        await message.answer(
            f"⚠️ সর্বনিম্ন উইথড্রো <b>{_fmt(min_withdraw)} BDT</b>। এর কম উইথড্রো করা যাবে না।",
            reply_markup=get_cancel_keyboard(),
        )
        return
    if amount > balance:
        await message.answer(
            f"⚠️ আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই। বর্তমান ব্যালেন্স: <b>{_fmt(balance)} BDT</b>",
            reply_markup=get_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    key = data.get("withdraw_method")
    account_no = data.get("withdraw_account")
    if key not in METHODS or not account_no:
        await state.clear()
        await message.answer("⚠️ সেশন মেয়াদোত্তীর্ণ। আবার <b>Withdraw</b> চাপুন।", reply_markup=get_main_keyboard())
        return

    # Clear first so a double-tap cannot submit twice.
    await state.clear()
    status, req = await db.create_withdrawal(user_id, amount, METHODS[key], account_no)

    if status == "ok":
        await message.answer(
            "✅ <b>উইথড্রো রিকোয়েস্ট সফলভাবে জমা হয়েছে!</b>\n\n"
            f"💰 পরিমাণ: <b>{_fmt(amount)} BDT</b>\n"
            f"💳 মাধ্যম: <b>{METHODS[key]}</b>\n"
            f"📱 অ্যাকাউন্ট: <code>{html.escape(account_no)}</code>\n\n"
            "⏳ এডমিন যাচাই করে ২৪ ঘণ্টার মধ্যে পেমেন্ট পাঠিয়ে দেবেন।",
            reply_markup=get_main_keyboard(),
        )
        if req:
            await notify_admins_new_withdrawal(message.bot, req)
    elif status == "below_min":
        new_min = await db.get_float_setting("min_withdraw", 50.0)
        await message.answer(
            f"⚠️ সর্বনিম্ন উইথড্রো লিমিট পরিবর্তিত হয়ে <b>{_fmt(new_min)} BDT</b> হয়েছে।",
            reply_markup=get_main_keyboard(),
        )
    elif status == "insufficient":
        await message.answer("⚠️ আপনার অ্যাকাউন্টে পর্যাপ্ত ব্যালেন্স নেই।", reply_markup=get_main_keyboard())
    else:
        await message.answer(
            "⚠️ উইথড্রো রিকোয়েস্ট সাবমিট করতে সমস্যা হয়েছে। আপনার ব্যালেন্স কাটা হয়নি, আবার চেষ্টা করুন।",
            reply_markup=get_main_keyboard(),
        )


# --- Cancel (inline) --------------------------------------------------------
@withdraw_router.callback_query(F.data == "wd_cancel")
async def handle_wd_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback.message, "❌ উইথড্রো প্রক্রিয়া বাতিল করা হয়েছে।")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()
