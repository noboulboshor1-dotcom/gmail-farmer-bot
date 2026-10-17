from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📥 নতুন জিমেইল টাস্ক", callback_data="get_task")
    builder.button(text="💰 আমার ব্যালেন্স", callback_data="my_balance")
    builder.button(text="📊 ফার্মিং স্ট্যাটাস", callback_data="my_stats")
    builder.button(text="⚙️ সাহায্য ও নিয়মাবলী", callback_data="help_info")
    builder.adjust(1) # প্রতি লাইনে ১টি করে বাটন
    return builder.as_markup()

def get_back_button():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 মূল মেনুতে ফিরে যান", callback_data="main_menu")
    return builder.as_markup()
