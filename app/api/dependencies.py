from typing import Annotated
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.database import get_db
from app.config import settings


async def get_database() -> AsyncSession:
    """Получение сессии базы данных"""
    async for db in get_db():
        yield db


async def verify_api_key(x_api_key: Annotated[str, Header()]):
    """Проверка API ключа"""
    if x_api_key != settings.api_secret_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )
    return True


DatabaseDep = Annotated[AsyncSession, Depends(get_database)]
ApiKeyDep = Annotated[bool, Depends(verify_api_key)]
