from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove


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


# ========== НОВЫЕ КЛАВИАТУРЫ ДЛЯ РЕГИСТРАЦИИ ==========

def get_registration_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для начала регистрации"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📱 Поделиться номером телефона", request_contact=True)
            ],
            [
                KeyboardButton(text="❌ Отмена")
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Нажмите кнопку для регистрации"
    )
    return keyboard


def get_registration_confirmation_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения регистрации"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, это правильно",
                callback_data="confirm_registration"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Нет, попробовать снова", 
                callback_data="retry_registration"
            )
        ]
    ])
    return keyboard


def remove_keyboard() -> ReplyKeyboardRemove:
    """Убрать клавиатуру"""
    return ReplyKeyboardRemove()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Основное меню для зарегистрированных пользователей"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="ℹ️ Справка",
                callback_data="help"
            ),
            InlineKeyboardButton(
                text="📞 Поддержка",
                callback_data="support"
            )
        ]
    ])
    return keyboard
