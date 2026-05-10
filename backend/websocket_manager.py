import socketio
from typing import Dict, Set

class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[str]] = {}  # workflow_id -> set of session_ids
        self.user_sessions: Dict[str, str] = {}  # session_id -> user_id
    
    async def connect(self, session_id: str):
        """Handle new WebSocket connection"""
        print(f"WebSocket connected: {session_id}")
    
    async def disconnect(self, session_id: str):
        """Handle WebSocket disconnection"""
        # Remove from all workflow rooms
        for workflow_id, sessions in self.active_connections.items():
            sessions.discard(session_id)
        
        # Remove user session
        if session_id in self.user_sessions:
            del self.user_sessions[session_id]
        
        print(f"WebSocket disconnected: {session_id}")
    
    async def join_workflow(self, session_id: str, workflow_id: str):
        """Join a workflow room for real-time updates"""
        if workflow_id not in self.active_connections:
            self.active_connections[workflow_id] = set()
        
        self.active_connections[workflow_id].add(session_id)
        print(f"Session {session_id} joined workflow {workflow_id}")
    
    async def leave_workflow(self, session_id: str, workflow_id: str):
        """Leave a workflow room"""
        if workflow_id in self.active_connections:
            self.active_connections[workflow_id].discard(session_id)
    
    async def broadcast_to_workflow(self, workflow_id: str, event: str, data: dict):
        """Broadcast message to all sessions in a workflow room"""
        if workflow_id in self.active_connections:
            for session_id in self.active_connections[workflow_id]:
                # In a real implementation, you'd emit to the specific session
                # This is a placeholder for the Socket.IO integration
                print(f"Broadcasting {event} to session {session_id} in workflow {workflow_id}: {data}")

# Global instance
websocket_manager = WebSocketManager()