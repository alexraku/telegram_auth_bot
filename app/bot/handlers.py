import hashlib
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Update, Contact
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.bot.keyboards import (
    get_auth_keyboard, 
    get_auth_result_keyboard,
    get_registration_keyboard,
    get_registration_confirmation_keyboard,
    remove_keyboard,
    get_main_menu_keyboard,
)
from app.services.redis_service import redis_service
from app.services.auth_service import auth_service
from app.database.database import get_db


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    telegram_id = user.id
    
    # Проверяем, зарегистрирован ли пользователь
    is_registered = await auth_service.is_user_registered(telegram_id)
    
    if is_registered:
        # Пользователь уже зарегистрирован
        welcome_text = f"""
🔐 **Добро пожаловать в систему авторизации!**

Привет, {user.first_name}! Вы уже зарегистрированы в системе.

Теперь вы будете получать уведомления для подтверждения операций.

*Ваш Telegram ID:* `{user.id}`
"""
        await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())
        
    else:
        # Пользователь не зарегистрирован - предлагаем регистрацию
        registration_text = f"""
🔐 **Добро пожаловать в систему авторизации!**

Привет, {user.first_name}! 

Для использования системы подтверждения операций необходимо пройти регистрацию.

📱 **Шаг 1:** Поделитесь номером телефона
Мы проверим, есть ли вы в базе наших клиентов и свяжем ваш аккаунт Telegram с профилем клиента.

🔒 **Безопасность:** Ваш номер телефона используется только для проверки и не передается третьим лицам.

Нажмите кнопку ниже для начала регистрации:
"""
        await message.answer(registration_text, reply_markup=get_registration_keyboard())


@router.message(F.text == "❌ Отмена")
async def cancel_registration(message: Message):
    """Отмена регистрации"""
    await message.answer(
        "❌ Регистрация отменена.\n\n"
        "Для использования системы авторизации необходимо пройти регистрацию.\n"
        "Используйте команду /start для повторной попытки.",
        reply_markup=remove_keyboard()
    )


@router.message(F.contact)
async def handle_contact(message: Message):
    """Обработчик получения контакта"""
    contact: Contact = message.contact
    user = message.from_user
    
    # Проверяем, что пользователь поделился своим контактом
    if contact.user_id != user.id:
        await message.answer(
            "❌ **Ошибка!**\n\n"
            "Пожалуйста, поделитесь именно своим номером телефона, "
            "а не контактом другого человека.",
            reply_markup=get_registration_keyboard()
        )
        return
    
    phone_number = contact.phone_number
    
    # Убираем клавиатуру
    await message.answer("🔍 **Проверяем ваш номер телефона...**", reply_markup=remove_keyboard())
    
    # Ищем клиента в базе
    client_info = await auth_service.get_client_by_phone(phone_number)
    
    if not client_info:
        # Клиент не найден в базе
        await message.answer(
            f"❌ **Номер телефона не найден**\n\n"
            f"К сожалению, номер `{phone_number}` не найден в нашей базе клиентов.\n\n"
            f"**Возможные причины:**\n"
            f"• Вы не являетесь клиентом нашей компании\n"
            f"• Номер телефона в профиле отличается от предоставленного\n"
            f"• Номер не актуализирован в базе\n\n"
            f"**Что делать:**\n"
            f"• Обратитесь к администратору для добавления в систему\n"
            f"• Проверьте правильность номера телефона в профиле\n\n"
            f"📞 **Техподдержка:** support@yourcompany.com"
        )
        return
    
    # Проверяем, не зарегистрирован ли уже этот клиент с другим Telegram
    if client_info['registration_status'] == 'completed':
        await message.answer(
            f"⚠️ **Клиент уже зарегистрирован**\n\n"
            f"Номер телефона `{phone_number}` уже привязан к системе авторизации.\n\n"
            f"Если это ваш номер, но вы потеряли доступ к предыдущему аккаунту Telegram, "
            f"обратитесь в техподдержку для сброса привязки."
        )
        return
    
    # Предлагаем подтвердить регистрацию
    confirmation_text = f"""
✅ **Номер телефона найден!**

**Данные клиента:**
👤 Имя: {client_info.get('first_name', 'Не указано')} {client_info.get('last_name', '')}
📱 Телефон: `{phone_number}`
🆔 ID клиента: `{client_info['client_id']}`

Подтверждаете регистрацию этого профиля клиента в системе авторизации?
"""
    
    # Сохраняем данные для подтверждения в Redis
    await redis_service.redis.setex(
        f"registration:{user.id}",
        300,  # 5 минут
        f"{phone_number}|{client_info['client_id']}"
    )
    
    await message.answer(confirmation_text, reply_markup=get_registration_confirmation_keyboard())


