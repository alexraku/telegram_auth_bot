import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from loguru import logger

from app.services.redis_service import redis_service
from app.database.database import async_session
from app.database.models import AuthRequest, Client
from sqlalchemy import select, update, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    """Сервис для работы с авторизацией клиентов"""
    
    # ========== НОВЫЕ МЕТОДЫ ДЛЯ РЕГИСТРАЦИИ ==========
    
    async def is_user_registered(self, telegram_id: int) -> bool:
        """Проверка, зарегистрирован ли пользователь"""
        try:
            async with async_session() as db:
                result = await db.execute(
                    select(Client).where(
                        Client.telegram_id == telegram_id,
                        Client.is_active == True,
                        Client.registration_status == 'completed'
                    )
                )
                client = result.scalar_one_or_none()
                return client is not None
        except Exception as e:
            logger.error(f"Error checking user registration: {e}")
            return False
    
    async def get_client_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Получение клиента по номеру телефона"""
        try:
            # Нормализуем номер телефона (убираем +, пробелы, скобки)
            normalized_phone = self._normalize_phone(phone_number)
            print(f"{phone_number=}, {normalized_phone=}")
            
            async with async_session() as db:
                
                # debug find by phone num begin
                tmp = select(Client).where(
                        or_(
                            Client.phone == phone_number,
                            Client.phone == normalized_phone,
                            Client.phone == f"+{normalized_phone}"
                        )
                    )
                from sqlalchemy.dialects import postgresql
                compiled = tmp.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_linds': True})
                print(f"{str(compiled)=}")
                
                # debug find by phone num end ----------
                
                result = await db.execute(
                    select(Client).where(
                        or_(
                            Client.phone == phone_number,
                            Client.phone == normalized_phone,
                            Client.phone == f"+{normalized_phone}"
                        )
                    )
                )
                client = result.scalar_one_or_none()
                
                if client:
                    return {
                        'client_id': client.client_id,
                        'telegram_id': client.telegram_id,
                        'phone': client.phone,
                        'first_name': client.first_name,
                        'last_name': client.last_name,
                        # 'username': client.username,
                        # 'email': client.email,
                        'is_active': client.is_active,
                        'registration_status': client.registration_status,
                        'created_at': client.created_at.isoformat() if client.created_at else None
                    }
                return None
        except Exception as e:
            logger.error(f"Error getting client by phone: {e}")
            return None
    
    async def complete_phone_registration(
        self,
        phone_number: str,
        telegram_id: int,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        # username: Optional[str] = None
    ) -> Dict[str, Any]:
        """Завершение регистрации пользователя по номеру телефона"""
        try:
            normalized_phone = self._normalize_phone(phone_number)
            
            # Ищем существующего клиента в базе 1С
            existing_client = await self.get_client_by_phone(phone_number)
            
            if not existing_client:
                return {
                    'success': False,
                    'error': 'phone_not_found',
                    'message': 'Номер телефона не найден в базе клиентов'
                }
            
            # Проверяем, не зарегистрирован ли уже этот telegram_id
            async with async_session() as db:
                existing_telegram = await db.execute(
                    select(Client).where(Client.telegram_id == telegram_id)
                )
                if existing_telegram.scalar_one_or_none():
                    return {
                        'success': False,
                        'error': 'telegram_already_registered',
                        'message': 'Этот Telegram аккаунт уже привязан к другому клиенту'
                    }
                
                # Обновляем существующего клиента
                await db.execute(
                    update(Client)
                    .where(Client.client_id == existing_client['client_id'])
                    .values(
                        telegram_id=telegram_id,
                        first_name=first_name,
                        last_name=last_name,
                        # username=username,
                        registration_status='completed',
                        updated_at=datetime.now()
                    )
                )
                await db.commit()
                
                logger.info(f"Client {existing_client['client_id']} registered with Telegram ID {telegram_id}")
                
                return {
                    'success': True,
                    'client_id': existing_client['client_id'],
                    'message': 'Регистрация успешно завершена'
                }
                
        except Exception as e:
            logger.error(f"Error completing phone registration: {e}")
            return {
                'success': False,
                'error': 'internal_error',
                'message': 'Внутренняя ошибка сервиса'
            }
    
    def _normalize_phone(self, phone: str) -> str:
        """Нормализация номера телефона"""
        # Убираем все символы кроме цифр
        digits_only = ''.join(filter(str.isdigit, phone))
        
        # Если начинается с 8, меняем на 7 (для России)
        if digits_only.startswith('8') and len(digits_only) == 11:
            digits_only = '7' + digits_only[1:]
            
        return digits_only
    
    # ========== СУЩЕСТВУЮЩИЕ МЕТОДЫ (с модификациями) ==========
    
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
            # НОВАЯ ПРОВЕРКА: Пользователь должен быть зарегистрирован
            if not await self.is_user_registered(telegram_id):
                raise ValueError("Пользователь не зарегистрирован в системе")
            
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
        telegram_id: int | None = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        # username: Optional[str] = None,
        phone: Optional[str] = None,
        # email: Optional[str] = None
    ) -> bool:
        """Регистрация нового клиента"""
        try:
            async with async_session() as db:
                # Проверяем, существует ли клиент
                existing = await db.execute(
                     select(Client).where(
                         or_(
                             Client.phone == phone,
                             and_(
                                 Client.telegram_id.isnot(None),
                                 Client.telegram_id == telegram_id,
                             )
                         )
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
                    # username=username,
                    phone=phone,
                    # email=email,
                    is_active=True,
                    registration_status='completed',  # ИЗМЕНЕНИЕ: сразу completed
                )
                
                db.add(client)
                await db.commit()
                
                logger.info(f"Client {client_id} registered successfully")
                return client_id
                
        except Exception as e:
            logger.error(f"Error registering client: {e}")
            return None
    
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
                        # 'username': client.username,
                        'phone': client.phone,
                        # 'email': client.email,
                        'is_active': client.is_active,
                        'registration_status': client.registration_status,  # ДОБАВЛЕНО
                        'created_at': client.created_at.isoformat() if client.created_at else None
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting client: {e}")
            return None


# Глобальный экземпляр
auth_service = AuthService()
