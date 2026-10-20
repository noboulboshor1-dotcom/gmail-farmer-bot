"""
Enhanced Keyboard Layouts
Includes profile, gift codes, CSV operations, and all user/admin keyboards
"""

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

# ================================================================
# MAIN USER MENU BUTTONS
# ================================================================

BTN_TASKS = "📝 টাস্ক করুন"
BTN_BONUS = "🎁 ডেইলি বোনাস"
BTN_BALANCE = "💰 আমার ব্যালেন্স"
BTN_REFERRALS = "👥 রেফারেল"
BTN_PROFILE = "👤 আমার প্রোফাইল"
BTN_GIFTS = "🎁 গিফট কোড"
BTN_SUPPORT = "💬 সাপোর্ট"
BTN_CANCEL = "❌ বাতিল করুন"

# Menu button set
MENU_BUTTONS = {BTN_TASKS, BTN_BONUS, BTN_BALANCE, BTN_REFERRALS, BTN_PROFILE, BTN_GIFTS, BTN_SUPPORT, BTN_CANCEL}


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Main user menu keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_TASKS), KeyboardButton(text=BTN_BONUS)],
            [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_REFERRALS)],
            [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_GIFTS)],
            [KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard with cancel button."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ================================================================
# INLINE KEYBOARDS - UTILITIES
# ================================================================

async def safe_edit(message, text: str, kb: InlineKeyboardMarkup):
    """
    Safely edit message with fallback to new message.
    Prevents errors when content hasn't changed or message is deleted.
    """
    try:
        await message.edit_text(text=text, reply_markup=kb)
    except Exception as e:
        # If edit fails, send new message
        try:
            await message.answer(text, reply_markup=kb)
        except Exception as inner_e:
            # Last resort: log error
            print(f"Error editing/sending message: {e} -> {inner_e}")


# ================================================================
# TASK SUBMISSION KEYBOARDS
# ================================================================

def get_task_submission_keyboard(task_id: str) -> InlineKeyboardMarkup:
    """Keyboard for task submission options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ সম্পন্ন করুন", callback_data=f"submit_task_{task_id}")],
        [InlineKeyboardButton(text="⏭️ পরবর্তী টাস্ক", callback_data="skip_task")],
        [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="cancel_task")],
    ])


def get_task_verification_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    """Keyboard for task verification (admin)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ অনুমোদন করুন", callback_data=f"verify_approve_{submission_id}")],
        [InlineKeyboardButton(text="❌ প্রত্যাখ্যান করুন", callback_data=f"verify_reject_{submission_id}")],
    ])


# ================================================================
# SUBMISSION STATUS KEYBOARDS
# ================================================================

def get_submission_status_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for checking submission status."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 স্ট্যাটাস দেখুন", callback_data="check_submission_status")],
        [InlineKeyboardButton(text="🔄 নতুন টাস্ক", callback_data="get_new_task")],
        [InlineKeyboardButton(text="🔙 মূল মেনু", callback_data="menu_main")],
    ])


def get_task_feedback_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    """Keyboard for providing feedback on rejected task."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 প্রতিক্রিয়া দেখুন", callback_data=f"view_feedback_{submission_id}")],
        [InlineKeyboardButton(text="🔄 পুনরায় চেষ্টা করুন", callback_data=f"retry_task_{submission_id}")],
        [InlineKeyboardButton(text="⏭️ পরবর্তী টাস্ক", callback_data="get_new_task")],
    ])


# ================================================================
# WITHDRAWAL KEYBOARDS
# ================================================================

def withdrawal_review_kb(withdrawal_id: str) -> InlineKeyboardMarkup:
    """Keyboard for withdrawal request review (admin)."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ অনুমোদন করুন", callback_data=f"withdraw_approve_{withdrawal_id}")],
        [InlineKeyboardButton(text="❌ প্রত্যাখ্যান করুন", callback_data=f"withdraw_reject_{withdrawal_id}")],
    ])


def get_withdrawal_method_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting withdrawal method."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 বিকাশ", callback_data="withdraw_bkash")],
        [InlineKeyboardButton(text="📱 নগদ", callback_data="withdraw_nagad")],
        [InlineKeyboardButton(text="🏪 রকেট", callback_data="withdraw_rocket")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="withdraw_back")],
    ])


# ================================================================
# BROADCAST KEYBOARDS (ADMIN)
# ================================================================

def get_broadcast_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for selecting broadcast message type."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 শুধু টেক্সট", callback_data="broadcast_type_text")],
        [InlineKeyboardButton(text="🖼️ ফটো + টেক্সট", callback_data="broadcast_type_photo")],
        [InlineKeyboardButton(text="🎥 ভিডিও + টেক্সট", callback_data="broadcast_type_video")],
        [InlineKeyboardButton(text="📄 ডকুমেন্ট", callback_data="broadcast_type_document")],
        [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="broadcast_cancel")],
    ])


def get_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for confirming broadcast message."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ পাঠান", callback_data="broadcast_confirm_send")],
        [InlineKeyboardButton(text="❌ বাতিল করুন", callback_data="broadcast_cancel")],
    ])


# ================================================================
# ADMIN BROADCAST KEYBOARD
# ================================================================

