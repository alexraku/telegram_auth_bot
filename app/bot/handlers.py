import hashlib
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, Update
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.bot.keyboards import get_auth_keyboard, get_auth_result_keyboard
from app.services.redis_service import redis_service
from app.services.auth_service import auth_service
from app.database.database import get_db


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    user = message.from_user
    welcome_text = f"""
🔐 <b>Добро пожаловать в систему авторизации!</b>

Привет, {user.first_name}! 

Этот бот поможет вам подтверждать операции в нашей системе.

<i>Ваш Telegram ID:</i> <code>{user.id}</code>

Для настройки авторизации обратитесь к администратору системы.
"""
    
    await message.answer(welcome_text)


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработчик команды /help"""
    help_text = """
📋 <b>Справка по использованию</b>

🔹 Когда в системе инициируется операция, требующая вашего подтверждения, вы получите сообщение с описанием операции и кнопками "Да" / "Нет"

🔹 У вас есть 5 минут на принятие решения

🔹 После истечения времени запрос автоматически отклоняется

🔹 Для связи с поддержкой используйте команду /support

<b>Команды:</b>
/start - Главное меню
/help - Эта справка
/support - Связь с поддержкой
"""
    
    await message.answer(help_text)


@router.message(Command("support"))
async def cmd_support(message: Message):
    """Обработчик команды /support"""
    support_text = f"""
🆘 <b>Техническая поддержка</b>

По вопросам работы системы авторизации обращайтесь:

📧 Email: support@yourcompany.com
📞 Телефон: +7 (XXX) XXX-XX-XX
🕐 Время работы: 9:00 - 18:00 (МСК)

<i>Ваш Telegram ID для службы поддержки:</i> <code>{message.from_user.id}</code>
"""
    
    await message.answer(support_text)


@router.callback_query(F.data.startswith("auth_"))
async def handle_auth_callback(callback: CallbackQuery):
    """Обработчик кнопок авторизации"""
    try:
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
            result_text = "✅ <b>Операция подтверждена</b>\\n\\nВаше разрешение получено и передано в систему."
            callback_text = "✅ Операция подтверждена"
            
        elif action == "auth_reject":
            await auth_service.reject_request(request_id, user_id)
            result_text = "❌ <b>Операция отклонена</b>\\n\\nВаш отказ получен и передан в систему."
            callback_text = "❌ Операция отклонена"
        else:
            await callback.answer("❌ Неизвестное действие", show_alert=True)
            return
        
        # Отправляем подтверждение
        await callback.answer(callback_text, show_alert=True)
        
        # Обновляем сообщение
        original_text = callback.message.html_text
        updated_text = f"{original_text}\\n\\n{result_text}"
        
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
        
        # Формируем текст сообщения
        message_text = f"""
🔐 <b>Запрос на подтверждение операции</b>

👤 <b>Клиент:</b> {client_id}
💰 <b>Операция:</b> {operation}
"""
        
        if amount:
            message_text += f"\\n💵 <b>Сумма:</b> {amount}"
        
        message_text += """

⏰ <b>Время на принятие решения:</b> 5 минут

<i>Разрешить выполнение операции?</i>
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
