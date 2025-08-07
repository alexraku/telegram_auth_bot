from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_auth_keyboard(request_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для подтверждения авторизации"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, разрешаю",
                callback_data=f"auth_approve:{request_id}"
            ),
            InlineKeyboardButton(
                text="❌ Нет, отклоняю", 
                callback_data=f"auth_reject:{request_id}"
            )
        ]
    ])
    return keyboard


def get_auth_result_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру после обработки авторизации"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="main_menu"
            )
        ]
    ])
    return keyboard