@router.callback_query(F.data == "confirm_registration")
async def confirm_registration(callback: CallbackQuery):
    """Подтверждение регистрации"""
    user = callback.from_user
    
    # Получаем данные регистрации из Redis
    registration_data = await redis_service.redis.get(f"registration:{user.id}")
    
    if not registration_data:
        await callback.answer("❌ Сессия регистрации истекла", show_alert=True)
        await callback.message.edit_text(
            "❌ **Сессия регистрации истекла**\n\n"
            "Пожалуйста, начните регистрацию заново с команды /start"
        )
        return
    
    phone_number, client_id = registration_data.split("|")
    
    # Завершаем регистрацию
    registration_result = await auth_service.complete_phone_registration(
        phone_number=phone_number,
        telegram_id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        username=user.username
    )
    
    if registration_result['success']:
        # Успешная регистрация
        await callback.message.edit_text(
            f"🎉 **Регистрация завершена!**\n\n"
            f"Ваш аккаунт Telegram успешно привязан к профилю клиента.\n\n"
            f"**Что дальше:**\n"
            f"• Теперь вы будете получать запросы на подтверждение операций\n"
            f"• У вас будет 5 минут на принятие решения по каждому запросу\n"
            f"• Для справки используйте команду /help\n\n"
            f"**Добро пожаловать в систему авторизации!** 🔐",
            reply_markup=get_main_menu_keyboard()
        )
        
        # Удаляем данные регистрации
        await redis_service.redis.delete(f"registration:{user.id}")
        
        await callback.answer("✅ Регистрация успешно завершена!")
        
    else:
        # Ошибка регистрации
        error_messages = {
            'phone_not_found': "Номер телефона не найден в базе",
            'telegram_already_registered': "Этот Telegram уже привязан к другому клиенту",
            'internal_error': "Внутренняя ошибка сервиса"
        }
        
        error_text = error_messages.get(
            registration_result.get('error'), 
            "Неизвестная ошибка"
        )
        
        await callback.answer(f"❌ {error_text}", show_alert=True)
        await callback.message.edit_text(
            f"❌ **Ошибка регистрации**\n\n"
            f"{registration_result.get('message', error_text)}\n\n"
            f"Попробуйте снова или обратитесь в техподдержку."
        )


@router.callback_query(F.data == "retry_registration")
async def retry_registration(callback: CallbackQuery):
    """Повторная регистрация"""
    await callback.message.delete()
    await cmd_start(callback.message)
    await callback.answer()


# ========== ОСНОВНЫЕ КОМАНДЫ ==========

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    user_id = message.from_user.id
    is_registered = await auth_service.is_user_registered(user_id)
    
    if not is_registered:
        help_text = """
📋 **Справка по системе авторизации**

❌ **Вы не зарегистрированы в системе**

Для использования системы авторизации операций необходимо:
1. Пройти регистрацию через команду /start
2. Поделиться номером телефона для проверки
3. Подтвердить привязку к профилю клиента

После регистрации вы сможете получать и подтверждать запросы операций.
"""
    else:
        help_text = """
📋 **Справка по использованию**

✅ **Вы зарегистрированы в системе**

🔹 **Как это работает:**
• Когда в системе инициируется операция, требующая вашего подтверждения, вы получите сообщение
• У вас будет 5 минут на принятие решения
• Используйте кнопки "✅ Да, разрешаю" или "❌ Нет, отклоняю"
• После истечения времени запрос автоматически отклоняется

🔹 **Команды:**
/start - Главное меню
/help - Эта справка  
/support - Связь с поддержкой

🔒 **Безопасность:**
• Подтверждать операции можете только вы
• Все запросы привязаны к вашему профилю клиента
• История операций сохраняется в системе
"""
    
    await message.answer(help_text)


@router.message(Command("support"))
async def cmd_support(message: Message):
    """Обработчик команды /support"""
    support_text = f"""
🆘 **Техническая поддержка**

По вопросам работы системы авторизации обращайтесь:

📧 **Email:** support@yourcompany.com
📞 **Телефон:** +7 (XXX) XXX-XX-XX  
🕐 **Время работы:** 9:00 - 18:00 (МСК)

**При обращении укажите:**
• Ваш Telegram ID: `{message.from_user.id}`
• Описание проблемы
• Время возникновения

**Частые вопросы:**
• Не приходят уведомления - проверьте, не заблокирован ли бот
• Ошибка регистрации - убедитесь, что номер телефона указан корректно
• Забыли пароль - система не использует пароли, только Telegram авторизация
"""
    
    await message.answer(support_text)


