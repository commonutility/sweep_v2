from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json

from database import get_db
from models import User, Trade, Portfolio, Market
from security import get_current_user

# Pydantic models
class TradeBase(BaseModel):
    symbol: str
    side: str  # buy or sell
    order_type: str  # market or limit
    amount: float
    price: Optional[float] = None  # Optional for market orders

class TradeCreate(TradeBase):
    pass

class TradeResponse(TradeBase):
    id: int
    status: str
    created_at: datetime
    executed_at: Optional[datetime] = None
    user_id: int
    bot_id: Optional[int] = None

    class Config:
        orm_mode = True

class MarketData(BaseModel):
    symbol: str
    price: float
    volume_24h: float
    change_24h: float

    class Config:
        orm_mode = True

# Router
router = APIRouter()

@router.post("/orders", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
def create_order(trade: TradeCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Validate trade data
    if trade.side not in ["buy", "sell"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'buy' or 'sell'"
        )
    
    if trade.order_type not in ["market", "limit"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order type must be 'market' or 'limit'"
        )
    
    if trade.order_type == "limit" and not trade.price:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price is required for limit orders"
        )
    
    # Get market data to check if symbol exists and get current price for market orders
    market = db.query(Market).filter(Market.symbol == trade.symbol).first()
    if not market:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Market {trade.symbol} not found"
        )
    
    # For market orders, use current market price
    price = trade.price if trade.order_type == "limit" else market.price
    
    # Create new trade
    new_trade = Trade(
        symbol=trade.symbol,
        side=trade.side,
        order_type=trade.order_type,
        amount=trade.amount,
        price=price,
        status="open",
        user_id=current_user.id
    )
    
    db.add(new_trade)
    db.commit()
    db.refresh(new_trade)
    
    # If it's a market order, execute it immediately
    if trade.order_type == "market":
        # Update trade status
        new_trade.status = "filled"
        new_trade.executed_at = datetime.now()
        
        # Update user's portfolio
        base_asset, quote_asset = trade.symbol.split("/")
        
        # Check if user has portfolio entries for these assets
        base_portfolio = db.query(Portfolio).filter(
            Portfolio.user_id == current_user.id,
            Portfolio.asset == base_asset
        ).first()
        
        quote_portfolio = db.query(Portfolio).filter(
            Portfolio.user_id == current_user.id,
            Portfolio.asset == quote_asset
        ).first()
        
        # Create portfolio entries if they don't exist
        if not base_portfolio:
            base_portfolio = Portfolio(user_id=current_user.id, asset=base_asset, balance=0)
            db.add(base_portfolio)
        
        if not quote_portfolio:
            quote_portfolio = Portfolio(user_id=current_user.id, asset=quote_asset, balance=0)
            db.add(quote_portfolio)
        
        # Update balances based on trade
        if trade.side == "buy":
            base_portfolio.balance += trade.amount
            quote_portfolio.balance -= trade.amount * price
        else:  # sell
            base_portfolio.balance -= trade.amount
            quote_portfolio.balance += trade.amount * price
        
        db.commit()
    
    return new_trade

@router.get("/orders", response_model=List[TradeResponse])
def get_orders(status: Optional[str] = None, symbol: Optional[str] = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Trade).filter(Trade.user_id == current_user.id)
    
    if status:
        query = query.filter(Trade.status == status)
    
    if symbol:
        query = query.filter(Trade.symbol == symbol)
    
    trades = query.order_by(Trade.created_at.desc()).offset(skip).limit(limit).all()
    return trades

@router.get("/orders/{trade_id}", response_model=TradeResponse)
def get_order(trade_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    trade = db.query(Trade).filter(Trade.id == trade_id, Trade.user_id == current_user.id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade

@router.get("/markets", response_model=List[MarketData])
def get_markets(db: Session = Depends(get_db)):
    markets = db.query(Market).all()
    return markets

@router.get("/markets/{symbol}", response_model=MarketData)
def get_market(symbol: str, db: Session = Depends(get_db)):
    market = db.query(Market).filter(Market.symbol == symbol).first()
    if not market:
        raise HTTPException(status_code=404, detail=f"Market {symbol} not found")
    return market

@router.get("/portfolio", response_model=List[dict])
def get_portfolio(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == current_user.id).all()
    
    # Enrich portfolio data with current market prices
    result = []
    for item in portfolio:
        # Skip zero balances
        if item.balance == 0:
            continue
        
        data = {
            "asset": item.asset,
            "balance": item.balance,
            "value_usd": None  # Will be populated if market data is available
        }
        
        # Try to find a USD market for this asset
        market = db.query(Market).filter(Market.symbol == f"{item.asset}/USD").first()
        if market:
            data["value_usd"] = item.balance * market.price
        
        result.append(data)
    
    return result

# WebSocket for real-time market data
@router.websocket("/ws/markets")
async def websocket_markets(websocket: WebSocket, db: Session = Depends(get_db)):
    await websocket.accept()
    try:
        while True:
            # Simulated market data update (in a real app, this would come from an exchange API)
            markets = db.query(Market).all()
            market_data = [{
                "symbol": market.symbol,
                "price": market.price,
                "volume_24h": market.volume_24h,
                "change_24h": market.change_24h,
                "timestamp": datetime.now().isoformat()
            } for market in markets]
            
            await websocket.send_json({"type": "market_update", "data": market_data})
            
            # In a real app, you would wait for actual updates rather than sending periodically
            import asyncio
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        print("Client disconnected from market websocket") 