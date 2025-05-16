from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime
import json

from database import get_db
from models import User, Bot, Trade
from security import get_current_user

# Pydantic models
class BotBase(BaseModel):
    name: str
    strategy: str
    config: str  # JSON string

class BotCreate(BotBase):
    pass

class BotResponse(BotBase):
    id: int
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    owner_id: int

    class Config:
        orm_mode = True

class BotActionResponse(BaseModel):
    success: bool
    message: str
    status: str

# Router
router = APIRouter()

# Background task to simulate bot behavior
def run_bot_task(bot_id: int, db: Session):
    bot = db.query(Bot).filter(Bot.id == bot_id).first()
    if not bot:
        return
    
    # Update bot status
    bot.status = "running"
    db.commit()
    
    # Simulate some bot trades (in a real app, this would be more complex)
    try:
        config = json.loads(bot.config)
        symbol = config.get("symbol", "BTC/USD")
        side = config.get("side", "buy")
        amount = float(config.get("amount", 0.01))
        
        # Create a trade
        from models import Market
        market = db.query(Market).filter(Market.symbol == symbol).first()
        if market:
            trade = Trade(
                symbol=symbol,
                side=side,
                order_type="market",
                amount=amount,
                price=market.price,
                status="filled",
                executed_at=datetime.now(),
                user_id=bot.owner_id,
                bot_id=bot.id
            )
            db.add(trade)
            db.commit()
    except Exception as e:
        # If there's an error, update bot status
        bot.status = "error"
        db.commit()
        print(f"Error running bot {bot_id}: {str(e)}")

@router.post("/", response_model=BotResponse, status_code=status.HTTP_201_CREATED)
def create_bot(bot: BotCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Validate bot data
    try:
        json.loads(bot.config)  # Ensure config is valid JSON
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in config field"
        )
    
    # Create new bot
    new_bot = Bot(
        name=bot.name,
        strategy=bot.strategy,
        config=bot.config,
        status="stopped",  # Initially stopped
        owner_id=current_user.id
    )
    
    db.add(new_bot)
    db.commit()
    db.refresh(new_bot)
    
    return new_bot

@router.get("/", response_model=List[BotResponse])
def get_bots(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    bots = db.query(Bot).filter(Bot.owner_id == current_user.id).all()
    return bots

@router.get("/{bot_id}", response_model=BotResponse)
def get_bot(bot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.owner_id == current_user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    return bot

@router.put("/{bot_id}", response_model=BotResponse)
def update_bot(bot_id: int, bot_data: BotBase, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Find the bot
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.owner_id == current_user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Validate bot data
    try:
        json.loads(bot_data.config)  # Ensure config is valid JSON
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON in config field"
        )
    
    # Update bot
    bot.name = bot_data.name
    bot.strategy = bot_data.strategy
    bot.config = bot_data.config
    
    db.commit()
    db.refresh(bot)
    
    return bot

@router.post("/{bot_id}/start", response_model=BotActionResponse)
def start_bot(bot_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Find the bot
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.owner_id == current_user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Check if bot is already running
    if bot.status == "running":
        return BotActionResponse(
            success=False,
            message="Bot is already running",
            status=bot.status
        )
    
    # Start the bot (in a real app, this would be more complex)
    background_tasks.add_task(run_bot_task, bot_id, db)
    
    return BotActionResponse(
        success=True,
        message="Bot started successfully",
        status="starting"
    )

@router.post("/{bot_id}/stop", response_model=BotActionResponse)
def stop_bot(bot_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Find the bot
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.owner_id == current_user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Check if bot is already stopped
    if bot.status == "stopped":
        return BotActionResponse(
            success=False,
            message="Bot is already stopped",
            status=bot.status
        )
    
    # Stop the bot
    bot.status = "stopped"
    db.commit()
    
    return BotActionResponse(
        success=True,
        message="Bot stopped successfully",
        status="stopped"
    )

@router.get("/{bot_id}/trades", response_model=List[Dict[str, Any]])
def get_bot_trades(bot_id: int, limit: int = 10, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Find the bot
    bot = db.query(Bot).filter(Bot.id == bot_id, Bot.owner_id == current_user.id).first()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    # Get trades made by this bot
    trades = db.query(Trade).filter(Trade.bot_id == bot_id).order_by(Trade.created_at.desc()).limit(limit).all()
    
    # Format trades
    result = []
    for trade in trades:
        result.append({
            "id": trade.id,
            "symbol": trade.symbol,
            "side": trade.side,
            "amount": trade.amount,
            "price": trade.price,
            "executed_at": trade.executed_at.isoformat() if trade.executed_at else None,
            "status": trade.status
        })
    
    return result 