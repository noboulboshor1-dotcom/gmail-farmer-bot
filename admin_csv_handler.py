"""
Admin CSV Handler for bulk operations
Handles CSV uploads for earnings/referral updates and downloads of reports
"""

import io
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Document, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database_enhanced import db
from csv_processor import (
    CSVProcessor,
    safe_import_earnings_updates,
    safe_import_referral_commissions,
)

logger = logging.getLogger(__name__)

admin_csv_router = Router(name="admin_csv")


class AdminCSVStates(StatesGroup):
    """FSM states for CSV operations."""
    waiting_for_earnings_csv = State()
    waiting_for_referral_csv = State()
    confirming_import = State()


def get_csv_operations_keyboard() -> InlineKeyboardMarkup:
    """Get CSV operations menu keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📥 আর্নিং আপডেট আপলোড করুন",
            callback_data="csv_upload_earnings"
        )],
        [InlineKeyboardButton(
            text="📥 রেফারেল কমিশন আপলোড করুন",
            callback_data="csv_upload_referral"
        )],
        [InlineKeyboardButton(
            text="📤 পেন্ডিং সাবমিশন ডাউনলোড করুন",
            callback_data="csv_download_submissions"
        )],
        [InlineKeyboardButton(
            text="📤 ইউজার আর্নিং রিপোর্ট ডাউনলোড করুন",
            callback_data="csv_download_earnings_report"
        )],
        [InlineKeyboardButton(
            text="📝 নমুনা CSV ডাউনলোড করুন",
            callback_data="csv_download_sample"
        )],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="admin_back")],
    ])


# ================================================================
# UPLOAD HANDLERS
# ================================================================

@admin_csv_router.callback_query(F.data == "csv_upload_earnings")
async def handle_earnings_upload_request(callback: CallbackQuery, state: FSMContext):
    """Request earnings CSV upload."""
    await state.set_state(AdminCSVStates.waiting_for_earnings_csv)
    
    text = (
        "📥 <b>আর্নিং আপডেট CSV আপলোড করুন</b>\n\n"
        "<b>CSV ফর্ম্যাট (হেডার সহ):</b>\n"
        "<code>user_id,amount,reason\n"
        "12345,100.50,completed_task_batch_1\n"
        "67890,-50.00,balance_correction</code>\n\n"
        "ফাইল সংযুক্ত করুন বা সাবমিট করুন।"
    )
    
    try:
        await callback.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="admin_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error requesting earnings upload: {e}")
        await callback.answer("⚠️ শুরু করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@admin_csv_router.message(AdminCSVStates.waiting_for_earnings_csv)
async def handle_earnings_csv_file(message: Message, state: FSMContext):
    """Process earnings CSV file."""
    if not message.document:
        await message.answer("❌ কোন ফাইল সংযুক্ত করা হয়নি। CSV ফাইল সংযুক্ত করুন।")
        return
    
    if not message.document.file_name.lower().endswith(".csv"):
        await message.answer("❌ শুধুমাত্র CSV ফাইল গ্রহণযোগ্য।")
        return
    
    if message.document.file_size > 5 * 1024 * 1024:  # 5MB limit
        await message.answer("❌ ফাইল খুব বড় (সর্বোচ্চ 5MB)।")
        return
    
    # Download and read file
    try:
        file = await message.bot.get_file(message.document.file_id)
        file_content = await message.bot.download_file(file.file_path)
        csv_text = file_content.read().decode('utf-8')
    except Exception as e:
        logger.exception(f"Error downloading CSV: {e}")
        await message.answer("❌ ফাইল ডাউনলোড করতে ত্রুটি।")
        return
    
    # Validate CSV
    is_valid, validation_msg = CSVProcessor.validate_csv_structure(
        csv_text,
        CSVProcessor.EARNINGS_UPDATE_HEADERS,
    )
    
    if not is_valid:
        await message.answer(f"❌ {validation_msg}")
        return
    
    # Store in context for confirmation
    await state.update_data(csv_content=csv_text, csv_type="earnings")
    
    # Show preview
    from csv_processor import CSVProcessor as CP
    updates, errors = CP.parse_earnings_update_csv(csv_text)
    
    preview_text = (
        f"✅ <b>CSV বৈধ</b>\n\n"
        f"<b>প্রক্রিয়া করার জন্য প্রস্তুত:</b>\n"
        f"• মোট রো: {len(updates)}\n"
        f"• সম্ভাব্য ত্রুটি: {len(errors)}\n\n"
    )
    
    if errors[:5]:  # Show first 5 errors
        preview_text += "<b>সতর্কতা:</b>\n"
        for err in errors[:5]:
            preview_text += f"  • {err}\n"
        if len(errors) > 5:
            preview_text += f"  ... এবং {len(errors) - 5} আরও\n"
    
    preview_text += "\n<b>আপনি নিশ্চিত?</b>"
    
    await state.set_state(AdminCSVStates.confirming_import)
    await message.answer(
        preview_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ নিশ্চিত করুন", callback_data="csv_confirm_import")],
            [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="csv_cancel_import")],
        ])
    )


@admin_csv_router.callback_query(F.data == "csv_confirm_import")
async def handle_csv_confirm_import(callback: CallbackQuery, state: FSMContext):
    """Confirm and apply CSV import."""
    data = await state.get_data()
    csv_content = data.get("csv_content", "")
    csv_type = data.get("csv_type", "")
    
    if not csv_content or not csv_type:
        await callback.answer("❌ সেশন এক্সপায়ার। পুনরায় চেষ্টা করুন।", show_alert=True)
        await state.clear()
        return
    
    # Process based on type
    if csv_type == "earnings":
        result = await safe_import_earnings_updates(db, csv_content)
    elif csv_type == "referral":
        result = await safe_import_referral_commissions(db, csv_content)
    else:
        await callback.answer("❌ অজানা CSV প্রকার।", show_alert=True)
        await state.clear()
        return
    
    # Show result
    result_text = (
        f"<b>📊 আমদানি ফলাফল</b>\n\n"
        f"✅ সফল: {result.processed_rows}\n"
        f"❌ ব্যর্থ: {result.skipped_rows}\n"
        f"📝 মোট: {result.total_rows}\n\n"
    )
    
    if result.errors:
        result_text += "<b>সতর্কতা/ত্রুটি:</b>\n"
        for err in result.errors[:10]:  # Show first 10
            result_text += f"  • {err}\n"
        if len(result.errors) > 10:
            result_text += f"  ... এবং {len(result.errors) - 10} আরও\n"
    
    await state.clear()
    
    try:
        await callback.message.edit_text(
            text=result_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="admin_back")],
            ])
        )
    except Exception as e:
        logger.exception(f"Error showing import result: {e}")
        await callback.answer("⚠️ ফলাফল দেখাতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@admin_csv_router.callback_query(F.data == "csv_cancel_import")
async def handle_csv_cancel_import(callback: CallbackQuery, state: FSMContext):
    """Cancel CSV import."""
    await state.clear()
    
    try:
        await callback.message.edit_text(
            text="❌ আমদানি বাতিল করা হয়েছে।",
            reply_markup=get_csv_operations_keyboard()
        )
    except Exception as e:
        logger.exception(f"Error canceling import: {e}")
        await callback.answer("⚠️ বাতিল করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


# ================================================================
# DOWNLOAD HANDLERS
# ================================================================

@admin_csv_router.callback_query(F.data == "csv_download_submissions")
async def handle_download_submissions(callback: CallbackQuery):
    """Download pending submissions as CSV."""
    try:
        submissions = await db.get_pending_submissions_for_csv(limit=10000)
        
        if not submissions:
            await callback.answer("ℹ️ কোন পেন্ডিং সাবমিশন নেই।", show_alert=True)
            return
        
        csv_content = CSVProcessor.export_pending_submissions_csv(submissions)
        filename, csv_bytes = CSVProcessor.generate_csv_file(
            CSVProcessor.PENDING_SUBMISSIONS_HEADERS,
            submissions,
            "pending_submissions"
        )
        
        file = BufferedInputFile(file=csv_bytes, filename=filename)
        await callback.message.answer_document(
            document=file,
            caption=f"📥 {filename}\n\n{len(submissions)} টি সাবমিশন।"
        )
        
    except Exception as e:
        logger.exception(f"Error downloading submissions: {e}")
        await callback.answer("❌ ডাউনলোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@admin_csv_router.callback_query(F.data == "csv_download_earnings_report")
async def handle_download_earnings_report(callback: CallbackQuery):
    """Download user earnings report as CSV."""
    try:
        users, total = await db.get_users_paginated(page=1, limit=100000)
        
        if not users:
            await callback.answer("ℹ️ কোন ব্যবহারকারী নেই।", show_alert=True)
            return
        
        filename, csv_bytes = CSVProcessor.generate_csv_file(
            CSVProcessor.USER_EARNINGS_REPORT_HEADERS,
            users,
            "user_earnings_report"
        )
        
        file = BufferedInputFile(file=csv_bytes, filename=filename)
        await callback.message.answer_document(
            document=file,
            caption=f"📤 {filename}\n\n{len(users)} জন ব্যবহারকারী।"
        )
        
    except Exception as e:
        logger.exception(f"Error downloading earnings report: {e}")
        await callback.answer("❌ ডাউনলোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()


@admin_csv_router.callback_query(F.data == "csv_download_sample")
async def handle_download_sample_csv(callback: CallbackQuery):
    """Download sample CSV templates."""
    try:
        sample_earnings = [
            {"user_id": "12345", "amount": "100.50", "reason": "completed_task_batch_1"},
            {"user_id": "67890", "amount": "-50.00", "reason": "balance_correction"},
        ]
        
        filename, csv_bytes = CSVProcessor.generate_csv_file(
            CSVProcessor.EARNINGS_UPDATE_HEADERS,
            sample_earnings,
            "sample_earnings_update"
        )
        
        file = BufferedInputFile(file=csv_bytes, filename=filename)
        await callback.message.answer_document(
            document=file,
            caption="📝 আর্নিং আপডেট CSV নমুনা\n\nএই ফর্ম্যাটে আপনার CSV তৈরি করুন।"
        )
        
    except Exception as e:
        logger.exception(f"Error downloading sample CSV: {e}")
        await callback.answer("❌ ডাউনলোড করতে ত্রুটি।", show_alert=True)
        return
    
    await callback.answer()
