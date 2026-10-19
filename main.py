import asyncio
import contextlib
import html
import logging
import signal
import time
from urllib.parse import quote

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramConflictError, TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, ErrorEvent, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiohttp import web

from admin import admin_router
from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    FB_FIRST_NAME,
    FB_LAST_NAME,
    FB_PASSWORD,
    LOCK_RENEW_SECONDS,
    LOCK_RETRY_SECONDS,
    LOCK_TTL,
    PORT,
    SUPPORT_USERNAME,
    TASK_STALE_MINUTES,
)
from database import db
from keyboards import (
    BTN_BALANCE,
    BTN_BONUS,
    BTN_CANCEL,
    BTN_NEW,
    BTN_REFERRALS,
    BTN_SUPPORT,
    BTN_TASKS,
    MENU_BUTTONS,
    get_cancel_keyboard,
    get_main_keyboard,
    safe_edit,
)
from tasks import task_manager
from social_tasks import social_router
from verifier import API_ERROR, UNSUPPORTED, inbox_verifier
from withdraw import withdraw_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

router = Router(name="user")
_verifying: set[int] = set()          # users with a verification currently running


class TaskStates(StatesGroup):
    working_on_gmail = State()
    waiting_for_fb_uid = State()
    waiting_for_fb_cookies = State()
    waiting_for_insta_2fa = State()


def _fmt(x) -> str:
    return f"{float(x):.2f}"


# ----------------------------------------------------------------------------
# MIDDLEWARES (registered on the Dispatcher so they cover EVERY router)
# ----------------------------------------------------------------------------
class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user and user.id not in ADMIN_IDS and await db.is_banned(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 আপনার অ্যাকাউন্টটি ব্যান করা হয়েছে!", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("🚫 <b>আপনার অ্যাকাউন্টটি ব্যান করা হয়েছে!</b>")
            return None
        return await handler(event, data)


class MenuResetMiddleware(BaseMiddleware):
    """Pressing a main-menu button always aborts any half-finished flow, so menu
    labels can never be swallowed as 'account number', 'UID', etc."""

    async def __call__(self, handler, event: Message, data):
        if event.text in MENU_BUTTONS:
            state: FSMContext | None = data.get("state")
            if state is not None:
                await state.clear()
        return await handler(event, data)


# ----------------------------------------------------------------------------
# START / MENU
# ----------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name

    referred_by = None
    if command.args and command.args.strip().isdigit():
        ref_id = int(command.args.strip())
        if ref_id != user_id:
            referred_by = ref_id

    await db.get_or_create_user(user_id=user_id, username=username, referred_by=referred_by)

    await message.answer(
        f"🌟 <b>স্বাগতম, {html.escape(message.from_user.first_name)}!</b>\n\n"
        "🚀 <b>পেশাদার মাইক্রো-টাস্ক ও আর্নিং প্ল্যাটফর্মে আপনাকে স্বাগতম।</b>\n"
        "আমাদের এই অটোমেটেড সিস্টেমের মাধ্যমে আপনি খুব সহজেই বিভিন্ন টাস্ক সম্পন্ন করে প্রতিদিন নিশ্চিত আয় করতে পারবেন।\n\n"
        "📌 <b>মূল বৈশিষ্ট্যসমূহ:</b>\n"
        "▪️ দ্রুত ও অটোমেটেড জিমেইল ভেরিফিকেশন\n"
        "▪️ ইনস্ট্যান্ট ডেইলি বোনাস ও রেফারেল কমিশন\n"
        "▪️ নিরাপদ ও ঝামেলাহীন উইথড্রো সিস্টেম\n\n"
        "👇 কাজ শুরু করতে নিচের মেনু থেকে অপশন নির্বাচন করুন:",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == BTN_CANCEL)
async def handle_cancel_button(message: Message, state: FSMContext):
    await state.clear()                       # (MenuResetMiddleware already did, kept for safety)
    await db.release_user_task(message.from_user.id)
    await message.answer("❌ কাজ বাতিল করা হয়েছে।", reply_markup=get_main_keyboard())


@router.message(F.text == BTN_BONUS)
async def handle_daily_bonus(message: Message):
    _, msg, _ = await db.claim_daily_bonus(message.from_user.id)
    await message.answer(msg, reply_markup=get_main_keyboard())


@router.message(F.text == BTN_BALANCE)
async def handle_balance_btn(message: Message):
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    await message.answer(
        "💰 <b>আপনার ব্যালেন্স একাউন্ট ইনফো:</b>\n\n"
        f"🆔 ইউজার আইডি: <code>{user_id}</code>\n"
        f"💵 মূল ব্যালেন্স: <b>{_fmt(user.get('balance') or 0)} BDT</b>\n"
        f"✅ সফল টাস্ক সম্পন্ন: <b>{int(user.get('completed_tasks') or 0)} টি</b>",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == BTN_REFERRALS)
async def handle_referral(message: Message):
    user_id = message.from_user.id
    user = await db.get_or_create_user(user_id, message.from_user.username or "")
    me = await message.bot.me()
    ref_link = f"https://t.me/{me.username}?start={user_id}"
    pct = await db.get_float_setting("referral_commission", 10.0)

    share_url = f"https://t.me/share/url?url={quote(ref_link, safe='')}&text={quote('Join this amazing earning bot!')}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🌐 Share Now", url=share_url)]])
    await message.answer(
        "🎁 <b>My Referrals</b>\n"
        f"👥 Total Refer: <b>{int(user.get('referral_count') or 0)}</b>\n"
        f"💰 Total Refer Income: <b>{float(user.get('referral_income') or 0):.4f} BDT</b>\n"
        f"🔗 <b>Your Referral Link:</b>\n<code>{ref_link}</code>\n\n"
        f"ℹ️ You will receive <b>{pct:g}% commission</b> on earnings from each task completed by your referrals.",
        reply_markup=kb,
    )


