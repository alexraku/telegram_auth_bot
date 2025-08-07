import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from aiogram.types import Update
from loguru import logger

from app.config import settings
from app.database.database import init_db
from app.services.redis_service import redis_service
from app.bot.bot import bot, dp, setup_bot, shutdown_bot
from app.bot.handlers import router as bot_router
from app.api.auth import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Starting application...")
    
    try:
        # Инициализация базы данных
        await init_db()
        logger.info("Database initialized")
        
        # Регистрация роутеров бота
        dp.include_router(bot_router)
        
        # Настройка бота
        await setup_bot()
        
        logger.info("Application started successfully")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise
    
    yield  # Приложение работает
    
    # Завершение работы
    logger.info("Shutting down application...")
    try:
        await shutdown_bot()
        logger.info("Application shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Создание FastAPI приложения
app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description="Telegram Bot для авторизации клиентов в учетной системе",
    lifespan=lifespan
)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В продакшене указать конкретные домены
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключение роутеров
app.include_router(auth_router)


@app.post(settings.webhook_path)
async def webhook(request: Request):
    """Обработка webhook от Telegram"""
    try:
        # Получаем данные от Telegram
        update_payload = await request.json()
        
        # Создаем объект Update
        update = Update.model_validate(update_payload, context={"bot": bot})
        
        # Передаем обновление диспетчеру
        await dp.feed_update(bot, update)
        
        return {"status": "ok"}
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing error")


@app.get("/")
async def root():
    """Корневой эндпоинт"""
    return {
        "service": settings.app_title,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health():
    """Проверка здоровья сервиса"""
    try:
        # Проверяем соединение с Redis
        await redis_service.redis.ping()
        
        return {
            "status": "healthy",
            "services": {
                "redis": "connected",
                "bot": "running",
                "database": "connected"
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {settings.app_host}:{settings.app_port}")
    
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.debug,
        log_level="info"
    )
