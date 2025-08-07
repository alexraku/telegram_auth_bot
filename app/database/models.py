from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, BigInteger, Index
from sqlalchemy.sql import func
from app.database.database import Base


class Client(Base):
    """Модель клиента"""
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(String(100), unique=True, index=True, nullable=False)
    telegram_id = Column(BigInteger, unique=True, index=True, nullable=False)
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    username = Column(String(100), nullable=True)
    # new 07/08/25 begin
    phone = Column(String(20), nullable=True, index=True)  # Теперь с индексом!
    email = Column(String(100), nullable=True)
    registration_status = Column(String(20), default='pending', nullable=False)  # pending, completed
    # new 07/08/25 end ----------------
    # before_begin
    # phone = Column(String(20), nullable=True)
    # email = Column(String(100), nullable=True)
    # before_end -----------------
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Добавляем составной индекс для оптимизации запросов
    __table_args__ = (
        Index('idx_client_phone_active', 'phone', 'is_active'),
    )


class AuthRequest(Base):
    """Модель запроса на авторизацию"""
    __tablename__ = "auth_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), unique=True, index=True, nullable=False)
    client_id = Column(String(100), index=True, nullable=False)
    telegram_id = Column(BigInteger, index=True, nullable=False)
    operation = Column(String(255), nullable=False)
    amount = Column(String(50), nullable=True)
    status = Column(String(20), default="pending", nullable=False)  # pending, approved, rejected, expired
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)
    metadata_json = Column(Text, nullable=True)  # Дополнительные данные в JSON