@router.message(F.text == BTN_SUPPORT)
async def handle_support(message: Message):
    await message.answer(
        "🎧 <b>সাপোর্ট ও হেল্প সেন্টার</b>\n\n"
        "যেকোনো প্রয়োজনে আমাদের সাপোর্ট টিমের সাথে যোগাযোগ করুন:\n"
        f"👉 এডমিন সাপোর্ট: {html.escape(SUPPORT_USERNAME)}",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == BTN_NEW)
async def handle_iam_new(message: Message):
    await message.answer(
        "💡 <b>নতুনদের জন্য নির্দেশিকা:</b>\n\n"
        "১. <b>Tasks ▸</b> থেকে পছন্দের টাস্ক নিন।\n"
        "২. জিমেইল টাস্কে রিকভারি মেইল বসিয়ে অটোভেরিফাই করুন।\n"
        "৩. ফেসবুক ও ইনস্টাগ্রাম টাস্কে আইডি/2FA কী সাবমিট করুন।\n"
        "৪. প্রতিদিন <b>Daily Bonus</b> দাবি করুন!",
        reply_markup=get_main_keyboard(),
    )


# ----------------------------------------------------------------------------
# TASKS
# ----------------------------------------------------------------------------
@router.message(F.text == BTN_TASKS)
async def handle_tasks_menu(message: Message):
    rows = [
        [InlineKeyboardButton(text=cat["category_name"], callback_data=f"cat_task_{cat['category_key']}")]
        for cat in await db.get_categories() if cat.get("is_enabled")
    ]
    if not rows:
        await message.answer("⚠️ বর্তমানে সকল টাস্ক ক্যাটাগরি সাময়িকভাবে বন্ধ রয়েছে।", reply_markup=get_main_keyboard())
        return
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_task")])
    await message.answer("🎯 <b>কাজের ক্যাটাগরি নির্বাচন করুন:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


def _gmail_task_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Verify Task", callback_data="verify_task")],
        [InlineKeyboardButton(text="❌ Cancel Task", callback_data="cancel_task")],
    ])


def _gmail_task_text(task: dict) -> str:
    first, last = task_manager.display_names(task)
    return (
        "✏️ <b>নিচে দেওয়া তথ্য দিয়ে জিমেইল একাউন্ট তৈরি করুন:</b>\n\n"
        f"👤 <b>First Name:</b> <code>{html.escape(first)}</code>\n"
        f"👤 <b>Last Name:</b> <code>{html.escape(last)}</code>\n"
        f"📧 <b>Email:</b> <code>{html.escape(task['email'])}</code>\n"
        f"🔑 <b>Password:</b> <code>{html.escape(task['password'])}</code>\n\n"
        f"🛡️ <b>Recovery Email:</b>\n<code>{html.escape(task['recovery'])}</code>"
    )


