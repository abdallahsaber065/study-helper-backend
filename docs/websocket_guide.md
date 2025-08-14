# WebSocket Real-time Communication Guide

## Overview

The Study Assistant backend provides WebSocket support for real-time communication, enabling live progress updates for AI summary generation and other notifications.

## Features

- **Real-time Task Progress**: Live updates for AI summary generation
- **User Notifications**: System-wide and user-specific notifications
- **Connection Management**: Automatic cleanup of disconnected clients
- **Authentication**: JWT-based WebSocket authentication
- **Scalable Architecture**: Support for multiple concurrent connections

## Connection

### WebSocket Endpoint

```bash
ws://localhost:8000/ws/connect?token=YOUR_JWT_TOKEN
```

### Authentication

WebSocket connections require authentication via JWT token passed as a query parameter:

```javascript
const token = "your-jwt-access-token";
const socket = new WebSocket(`ws://localhost:8000/ws/connect?token=${token}`);
```

## Client-Side Implementation

### Basic Connection

```javascript
class StudyAssistantWebSocket {
    constructor(token) {
        this.token = token;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect() {
        this.socket = new WebSocket(
            `ws://localhost:8000/ws/connect?token=${this.token}`
        );

        this.socket.onopen = (event) => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
        };

        this.socket.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
        };

        this.socket.onclose = (event) => {
            console.log('WebSocket disconnected');
            this.handleReconnect();
        };

        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    handleMessage(message) {
        switch (message.type) {
            case 'connected':
                console.log('Connection established:', message);
                break;
            case 'task_progress':
                this.handleTaskProgress(message.data);
                break;
            case 'notification':
                this.handleNotification(message);
                break;
            case 'system_message':
                this.handleSystemMessage(message);
                break;
            case 'subscription_confirmed':
                console.log('Subscribed to task:', message.task_id);
                break;
            case 'pong':
                console.log('Pong received');
                break;
        }
    }

    handleTaskProgress(progress) {
        // Update UI with task progress
        const progressBar = document.getElementById(`progress-${progress.summary_id}`);
        if (progressBar) {
            progressBar.style.width = `${progress.progress_percentage}%`;
            progressBar.textContent = `${progress.progress_percentage}% - ${progress.current_step}`;
        }
    }

    // Subscribe to task progress updates
    subscribeToTask(taskId) {
        this.send({
            type: 'subscribe_task',
            task_id: taskId
        });
    }

    // Unsubscribe from task progress updates
    unsubscribeFromTask(taskId) {
        this.send({
            type: 'unsubscribe_task',
            task_id: taskId
        });
    }

    // Send ping to keep connection alive
    ping() {
        this.send({ type: 'ping' });
    }

    send(message) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        }
    }

    handleReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff
            setTimeout(() => {
                console.log(`Reconnecting... Attempt ${this.reconnectAttempts}`);
                this.connect();
            }, delay);
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }
}
```

### Usage Example

```javascript
// Initialize WebSocket connection
const ws = new StudyAssistantWebSocket(userToken);
ws.connect();

// Subscribe to task progress when starting a summary
async function generateSummary(fileId, title) {
    const response = await fetch('/summaries/generate', {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${userToken}`,
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            file_id: fileId,
            title: title,
            summary_type: 'general'
        })
    });
    
    const result = await response.json();
    
    // Subscribe to real-time progress updates
    ws.subscribeToTask(result.task_id);
    
    return result;
}
```

## Message Types

### Incoming Messages (Server → Client)

#### Connection Established

```json
{
    "type": "connected",
    "message": "WebSocket connection established",
    "user_id": 123,
    "timestamp": "2025-01-14T02:42:00Z"
}
```

#### Task Progress Update

```json
{
    "type": "task_progress",
    "data": {
        "task_id": "task-uuid",
        "summary_id": "summary-uuid", 
        "status": "processing",
        "progress_percentage": 65,
        "current_step": "Generating summary with AI",
        "estimated_time_remaining": 45,
        "error_message": null
    },
    "timestamp": "2025-01-14T02:42:00Z"
}
```

#### User Notification

```json
{
    "type": "notification",
    "notification_type": "summary_completed",
    "message": "Your summary has been generated successfully!",
    "data": {
        "summary_id": "summary-uuid",
        "title": "My Document Summary"
    },
    "timestamp": "2025-01-14T02:42:00Z"
}
```

#### System Message

```json
{
    "type": "system_message",
    "message": "System maintenance scheduled for 3 AM UTC",
    "data": {
        "maintenance_time": "2025-01-15T03:00:00Z"
    },
    "timestamp": "2025-01-14T02:42:00Z"
}
```

### Outgoing Messages (Client → Server)

#### Subscribe to Task

```json
{
    "type": "subscribe_task",
    "task_id": "task-uuid"
}
```

#### Unsubscribe from Task

```json
{
    "type": "unsubscribe_task", 
    "task_id": "task-uuid"
}
```

#### Ping

```json
{
    "type": "ping"
}
```

## React Integration Example

```jsx
import { useState, useEffect, useRef } from 'react';

const useWebSocket = (token) => {
    const [isConnected, setIsConnected] = useState(false);
    const [taskProgress, setTaskProgress] = useState({});
    const wsRef = useRef(null);

    useEffect(() => {
        if (!token) return;

        const ws = new WebSocket(`ws://localhost:8000/ws/connect?token=${token}`);
        wsRef.current = ws;

        ws.onopen = () => {
            setIsConnected(true);
        };

        ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            
            if (message.type === 'task_progress') {
                setTaskProgress(prev => ({
                    ...prev,
                    [message.data.task_id]: message.data
                }));
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
        };

        return () => {
            ws.close();
        };
    }, [token]);

    const subscribeToTask = (taskId) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
                type: 'subscribe_task',
                task_id: taskId
            }));
        }
    };

    return { isConnected, taskProgress, subscribeToTask };
};