def admin_broadcast_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for admin broadcast options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 নতুন বার্তা", callback_data="broadcast_create")],
        [InlineKeyboardButton(text="📊 সম্প্রচার ইতিহাস", callback_data="broadcast_history")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="admin_back")],
    ])


# ================================================================
# PAGINATION KEYBOARDS
# ================================================================

def get_pagination_keyboard(page: int, total_pages: int, callback_prefix: str = "page") -> InlineKeyboardMarkup:
    """Generate pagination keyboard."""
    buttons = []
    
    # Previous button
    if page > 1:
        buttons.append(InlineKeyboardButton(
            text="◀️ আগে",
            callback_data=f"{callback_prefix}_{page - 1}"
        ))
    
    # Current page info
    buttons.append(InlineKeyboardButton(
        text=f"{page}/{total_pages}",
        callback_data="noop"
    ))
    
    # Next button
    if page < total_pages:
        buttons.append(InlineKeyboardButton(
            text="পরে ▶️",
            callback_data=f"{callback_prefix}_{page + 1}"
        ))
    
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# ================================================================
# CONFIRMATION KEYBOARDS
# ================================================================

def get_confirmation_keyboard(yes_callback: str, no_callback: str = "cancel") -> InlineKeyboardMarkup:
    """Generic confirmation keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ হ্যাঁ", callback_data=yes_callback),
            InlineKeyboardButton(text="❌ না", callback_data=no_callback),
        ],
    ])


def get_yes_no_keyboard() -> InlineKeyboardMarkup:
    """Simple yes/no keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ হ্যাঁ", callback_data="choice_yes"),
            InlineKeyboardButton(text="❌ না", callback_data="choice_no"),
        ],
    ])


# ================================================================
# CATEGORY SELECTION KEYBOARDS
# ================================================================

def get_category_selection_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    """Keyboard for selecting task category."""
    buttons = []
    for cat in categories:
        if cat.get("is_enabled", False):
            buttons.append([InlineKeyboardButton(
                text=f"{cat.get('category_name', 'Unknown')} ({cat.get('task_count', 0)} টি)",
                callback_data=f"select_cat_{cat['category_key']}"
            )])
    
    buttons.append([InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="menu_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ================================================================
# USER LIST KEYBOARDS (ADMIN)
# ================================================================

def admin_user_list_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Keyboard for admin user list navigation."""
    buttons = []
    
    if page > 1:
        buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_users_page_{page - 1}"))
    
    buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_users_page_{page + 1}"))
    
    return InlineKeyboardMarkup(inline_keyboard=[
        buttons,
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="admin_back")],
    ])


def admin_user_action_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Keyboard for admin actions on a user."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 ম্যানুয়াল পেমেন্ট", callback_data=f"admin_user_payment_{user_id}")],
        [InlineKeyboardButton(text="🚫 ব্যান করুন", callback_data=f"admin_user_ban_{user_id}")],
        [InlineKeyboardButton(text="🔓 আনব্যান করুন", callback_data=f"admin_user_unban_{user_id}")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="admin_back")],
    ])


# ================================================================
# HELPTEXT KEYBOARDS
# ================================================================

def get_help_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for help options."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❓ FAQ দেখুন", callback_data="help_faq")],
        [InlineKeyboardButton(text="📞 সাপোর্ট যোগাযোগ করুন", callback_data="help_contact")],
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data="menu_main")],
    ])


# ================================================================
# BACK BUTTON KEYBOARD
# ================================================================

def get_back_keyboard(callback_data: str = "menu_main") -> InlineKeyboardMarkup:
    """Simple back button keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 ফিরে যান", callback_data=callback_data)],
    ])


# ================================================================
# FORMAT HELPERS
# ================================================================

def _fmt(x) -> str:
    """Format float to 2 decimal places."""
    return f"{float(x):.2f}"


def _mask_id(user_id: int) -> str:
    """Mask user ID for privacy."""
    s = str(user_id)
    return f"{s[:3]}•••{s[-2:]}" if len(s) > 5 else s


# ================================================================
# EXPORT UTILITIES
# ================================================================

__all__ = [
    # Buttons
    "BTN_TASKS",
    "BTN_BONUS",
    "BTN_BALANCE",
    "BTN_REFERRALS",
    "BTN_PROFILE",
    "BTN_GIFTS",
    "BTN_SUPPORT",
    "BTN_CANCEL",
    "MENU_BUTTONS",
    # Functions
    "get_main_keyboard",
    "get_cancel_keyboard",
    "safe_edit",
    "get_task_submission_keyboard",
    "get_task_verification_keyboard",
    "get_submission_status_keyboard",
    "get_task_feedback_keyboard",
    "withdrawal_review_kb",
    "get_withdrawal_method_keyboard",
    "get_broadcast_type_keyboard",
    "get_broadcast_confirm_keyboard",
    "admin_broadcast_keyboard",
    "get_pagination_keyboard",
    "get_confirmation_keyboard",
    "get_yes_no_keyboard",
    "get_category_selection_keyboard",
    "admin_user_list_keyboard",
    "admin_user_action_keyboard",
    "get_help_keyboard",
    "get_back_keyboard",
    "_fmt",
    "_mask_id",
]
