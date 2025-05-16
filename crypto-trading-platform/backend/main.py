import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel
import socketio
import uvicorn
import json

# Import routers
from routers import users, trading, bots
from database import get_db
from security import create_access_token, get_current_user

# Load environment variables
API_KEY = os.environ.get("COMPANY_API_KEY", "dev_api_key")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev_secret_key")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Initialize FastAPI app
app = FastAPI(title="Crypto Trading Platform API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins in development
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Initialize Socket.IO
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=["*"]
)

socket_app = socketio.ASGIApp(sio, app)

# Connected clients
connected_clients = set()

# Middleware to verify API key
@app.middleware("http")
async def verify_api_key(request, call_next):
    if request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        return await call_next(request)
        
    api_key = request.headers.get("X-API-Key")
    if not api_key and API_KEY != "dev_api_key":
        if api_key != API_KEY:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid API key"}
            )
    
    return await call_next(request)

# Socket.IO events
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    connected_clients.add(sid)
    await sio.emit("message", {"status": "connected", "timestamp": datetime.now().isoformat()})

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    connected_clients.discard(sid)

@sio.event
async def message(sid, data):
    print(f"Message from {sid}: {data}")
    # Process message and broadcast to all clients
    await sio.emit("message", {"data": data, "timestamp": datetime.now().isoformat()})

@sio.event
async def trade_update(sid, data):
    # Process trade update and broadcast to all clients
    await sio.emit("trade_update", {"data": data, "timestamp": datetime.now().isoformat()})

# WebSocket endpoint for direct connections (alternative to Socket.IO)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # Process the received data
            try:
                parsed_data = json.loads(data)
                # Echo back with timestamp
                await websocket.send_json({
                    "data": parsed_data,
                    "timestamp": datetime.now().isoformat()
                })
            except json.JSONDecodeError:
                await websocket.send_text(f"Received: {data}")
    except WebSocketDisconnect:
        print("Client disconnected from WebSocket")

# Include routers
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(trading.router, prefix="/api/trading", tags=["trading"])
app.include_router(bots.router, prefix="/api/bots", tags=["bots"])

# Root endpoint
@app.get("/")
def read_root():
    return {"message": "Welcome to the Crypto Trading Platform API"}

# Login endpoint
@app.post("/api/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    from models import User
    db = next(get_db())
    user = db.query(User).filter(User.username == form_data.username).first()
    
    if not user or not user.verify_password(form_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

# Run the server if this file is executed directly
if __name__ == "__main__":
    uvicorn.run(socket_app, host="0.0.0.0", port=8000) 