// Component usage
const SummaryGenerator = () => {
    const { isConnected, taskProgress, subscribeToTask } = useWebSocket(userToken);
    const [currentTask, setCurrentTask] = useState(null);

    const generateSummary = async () => {
        const response = await fetch('/summaries/generate', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${userToken}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_id: 'file-id',
                title: 'My Summary',
                summary_type: 'general'
            })
        });
        
        const result = await response.json();
        setCurrentTask(result.task_id);
        subscribeToTask(result.task_id);
    };

    const progress = currentTask ? taskProgress[currentTask] : null;

    return (
        <div>
            <div>Connection: {isConnected ? '🟢' : '🔴'}</div>
            <button onClick={generateSummary}>Generate Summary</button>
            
            {progress && (
                <div>
                    <div>Status: {progress.status}</div>
                    <div>Progress: {progress.progress_percentage}%</div>
                    <div>Step: {progress.current_step}</div>
                    <div className="progress-bar">
                        <div 
                            className="progress-fill"
                            style={{ width: `${progress.progress_percentage}%` }}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};
```

## Testing

### Test Page

Visit `http://localhost:8000/ws/test` for a simple WebSocket test interface (development only).

### Manual Testing with Browser Console

```javascript
// Connect to WebSocket
const token = "your-jwt-token";
const ws = new WebSocket(`ws://localhost:8000/ws/connect?token=${token}`);

ws.onmessage = (event) => {
    console.log('Received:', JSON.parse(event.data));
};

// Subscribe to a task
ws.send(JSON.stringify({
    type: 'subscribe_task',
    task_id: 'your-task-id'
}));

// Send ping
ws.send(JSON.stringify({ type: 'ping' }));
```

## Server-Side Usage

### Sending Progress Updates

```python
from app.websocket.manager import websocket_manager
from app.summaries.schemas import TaskProgressUpdate

# Send task progress update
progress_update = TaskProgressUpdate(
    task_id="task-uuid",
    summary_id="summary-uuid", 
    status="processing",
    progress_percentage=75,
    current_step="Finalizing summary"
)

await websocket_manager.send_task_progress("task-uuid", progress_update)
```

### Sending User Notifications

```python
# Send notification to specific user
await websocket_manager.send_user_notification(
    user_id=123,
    notification_type="summary_completed",
    message="Your summary is ready!",
    data={"summary_id": "summary-uuid"}
)
```

### Broadcasting System Messages

```python
# Broadcast to all connected users
await websocket_manager.broadcast_system_message(
    message="System maintenance in 10 minutes",
    data={"maintenance_time": "2025-01-15T03:00:00Z"}
)
```

## Connection Statistics

### GET /ws/stats

Returns WebSocket connection statistics:

```json
{
    "total_connections": 15,
    "users_connected": 8,
    "active_task_subscriptions": 3,
    "current_user_connections": 2,
    "connections_by_user": {
        "123": 2,
        "456": 1
    },
    "subscriptions_by_task": {
        "task-uuid-1": 2,
        "task-uuid-2": 1
    }
}
```

## Error Handling

### Connection Errors

- **4001**: Authentication failed - Invalid or expired JWT token
- **4002**: Invalid message format - Malformed JSON message
- **4003**: Authorization error - User not active or verified

### Client-Side Error Handling

```javascript
ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = (event) => {
    console.log(`Connection closed: ${event.code} - ${event.reason}`);
    
    switch (event.code) {
        case 4001:
            // Authentication failed - refresh token
            refreshTokenAndReconnect();
            break;
        case 4002:
            // Invalid message format
            console.error('Invalid message sent to server');
            break;
        default:
            // Normal closure or network error - attempt reconnect
            attemptReconnect();
    }
};
```

## Security Considerations

1. **Token Expiration**: WebSocket connections will be terminated when JWT tokens expire
2. **Rate Limiting**: Connections are monitored for excessive message sending
3. **User Isolation**: Users can only receive updates for their own tasks and data
4. **Connection Limits**: Maximum connections per user may be enforced
5. **Message Validation**: All incoming messages are validated for proper format

## Performance

- **Connection Pooling**: Efficient management of concurrent connections
- **Message Queuing**: Non-blocking message delivery with automatic cleanup
- **Memory Management**: Automatic cleanup of disconnected clients
- **Heartbeat**: Built-in ping/pong for connection health monitoring

## Troubleshooting

### Common Issues

1. **Connection Refused**: Check if WebSocket endpoint is enabled and JWT token is valid
2. **Messages Not Received**: Verify subscription to correct task ID
3. **Frequent Disconnections**: Check network stability and token expiration
4. **High Latency**: Monitor server load and WebSocket connection count

### Debugging

Enable debug logging to see WebSocket activity:

```python
import structlog
logger = structlog.get_logger("websocket")
logger.setLevel("DEBUG")
```

This will log all WebSocket connections, disconnections, and message handling.
