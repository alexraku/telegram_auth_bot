import uuid

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from loguru import logger
from uuid import UUID, uuid4

from app.api.dependencies import DatabaseDep, ApiKeyDep
from app.services.auth_service import auth_service


router = APIRouter(prefix="/api/v1", tags=["auth"])


class AuthRequestCreate(BaseModel):
    """Схема для создания запроса на авторизацию"""
    client_id: str = Field(..., description="ID клиента в системе")
    telegram_id: int = Field(..., description="Telegram ID пользователя")
    operation: str = Field(..., description="Описание операции", max_length=255)
    amount: Optional[str] = Field(None, description="Сумма операции")
    metadata: Optional[dict] = Field(None, description="Дополнительные данные")


# НОВАЯ СХЕМА: Создание запроса по номеру телефона
class AuthRequestByPhoneCreate(BaseModel):
    """Схема для создания запроса на авторизацию по номеру телефона"""
    phone_number: str = Field(..., description="Номер телефона клиента")
    operation: str = Field(..., description="Описание операции", max_length=255)
    amount: Optional[str] = Field(None, description="Сумма операции")
    metadata: Optional[dict] = Field(None, description="Дополнительные данные")


class AuthRequestResponse(BaseModel):
    """Схема ответа при создании запроса"""
    request_id: str
    status: str
    created_at: str
    expires_at: Optional[str] = None


# НОВАЯ СХЕМА: Ответ для незарегистрированных пользователей  
class RegistrationRequiredResponse(BaseModel):
    """Схема ответа когда требуется регистрация"""
    status: str = "registration_required"
    message: str
    phone_number: str
    client_id: Optional[str] = None


class AuthStatusResponse(BaseModel):
    """Схема ответа со статусом авторизации"""
    request_id: str
    client_id: str
    telegram_id: int
    operation: str
    amount: Optional[str]
    status: str
    created_at: str
    approved_at: Optional[str] = None
    rejected_at: Optional[str] = None
    metadata: Optional[dict] = None


class ClientRegister(BaseModel):
    """Схема для регистрации клиента"""
    client_id: UUID = Field(default_factory=uuid4, description="ID клиента в системе")
    telegram_id: Optional[int] = Field(None, description="Telegram ID пользователя")
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    # username: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    # email: Optional[str] = Field(None, max_length=100)


# ========== НОВЫЙ ЭНДПОИНТ: Создание запроса по номеру телефона ==========

@router.post("/auth/request-by-phone", response_model=AuthRequestResponse)
async def create_auth_request_by_phone(
    request: AuthRequestByPhoneCreate,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Создание запроса на авторизацию по номеру телефона"""
    try:
        # Ищем клиента по номеру телефона
        client = await auth_service.get_client_by_phone(request.phone_number)
        
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": "client_not_found",
                    "message": f"Клиент с номером {request.phone_number} не найден в базе",
                    "phone_number": request.phone_number
                }
            )
        
        # Проверяем статус регистрации
        if client['registration_status'] != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "registration_required", 
                    "message": f"Клиент с номером {request.phone_number} не завершил регистрацию в Telegram-боте",
                    "phone_number": request.phone_number,
                    "client_id": client['client_id']
                }
            )
        
        # Создаем запрос на авторизацию
        request_id = await auth_service.create_auth_request(
            client_id=client['client_id'],
            telegram_id=client['telegram_id'],
            operation=request.operation,
            amount=request.amount,
            metadata=request.metadata
        )
        
        from app.config import settings
        expires_at = datetime.now().timestamp() + settings.auth_request_timeout
        
        return AuthRequestResponse(
            request_id=request_id,
            status="pending",
            created_at=datetime.now().isoformat(),
            expires_at=datetime.fromtimestamp(expires_at).isoformat()
        )
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating auth request by phone: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )



@router.post("/auth/request", response_model=AuthRequestResponse)
async def create_auth_request(
    request: AuthRequestCreate,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Создание запроса на авторизацию"""
    try:
        # Проверяем существование клиента
        client = await auth_service.get_client_by_id(request.client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Client {request.client_id} not found"
            )
        
        # Проверяем соответствие telegram_id
        if client['telegram_id'] != request.telegram_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Telegram ID does not match client info"
            )
        
        # НОВАЯ ПРОВЕРКА: Статус регистрации
        if client['registration_status'] != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Client registration not completed"
            )
        
        # Создаем запрос на авторизацию
        request_id = await auth_service.create_auth_request(
            client_id=request.client_id,
            telegram_id=request.telegram_id,
            operation=request.operation,
            amount=request.amount,
            metadata=request.metadata
        )
        
        from app.config import settings
        expires_at = datetime.now().timestamp() + settings.auth_request_timeout
        
        return AuthRequestResponse(
            request_id=request_id,
            status="pending",
            created_at=datetime.now().isoformat(),
            expires_at=datetime.fromtimestamp(expires_at).isoformat()
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating auth request: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/auth/status/{request_id}", response_model=AuthStatusResponse)
async def get_auth_status(
    request_id: str,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Получение статуса запроса на авторизацию"""
    try:
        status_info = await auth_service.get_request_status(request_id)
        
        if not status_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Auth request not found"
            )
        
        return AuthStatusResponse(**status_info)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting auth status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.post("/client/register", status_code=status.HTTP_201_CREATED)
async def register_client(
    client: ClientRegister,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Регистрация нового клиента"""
    try:
        client_id = uuid.uuid4()
        success = await auth_service.register_client(
            client_id=client_id,
            telegram_id=client.telegram_id,
            first_name=client.first_name,
            last_name=client.last_name,
            # username=client.username,
            phone=client.phone,
            # email=client.email
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Client already exists"
            )
        
        return {"message": "Client registered successfully", "client_id": client.client_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering client: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/client/{client_id}")
async def get_client(
    client_id: str,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Получение данных клиента"""
    try:
        client = await auth_service.get_client_by_id(client_id)
        
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found"
            )
        
        return client
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# НОВЫЙ ЭНДПОИНТ: Поиск клиента по номеру телефона
@router.get("/client/by-phone/{phone_number}")
async def get_client_by_phone(
    phone_number: str,
    db: DatabaseDep,
    _: ApiKeyDep
):
    """Получение данных клиента по номеру телефона"""
    try:
        client = await auth_service.get_client_by_phone(phone_number)
        
        if not client:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Client not found"
            )
        
        return client
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client by phone: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@router.get("/health")
async def health_check():
    """Проверка здоровья сервиса"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}