# ========== ОБРАБОТЧИКИ CALLBACK ДЛЯ МЕНЮ ==========

@router.callback_query(F.data == "help")
async def callback_help(callback: CallbackQuery):
    """Callback для справки"""
    await cmd_help(callback.message)
    await callback.answer()


@router.callback_query(F.data == "support")
async def callback_support(callback: CallbackQuery):
    """Callback для поддержки"""
    await cmd_support(callback.message)
    await callback.answer()


# ========== СУЩЕСТВУЮЩИЕ ОБРАБОТЧИКИ АВТОРИЗАЦИИ ==========

@router.callback_query(F.data.startswith("auth_"))
async def handle_auth_callback(callback: CallbackQuery):
    """Обработчик кнопок авторизации"""
    try:
        # Проверяем регистрацию пользователя
        if not await auth_service.is_user_registered(callback.from_user.id):
            await callback.answer(
                "❌ Вы не зарегистрированы в системе. Используйте /start", 
                show_alert=True
            )
            return
        
        # Парсим callback_data
        action, request_id = callback.data.split(":", 1)
        user_id = callback.from_user.id
        
        logger.info(f"Auth callback: {action} for request {request_id} from user {user_id}")
        
        # Получаем данные запроса из Redis
        request_info = await redis_service.get_auth_request(request_id)
        
        if not request_info:
            await callback.answer(
                "❌ Запрос не найден или уже обработан", 
                show_alert=True
            )
            return
        
        # Проверяем, что пользователь имеет право отвечать на этот запрос
        if request_info.get('telegram_id') != user_id:
            await callback.answer(
                "❌ У вас нет прав на выполнение этой операции", 
                show_alert=True
            )
            return
        
        # Проверяем, что запрос еще не обработан
        if request_info.get('status') != 'pending':
            await callback.answer(
                f"❌ Запрос уже обработан со статусом: {request_info.get('status')}", 
                show_alert=True
            )
            return
        
        # Обрабатываем ответ
        if action == "auth_approve":
            await auth_service.approve_request(request_id, user_id)
            result_text = "✅ **Операция подтверждена**\n\nВаше разрешение получено и передано в систему."
            callback_text = "✅ Операция подтверждена"
            
        elif action == "auth_reject":
            await auth_service.reject_request(request_id, user_id)
            result_text = "❌ **Операция отклонена**\n\nВаш отказ получен и передан в систему."
            callback_text = "❌ Операция отклонена"
        else:
            await callback.answer("❌ Неизвестное действие", show_alert=True)
            return
        
        # Отправляем подтверждение
        await callback.answer(callback_text, show_alert=True)
        
        # Обновляем сообщение
        original_text = callback.message.html_text
        updated_text = f"{original_text}\n\n{result_text}"
        
        await callback.message.edit_text(
            updated_text,
            reply_markup=get_auth_result_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error handling auth callback: {e}")
        await callback.answer(
            "❌ Произошла ошибка при обработке запроса", 
            show_alert=True
        )


@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery):
    """Обработчик кнопки "В главное меню" """
    await callback.message.delete()
    await cmd_start(callback.message)
    await callback.answer()


async def send_auth_request_to_user(
    telegram_id: int,
    request_id: str,
    operation: str,
    amount: str = None,
    client_id: str = None
):
    """Отправка запроса на авторизацию пользователю"""
    try:
        from app.bot.bot import bot
        
        # НОВАЯ ПРОВЕРКА: Проверяем регистрацию перед отправкой
        if not await auth_service.is_user_registered(telegram_id):
            logger.warning(f"Attempt to send auth request to unregistered user {telegram_id}")
            raise ValueError("User not registered in the system")
        
        # Формируем текст сообщения
        message_text = f"""
🔐 **Запрос на подтверждение операции**

👤 **Клиент:** {client_id}
💰 **Операция:** {operation}
"""
        
        if amount:
            message_text += f"\n💵 **Сумма:** {amount}"
        
        message_text += """

⏰ **Время на принятие решения:** 5 минут

*Разрешить выполнение операции?*
"""
        
        # Отправляем сообщение с кнопками
        await bot.send_message(
            chat_id=telegram_id,
            text=message_text,
            reply_markup=get_auth_keyboard(request_id)
        )
        
        logger.info(f"Auth request sent to user {telegram_id}")
        
    except Exception as e:
        logger.error(f"Error sending auth request to user: {e}")
        raise
