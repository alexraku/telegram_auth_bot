from redis.asyncio import Redis, ConnectionPool
import json
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
from app.config import settings


class RedisService:
    """Сервис для работы с Redis"""
    
    def __init__(self):
        self.redis: Optional[Redis] = None
        self._connection_pool = None
    
    async def connect(self):
        """Подключение к Redis"""
        try:
            if self.redis is None:
                self._connection_pool = ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=20
                )
                self.redis = Redis(connection_pool=self._connection_pool)
                
                # Проверяем соединение
                await self.redis.ping()
                logger.info("Successfully connected to Redis")
                
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis:
            await self.redis.close()
            await self._connection_pool.disconnect()
            logger.info("Disconnected from Redis")
    
    async def set_auth_request(
        self, 
        request_id: str, 
        info: Dict[str, Any], 
        expire_seconds: int = settings.auth_request_timeout
    ):
        """Сохранение запроса на авторизацию в Redis"""
        try:
            key = f"auth_request:{request_id}"
            await self.redis.setex(
                key, 
                expire_seconds, 
                json.dumps(info, default=str)
            )
            logger.info(f"Auth request {request_id} saved to Redis")
        except Exception as e:
            logger.error(f"Error saving auth request to Redis: {e}")
            raise
    
    async def get_auth_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Получение запроса на авторизацию из Redis"""
        try:
            key = f"auth_request:{request_id}"
            info = await self.redis.get(key)
            if info:
                return json.loads(info)
            return None
        except Exception as e:
            logger.error(f"Error getting auth request from Redis: {e}")
            return None
    
    async def update_auth_request_status(
        self, 
        request_id: str, 
        status: str, 
        additional_info: Optional[Dict[str, Any]] = None
    ):
        """Обновление статуса запроса на авторизацию"""
        try:
            key = f"auth_request:{request_id}"
            info = await self.get_auth_request(request_id)
            if info:
                info['status'] = status
                info['updated_at'] = datetime.now().isoformat()
                
                if status == 'approved':
                    info['approved_at'] = datetime.now().isoformat()
                elif status == 'rejected':
                    info['rejected_at'] = datetime.now().isoformat()
                
                if additional_info:
                    info.update(additional_info)
                
                # Сохраняем обновленные данные
                ttl = await self.redis.ttl(key)
                if ttl > 0:
                    await self.redis.setex(key, ttl, json.dumps(info, default=str))
                
                logger.info(f"Auth request {request_id} status updated to {status}")
        except Exception as e:
            logger.error(f"Error updating auth request status: {e}")
            raise
    
    async def delete_auth_request(self, request_id: str):
        """Удаление запроса на авторизацию из Redis"""
        try:
            key = f"auth_request:{request_id}"
            await self.redis.delete(key)
            logger.info(f"Auth request {request_id} deleted from Redis")
        except Exception as e:
            logger.error(f"Error deleting auth request from Redis: {e}")
    
    async def get_user_pending_requests_count(self, telegram_id: int) -> int:
        """Получение количества активных запросов пользователя"""
        try:
            pattern = f"auth_request:*"
            keys = await self.redis.keys(pattern)
            
            count = 0
            for key in keys:
                info = await self.redis.get(key)
                if info:
                    request_info = json.loads(info)
                    if (request_info.get('telegram_id') == telegram_id and 
                        request_info.get('status') == 'pending'):
                        count += 1
            
            return count
        except Exception as e:
            logger.error(f"Error counting user pending requests: {e}")
            return 0
    
    async def cleanup_expired_requests(self):
        """Очистка истекших запросов (фоновая задача)"""
        try:
            pattern = f"auth_request:*"
            keys = await self.redis.keys(pattern)
            
            expired_count = 0
            for key in keys:
                ttl = await self.redis.ttl(key)
                if ttl == -1:  # Ключ без TTL
                    info = await self.redis.get(key)
                    if info:
                        request_info = json.loads(info)
                        created_at = datetime.fromisoformat(request_info.get('created_at', ''))
                        if datetime.now() - created_at > timedelta(seconds=settings.auth_request_timeout):
                            await self.redis.delete(key)
                            expired_count += 1
            
            if expired_count > 0:
                logger.info(f"Cleaned up {expired_count} expired auth requests")
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Глобальный экземпляр
redis_service = RedisService()
