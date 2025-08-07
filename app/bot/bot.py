from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from loguru import logger
from app.config import settings
from app.services.redis_service import redis_service


# Создаем экземпляр бота
bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

# Создаем диспетчер с Redis хранилищем для FSM
storage = RedisStorage.from_url(settings.redis_url)
dp = Dispatcher(storage=storage)


async def setup_bot():
    """Настройка бота"""
    try:
        # Подключаемся к Redis
        await redis_service.connect()
        
        # Устанавливаем webhook
        await bot.set_webhook(
            url=settings.full_webhook_url,
            allowed_updates=dp.resolve_used_update_types(),
            drop_pending_updates=True
        )
        
        logger.info(f"Webhook set to {settings.full_webhook_url}")
        logger.info("Bot setup completed successfully")
        
    except Exception as e:
        logger.error(f"Error setting up bot: {e}")
        raise


async def shutdown_bot():
    """Завершение работы бота"""
    try:
        # Удаляем webhook
        await bot.delete_webhook(drop_pending_updates=True)
        
        # Отключаемся от Redis
        await redis_service.disconnect()
        
        # Закрываем сессию бота
        await bot.session.close()
        
        logger.info("Bot shutdown completed")
        
    except Exception as e:
        logger.error(f"Error during bot shutdown: {e}")
