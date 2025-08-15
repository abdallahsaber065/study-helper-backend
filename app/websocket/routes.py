"""
WebSocket routes for real-time communication.
"""

import json
import logging
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
import structlog

from ..auth.dependencies import get_current_user, get_current_user_websocket
from ..users.models import User
from .manager import websocket_manager

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.websocket("/connect")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str,
):
    """
    Main WebSocket endpoint for real-time connections.
    
    Query parameter:
    - token: JWT access token for authentication
    
    Client can send messages like:
    {
        "type": "subscribe_task",
        "task_id": "task-uuid"
    }
    {
        "type": "unsubscribe_task", 
        "task_id": "task-uuid"
    }
    {
        "type": "ping"
    }
    """
    try:
        # Authenticate user from token
        user = await get_current_user_websocket(token)
        
        # Connect to WebSocket manager
        await websocket_manager.connect(websocket, user.id)
        
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket connection established",
            "user_id": user.id,
            "timestamp": "placeholder"  # Will be set by manager
        })
        
        try:
            # Listen for messages
            while True:
                # Receive message from client
                data = await websocket.receive_json()
                
                # Handle the message
                await websocket_manager.handle_client_message(websocket, data)
                
        except WebSocketDisconnect:
            pass
            
    except Exception as e:
        logger.error(
            "WebSocket connection error",
            error=str(e),
            error_type=type(e).__name__
        )
        try:
            await websocket.close(code=4001, reason="Authentication failed")
        except:
            pass
    finally:
        await websocket_manager.disconnect(websocket)


@router.get("/stats")
async def get_websocket_stats(
    current_user: User = Depends(get_current_user),
) -> Dict:
    """
    Get WebSocket connection statistics.
    
    Only available to authenticated users for debugging/monitoring.
    """
    try:
        stats = websocket_manager.get_connection_stats()
        
        # Add user-specific information if they have connections
        user_connections = stats["connections_by_user"].get(current_user.id, 0)
        stats["current_user_connections"] = user_connections
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting WebSocket stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve WebSocket statistics"
        )


@router.get("/test")
async def websocket_test_page():
    """
    Simple test page for WebSocket connections.
    
    Only available in development mode.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WebSocket Test</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; }
            .message { margin: 10px 0; padding: 10px; background: #f5f5f5; border-radius: 4px; }
            .controls { margin: 20px 0; }
            button { margin: 5px; padding: 10px 15px; }
            input { margin: 5px; padding: 8px; width: 200px; }
            #messages { height: 400px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>WebSocket Test</h1>
            
            <div class="controls">
                <input type="text" id="token" placeholder="JWT Token" />
                <button onclick="connect()">Connect</button>
                <button onclick="disconnect()">Disconnect</button>
            </div>
            
            <div class="controls">
                <input type="text" id="taskId" placeholder="Task ID" />
                <button onclick="subscribeTask()">Subscribe to Task</button>
                <button onclick="unsubscribeTask()">Unsubscribe from Task</button>
                <button onclick="ping()">Ping</button>
            </div>
            
            <div id="messages"></div>
        </div>

        <script>
            let socket = null;
            
            function addMessage(msg) {
                const messages = document.getElementById('messages');
                const div = document.createElement('div');
                div.className = 'message';
                div.innerHTML = `<strong>${new Date().toLocaleTimeString()}</strong>: ${JSON.stringify(msg, null, 2)}`;
                messages.appendChild(div);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function connect() {
                const token = document.getElementById('token').value;
                if (!token) {
                    alert('Please enter a JWT token');
                    return;
                }
                
                socket = new WebSocket(`ws://localhost:8000/ws/connect?token=${token}`);
                
                socket.onopen = function() {
                    addMessage({type: 'system', message: 'Connected to WebSocket'});
                };
                
                socket.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    addMessage(data);
                };
                
                socket.onclose = function() {
                    addMessage({type: 'system', message: 'WebSocket connection closed'});
                };
                
                socket.onerror = function(error) {
                    addMessage({type: 'error', message: 'WebSocket error', error: error});
                };
            }
            
            function disconnect() {
                if (socket) {
                    socket.close();
                    socket = null;
                }
            }
            
            function subscribeTask() {
                const taskId = document.getElementById('taskId').value;
                if (!socket || !taskId) return;
                
                socket.send(JSON.stringify({
                    type: 'subscribe_task',
                    task_id: taskId
                }));
            }
            
            function unsubscribeTask() {
                const taskId = document.getElementById('taskId').value;
                if (!socket || !taskId) return;
                
                socket.send(JSON.stringify({
                    type: 'unsubscribe_task',
                    task_id: taskId
                }));
            }
            
            function ping() {
                if (!socket) return;
                
                socket.send(JSON.stringify({
                    type: 'ping'
                }));
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