@router.callback_query(F.data.startswith("cat_task_"))
async def handle_category_selection(callback: CallbackQuery, state: FSMContext):
    cat_key = callback.data.removeprefix("cat_task_")

    if not await db.is_category_enabled(cat_key):          # honour live admin toggles
        await callback.answer("⚠️ এই ক্যাটাগরির কাজ বর্তমানে বন্ধ আছে।", show_alert=True)
        return

    if cat_key == "gmail":
        task = await db.claim_task(callback.from_user.id, fallback_task=task_manager.generate_random_gmail())
        if not task:
            await callback.answer("⚠️ টাস্ক লোড করতে সমস্যা হয়েছে। একটু পরে চেষ্টা করুন।", show_alert=True)
            return
        await state.set_state(TaskStates.working_on_gmail)
        await safe_edit(callback.message, _gmail_task_text(task), _gmail_task_kb())
        await callback.message.answer("⚠️ সঠিকভাবে কাজটি সম্পাদন করুন!", reply_markup=get_cancel_keyboard())

    elif cat_key == "facebook":
        await state.set_state(TaskStates.waiting_for_fb_uid)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Send UID", callback_data="prompt_fb_uid")]])
        await safe_edit(
            callback.message,
            f"👤 <b>First name:</b> {html.escape(FB_FIRST_NAME)}\n"
            f"👤 <b>Last name:</b> {html.escape(FB_LAST_NAME)}\n"
            f"🔑 <b>Password:</b> {html.escape(FB_PASSWORD)}\n\n"
            "📘 Create an account with the information above and click <b>Send UID</b> below:",
            kb,
        )
        await callback.message.answer("⚠️ ইউআইডি টাইপ করে পাঠাতে পারেন অথবা নিচে ক্যানসেল করতে পারেন:", reply_markup=get_cancel_keyboard())

    elif cat_key == "instagram":
        await state.set_state(TaskStates.waiting_for_insta_2fa)
        await safe_edit(callback.message, "🔑 <b>Enter 2FA Key:</b> ⤵️")
        await callback.message.answer("⚠️ আপনার 2FA Key পেস্ট করে সেন্ড করুন:", reply_markup=get_cancel_keyboard())

    else:
        await callback.answer("⚠️ এই ক্যাটাগরির কাজ বর্তমানে স্টকে নেই।", show_alert=True)
        return
    await callback.answer()


