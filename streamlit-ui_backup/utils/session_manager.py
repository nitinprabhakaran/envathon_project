import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any

class SessionManager:
    def __init__(self, session_dir: str = "/app/sessions"):
        self.session_dir = session_dir
        os.makedirs(session_dir, exist_ok=True)
    
    def create_session(self) -> str:
        """Create a new session"""
        session_id = str(uuid.uuid4())
        session_data = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "messages": []
        }
        
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        with open(session_path, 'w') as f:
            json.dump(session_data, f)
        
        return session_id
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session data"""
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_path):
            with open(session_path, 'r') as f:
                return json.load(f)
        return None
    
    def update_session(self, session_id: str, data: Dict[str, Any]):
        """Update session data"""
        session_path = os.path.join(self.session_dir, f"{session_id}.json")
        if os.path.exists(session_path):
            data["last_active"] = datetime.now().isoformat()
            with open(session_path, 'w') as f:
                json.dump(data, f)
    
    def add_message(self, session_id: str, message: Dict[str, Any]):
        """Add message to session"""
        session = self.get_session(session_id)
        if session:
            session["messages"].append(message)
            self.update_session(session_id, session)
    
    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Get messages from session"""
        session = self.get_session(session_id)
        return session["messages"] if session else []
    
    def get_active_sessions(self, hours: int = 3) -> List[Dict[str, Any]]:
        """Get active sessions within the last N hours"""
        active_sessions = []
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for filename in os.listdir(self.session_dir):
            if filename.endswith('.json'):
                session_path = os.path.join(self.session_dir, filename)
                with open(session_path, 'r') as f:
                    session = json.load(f)
                    last_active = datetime.fromisoformat(session["last_active"])
                    if last_active > cutoff_time:
                        active_sessions.append(session)
        
        return sorted(active_sessions, key=lambda x: x["last_active"], reverse=True)
    
    def cleanup_old_sessions(self, hours: int = 3):
        """Remove sessions older than N hours"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        for filename in os.listdir(self.session_dir):
            if filename.endswith('.json'):
                session_path = os.path.join(self.session_dir, filename)
                with open(session_path, 'r') as f:
                    session = json.load(f)
                    last_active = datetime.fromisoformat(session["last_active"])
                    if last_active < cutoff_time:
                        os.remove(session_path)