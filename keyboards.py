from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def get_reply_main_menu() -> ReplyKeyboardMarkup:
    """বোটের চ্যাট বক্সের নিচের স্থায়ী প্রফেশনাল মেনু"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Register a new Gmail")],
            [KeyboardButton(text="💰 My Balance"), KeyboardButton(text="👥 Referrals")],
            [KeyboardButton(text="📦 My Accounts"), KeyboardButton(text="⚙️ Help")]
        ],
        resize_keyboard=True
    )

def get_task_action_keyboard() -> InlineKeyboardMarkup:
    """টাস্কের নিচে Done এবং Cancel বাটন"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Done", callback_data="task_done"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="task_cancel")
            ],
            [
                InlineKeyboardButton(text="🔙 মূল মেনুতে ফিরে যান", callback_data="main_menu")
            ]
        ]
    )

def get_back_button() -> InlineKeyboardMarkup:
    """সাধারণ ব্যাক বাটন"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 মূল মেনুতে ফিরে যান", callback_data="main_menu")]
        ]
    )