@router.callback_query(F.data == "cancel_task")
async def handle_cancel_task(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await db.release_user_task(callback.from_user.id)
    await safe_edit(callback.message, "❌ টাস্কটি বাতিল করা হয়েছে।")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()


# --- Gmail verification ------------------------------------------------------
@router.callback_query(F.data == "verify_task")
async def handle_verify_task(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id in _verifying:
        await callback.answer("⏳ ভেরিফিকেশন চলছে, অপেক্ষা করুন...")
        return
    _verifying.add(user_id)
    try:
        # The DB is the source of truth, so this still works after a redeploy wiped the FSM.
        task = await db.get_user_assigned_task(user_id)
        if not task:
            await state.clear()
            await callback.answer("⚠️ টাস্কটির মেয়াদ শেষ হয়ে গেছে। নতুন টাস্ক নিন।", show_alert=True)
            await safe_edit(callback.message, "⚠️ টাস্কটির মেয়াদ শেষ হয়ে গেছে।")
            await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
            return

        await callback.answer()
        await safe_edit(callback.message, "🔍 ইনবক্স চেক করা হচ্ছে... দয়া করে অপেক্ষা করুন ⏳")
        verified, code = await inbox_verifier.check_inbox(task["recovery"], task["email"])

        if not verified:
            if code == UNSUPPORTED:
                reason = "⚠️ এই টাস্কের রিকভারি মেইল অটো-ভেরিফাই সাপোর্ট করে না। সাপোর্টে যোগাযোগ করুন অথবা টাস্ক বাতিল করুন।"
            elif code == API_ERROR:
                reason = "⚠️ ইনবক্স সার্ভিসে সাময়িক সমস্যা হচ্ছে। কিছুক্ষণ পর আবার চেষ্টা করুন।"
            else:
                reason = "গুগল থেকে রিকভারি মেইলে কনফার্মেশন মেসেজ আসেনি। আবার চেষ্টা করুন:"
            await safe_edit(callback.message, _gmail_task_text(task) + f"\n\n❌ <b>ভেরিফিকেশন ব্যর্থ!</b>\n{reason}", _gmail_task_kb())
            return

        result = await db.complete_task(task["id"], user_id)
        await state.clear()
        if not result:
            await safe_edit(callback.message, "⚠️ টাস্ক কমপ্লিট করতে সমস্যা হয়েছে। আবার চেষ্টা করুন বা সাপোর্টে জানান।")
            await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
            return

        await safe_edit(
            callback.message,
            "🎉 <b>অভিনন্দন! আপনার টাস্ক সফলভাবে ভেরিফাই হয়েছে।</b>\n\n"
            f"💰 ব্যালেন্সে যোগ হয়েছে: <b>+{result['reward']:g} BDT</b>",
        )
        await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())

        if result["referrer_id"] and result["commission"] > 0:
            try:
                await callback.bot.send_message(
                    result["referrer_id"],
                    f"🎁 আপনার রেফারেল টাস্ক সম্পন্ন করেছে! কমিশন: <b>+{result['commission']:.4f} BDT</b>",
                )
            except Exception as e:  # noqa: BLE001
                logger.info("Referrer %s not notified: %s", result["referrer_id"], e)
    finally:
        _verifying.discard(user_id)


# --- Facebook ----------------------------------------------------------------
@router.callback_query(F.data == "prompt_fb_uid")
async def handle_prompt_fb_uid(callback: CallbackQuery):
    await callback.message.answer("🏷️ <b>Enter your Facebook account 14-16 digit UID:</b>")
    await callback.answer()


@router.message(TaskStates.waiting_for_fb_uid, F.text)
async def process_fb_uid_submission(message: Message, state: FSMContext):
    uid_text = message.text.strip()
    if uid_text.isdigit() and 14 <= len(uid_text) <= 16:
        await state.update_data(fb_uid=uid_text)
        await state.set_state(TaskStates.waiting_for_fb_cookies)
        await message.answer("📘 <b>Now enter your Facebook account Cookies:</b>", reply_markup=get_cancel_keyboard())
    else:
        await message.answer("⚠️ সঠিক 14-16 ডিজিটের Facebook UID দিন।", reply_markup=get_cancel_keyboard())


@router.message(TaskStates.waiting_for_fb_cookies, F.text)
async def process_fb_cookies_submission(message: Message, state: FSMContext):
    cookies_text = message.text.strip()
    if len(cookies_text) <= 10:
        await message.answer("⚠️ <b>Invalid Cookies!</b> Please paste complete cookies.", reply_markup=get_cancel_keyboard())
        return

    fb_uid = (await state.get_data()).get("fb_uid")
    if not fb_uid:
        await state.clear()
        await message.answer("⚠️ সেশন মেয়াদোত্তীর্ণ। আবার Tasks থেকে শুরু করুন।", reply_markup=get_main_keyboard())
        return

    saved = await db.add_submission(message.from_user.id, "facebook", f"UID: {fb_uid} | Cookies: {cookies_text}")
    await state.clear()
    if saved:
        await message.answer(
            "✅ <b>Submitted successfully!</b>\n\n"
            "Your Facebook Account has been submitted to the buyer. Payment will be credited once verified.",
            reply_markup=get_main_keyboard(),
        )
    else:
        await message.answer("⚠️ সাবমিট করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।", reply_markup=get_main_keyboard())


# --- Instagram ---------------------------------------------------------------
def _insta_code_text(code: str, seconds_left: int) -> str:
    return (
        "Click the button below after opening account:\n"
        "Click the button below to copy the code ⤵️\n\n"
        f"📋 <code>{code}</code>\n"
        f"⏱ ~{seconds_left}s বাকি (শেষ হলে 🔄 চাপুন)"
    )


def _insta_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Refresh Code", callback_data="insta_refresh")],
        [InlineKeyboardButton(text="Account Created", callback_data="insta_created_confirm")],
    ])


@router.message(TaskStates.waiting_for_insta_2fa, F.text)
async def process_insta_2fa_submission(message: Message, state: FSMContext):
    secret = task_manager.normalize_secret(message.text)
    totp = task_manager.generate_totp(message.text) if secret else None
    if not secret or not totp:
        await message.answer("⚠️ সঠিক 2FA Key প্রদান করুন (Base32, অক্ষর A-Z ও সংখ্যা 2-7)।", reply_markup=get_cancel_keyboard())
        return

    await db.add_submission(message.from_user.id, "instagram", f"2FA Key: {secret}")
    await state.set_state(None)                      # leave the state but keep data for refresh
    await state.update_data(insta_secret=secret)
    code, left = totp
    await message.answer(_insta_code_text(code, left), reply_markup=_insta_kb())
    await message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())


