from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
from security import get_password_hash, verify_password

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    bots = relationship("Bot", back_populates="owner")
    trades = relationship("Trade", back_populates="user")
    portfolio = relationship("Portfolio", back_populates="user")

    def verify_password(self, password):
        return verify_password(password, self.hashed_password)

    def set_password(self, password):
        self.hashed_password = get_password_hash(password)

class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    status = Column(String)  # running, stopped, error
    strategy = Column(String)
    config = Column(String)  # JSON configuration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    owner_id = Column(Integer, ForeignKey("users.id"))

    # Relationships
    owner = relationship("User", back_populates="bots")
    trades = relationship("Trade", back_populates="bot")

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, index=True)  # e.g., BTC/USD
    side = Column(String)  # buy or sell
    order_type = Column(String)  # market, limit, etc.
    amount = Column(Float)
    price = Column(Float)
    status = Column(String)  # open, filled, canceled
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True))
    user_id = Column(Integer, ForeignKey("users.id"))
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=True)  # Nullable for manual trades

    # Relationships
    user = relationship("User", back_populates="trades")
    bot = relationship("Bot", back_populates="trades")

class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    asset = Column(String, index=True)  # e.g., BTC, ETH
    balance = Column(Float)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    user_id = Column(Integer, ForeignKey("users.id"))

    # Relationships
    user = relationship("User", back_populates="portfolio")

class Market(Base):
    __tablename__ = "markets"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, unique=True, index=True)  # e.g., BTC/USD
    base_asset = Column(String)  # e.g., BTC
    quote_asset = Column(String)  # e.g., USD
    price = Column(Float)
    volume_24h = Column(Float)
    change_24h = Column(Float)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now()) 