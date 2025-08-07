import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from loguru import logger

from app.services.redis_service import redis_service
from app.database.database import async_session
from app.database.models import AuthRequest, Client
# from app.bot.handlers import send_auth_request_to_user
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    """Сервис для работы с авторизацией клиентов"""
    
    async def create_auth_request(
        self,
        client_id: str,
        telegram_id: int,
        operation: str,
        amount: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Создание запроса на авторизацию"""
        from app.bot.handlers import send_auth_request_to_user
        try:
            # Проверяем лимит активных запросов
            pending_count = await redis_service.get_user_pending_requests_count(telegram_id)
            from app.config import settings
            
            if pending_count >= settings.max_pending_requests:
                raise ValueError(f"Превышен лимит активных запросов ({settings.max_pending_requests})")
            
            # Генерируем уникальный ID запроса
            request_id = str(uuid.uuid4())
            
            # Данные для сохранения в Redis
            redis_payload = {
                'request_id': request_id,
                'client_id': client_id,
                'telegram_id': telegram_id,
                'operation': operation,
                'amount': amount,
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            # Сохраняем в Redis с TTL
            await redis_service.set_auth_request(request_id, redis_payload)
            
            # Сохраняем в базу данных для истории
            async with async_session() as db:
                db_request = AuthRequest(
                    request_id=request_id,
                    client_id=client_id,
                    telegram_id=telegram_id,
                    operation=operation,
                    amount=amount,
                    status='pending',
                    metadata_json=str(metadata) if metadata else None
                )
                db.add(db_request)
                await db.commit()
            
            # Отправляем уведомление пользователю в Telegram
            await send_auth_request_to_user(
                telegram_id=telegram_id,
                request_id=request_id,
                operation=operation,
                amount=amount,
                client_id=client_id
            )
            
            logger.info(f"Auth request {request_id} created for client {client_id}")
            return request_id
            
        except Exception as e:
            logger.error(f"Error creating auth request: {e}")
            raise
    
    async def approve_request(self, request_id: str, user_id: int):
        """Подтверждение запроса авторизации"""
        try:
            # Обновляем статус в Redis
            await redis_service.update_auth_request_status(
                request_id, 
                'approved',
                {'approved_by': user_id}
            )
            
            # Обновляем в базе данных
            async with async_session() as db:
                result = await db.execute(
                    update(AuthRequest)
                    .where(AuthRequest.request_id == request_id)
                    .values(
                        status='approved',
                        approved_at=datetime.now()
                    )
                )
                await db.commit()
            
            logger.info(f"Auth request {request_id} approved by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error approving request: {e}")
            raise
    
    async def reject_request(self, request_id: str, user_id: int):
        """Отклонение запроса авторизации"""
        try:
            # Обновляем статус в Redis
            await redis_service.update_auth_request_status(
                request_id,
                'rejected',
                {'rejected_by': user_id}
            )
            
            # Обновляем в базе данных
            async with async_session() as db:
                result = await db.execute(
                    update(AuthRequest)
                    .where(AuthRequest.request_id == request_id)
                    .values(
                        status='rejected',
                        rejected_at=datetime.now()
                    )
                )
                await db.commit()
            
            logger.info(f"Auth request {request_id} rejected by user {user_id}")
            
        except Exception as e:
            logger.error(f"Error rejecting request: {e}")
            raise
    
    async def get_request_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Получение статуса запроса авторизации"""
        try:
            # Сначала проверяем Redis
            redis_info = await redis_service.get_auth_request(request_id)
            if redis_info:
                return redis_info
            
            # Если нет в Redis, проверяем базу данных
            async with async_session() as db:
                result = await db.execute(
                    select(AuthRequest).where(AuthRequest.request_id == request_id)
                )
                db_request = result.scalar_one_or_none()
                
                if db_request:
                    return {
                        'request_id': db_request.request_id,
                        'client_id': db_request.client_id,
                        'telegram_id': db_request.telegram_id,
                        'operation': db_request.operation,
                        'amount': db_request.amount,
                        'status': db_request.status,
                        'created_at': db_request.created_at.isoformat() if db_request.created_at else None,
                        'approved_at': db_request.approved_at.isoformat() if db_request.approved_at else None,
                        'rejected_at': db_request.rejected_at.isoformat() if db_request.rejected_at else None,
                        'metadata': db_request.metadata_json
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting request status: {e}")
            return None
    
    async def register_client(
        self,
        client_id: str,
        telegram_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        username: Optional[str] = None,
        phone: Optional[str] = None,
        email: Optional[str] = None
    ) -> bool:
        """Регистрация нового клиента"""
        try:
            async with async_session() as db:
                # Проверяем, существует ли клиент
                existing = await db.execute(
                    select(Client).where(
                        (Client.client_id == client_id) | (Client.telegram_id == telegram_id)
                    )
                )
                
                if existing.scalar_one_or_none():
                    logger.warning(f"Client {client_id} or telegram_id {telegram_id} already exists")
                    return False
                
                # Создаем нового клиента
                client = Client(
                    client_id=client_id,
                    telegram_id=telegram_id,
                    first_name=first_name,
                    last_name=last_name,
                    username=username,
                    phone=phone,
                    email=email,
                    is_active=True
                )
                
                db.add(client)
                await db.commit()
                
                logger.info(f"Client {client_id} registered successfully")
                return True
                
        except Exception as e:
            logger.error(f"Error registering client: {e}")
            return False
    
    async def get_client_by_id(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Получение данных клиента по ID"""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Client).where(Client.client_id == client_id)
                )
                client = result.scalar_one_or_none()
                
                if client:
                    return {
                        'client_id': client.client_id,
                        'telegram_id': client.telegram_id,
                        'first_name': client.first_name,
                        'last_name': client.last_name,
                        'username': client.username,
                        'phone': client.phone,
                        'email': client.email,
                        'is_active': client.is_active,
                        'created_at': client.created_at.isoformat() if client.created_at else None
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting client: {e}")
            return None


# Глобальный экземпляр
auth_service = AuthService()