@router.callback_query(F.data == "insta_refresh")
async def handle_insta_refresh(callback: CallbackQuery, state: FSMContext):
    secret = (await state.get_data()).get("insta_secret")
    totp = task_manager.generate_totp(secret) if secret else None
    if not totp:
        await callback.answer("⚠️ সেশন মেয়াদোত্তীর্ণ।", show_alert=True)
        return
    await safe_edit(callback.message, _insta_code_text(*totp), _insta_kb())
    await callback.answer()


@router.callback_query(F.data == "insta_created_confirm")
async def handle_insta_confirm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(callback.message, "⏳ <b>Payment will be processed within 2 to 72 hours.</b>")
    await callback.message.answer("প্রধান মেনু:", reply_markup=get_main_keyboard())
    await callback.answer()


# ----------------------------------------------------------------------------
# GLOBAL ERROR HANDLER
# ----------------------------------------------------------------------------
async def on_error(event: ErrorEvent) -> bool:
    logger.error("Unhandled error: %s", event.exception, exc_info=event.exception)
    update = event.update
    with contextlib.suppress(Exception):
        if update.callback_query:
            await update.callback_query.answer("⚠️ একটি সমস্যা হয়েছে, আবার চেষ্টা করুন।", show_alert=True)
        elif update.message:
            await update.message.answer("⚠️ একটি সমস্যা হয়েছে, আবার চেষ্টা করুন।")
    return True


# ----------------------------------------------------------------------------
# WEB SERVER (Render health check)
# ----------------------------------------------------------------------------
async def handle_web(_request: web.Request) -> web.Response:
    return web.Response(text="Super Premium Farmer Bot Live! 🚀")


async def start_web_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", handle_web)
    app.router.add_get("/healthz", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    logger.info("🌐 Server running on port %s", PORT)
    return runner


# ----------------------------------------------------------------------------
# SINGLE-INSTANCE POLLING (no TelegramConflictError on overlapping deploys)
# ----------------------------------------------------------------------------
def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.outer_middleware(BanMiddleware())
    dp.callback_query.outer_middleware(BanMiddleware())
    dp.message.outer_middleware(MenuResetMiddleware())
    dp.errors.register(on_error)
    dp.include_router(admin_router)
    dp.include_router(withdraw_router)
    dp.include_router(social_router)
    dp.include_router(router)
    return dp


async def leader_keeper(dp: Dispatcher, lost: asyncio.Event) -> None:
    """Renews the DB lease; stops polling if another instance took over."""
    last_ok = time.monotonic()
    while True:
        await asyncio.sleep(LOCK_RENEW_SECONDS)
        state = await db.renew_leader()
        now = time.monotonic()
        if state == "ok":
            last_ok = now
        elif state == "lost" or now - last_ok > LOCK_TTL - LOCK_RENEW_SECONDS:
            logger.error("Lost the polling lease (%s) - stopping polling.", state)
            lost.set()
            with contextlib.suppress(Exception):
                await dp.stop_polling()
            return


async def run_polling(bot: Bot, dp: Dispatcher, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        acquired = await db.acquire_leader()
        if acquired is False:
            logger.info("Another instance is polling - waiting for the lease...")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=LOCK_RETRY_SECONDS)
            continue

        lost = asyncio.Event()
        keeper = asyncio.create_task(leader_keeper(dp, lost)) if acquired else None
        try:
            await bot.delete_webhook(drop_pending_updates=False)
            logger.info("🚀 Starting bot polling...")
            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
                close_bot_session=False,
            )
        except TelegramConflictError:
            logger.error("TelegramConflictError: another poller/webhook is active. Retrying in 10s.")
            await asyncio.sleep(10)
            continue
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            continue
        except TelegramNetworkError as e:
            logger.error("Network error: %s. Retrying in 5s.", e)
            await asyncio.sleep(5)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("Polling crashed. Restarting in 5s.")
            await asyncio.sleep(5)
            continue
        finally:
            if keeper:
                keeper.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await keeper

        if not lost.is_set():
            break                                  # normal shutdown (SIGTERM / SIGINT)
        logger.warning("Lease lost - going back to the queue.")


async def main() -> None:
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError, RuntimeError):
            loop.add_signal_handler(sig, stop_event.set)

    runner = await start_web_server()        # open the port first so Render's health check passes
    try:
        await db.connect()
        logger.info("Abandoned Gmail tasks return to stock after %s min.", TASK_STALE_MINUTES)
        await run_polling(bot, dp, stop_event)
    finally:
        await db.release_leader()            # next instance can take over immediately
        await inbox_verifier.close()
        await bot.session.close()
        await runner.cleanup()
        logger.info("Bot stopped cleanly.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped!")
