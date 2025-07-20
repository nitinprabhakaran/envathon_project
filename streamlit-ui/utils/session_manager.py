import json
import os
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages user sessions and analysis history"""
    
    def __init__(self):
        """Initialize the session manager"""
        self.sessions_dir = Path("/app/data/sessions")
        os.makedirs(self.sessions_dir, exist_ok=True)
        logger.info(f"SessionManager initialized at {self.sessions_dir}")
    
    def create_session(self, session_id: str = None) -> str:
        """Create a new session and return its ID"""
        if not session_id:
            session_id = str(uuid.uuid4())
        
        session_file = self.sessions_dir / f"{session_id}.json"
        
        session_data = {
            "id": session_id,
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
            "messages": []
        }
        
        try:
            with open(session_file, "w") as f:
                json.dump(session_data, f)
            
            logger.info(f"Created new session: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return str(uuid.uuid4())
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session data by ID"""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            logger.warning(f"Session not found: {session_id}")
            return {
                "id": session_id,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "messages": []
            }
        
        try:
            with open(session_file, "r") as f:
                session_data = json.load(f)
            
            return session_data
        except Exception as e:
            logger.error(f"Error reading session {session_id}: {e}")
            return {
                "id": session_id,
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat(),
                "messages": []
            }
    
    def update_session_activity(self, session_id: str) -> bool:
        """Update the last_active timestamp of a session"""
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            logger.warning(f"Cannot update non-existent session: {session_id}")
            return False
        
        try:
            with open(session_file, "r") as f:
                session_data = json.load(f)
            
            session_data["last_active"] = datetime.now().isoformat()
            
            with open(session_file, "w") as f:
                json.dump(session_data, f)
            
            return True
        except Exception as e:
            logger.error(f"Error updating session activity {session_id}: {e}")
            return False
    
    def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Add a message to a session's history"""
        session_file = self.sessions_dir / f"{session_id}.json"
        
        # Create session if it doesn't exist
        if not session_file.exists():
            self.create_session(session_id)
        
        try:
            with open(session_file, "r") as f:
                session_data = json.load(f)
            
            # Add timestamp if not present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now().isoformat()
            
            session_data["messages"].append(message)
            session_data["last_active"] = datetime.now().isoformat()
            
            with open(session_file, "w") as f:
                json.dump(session_data, f)
            
            logger.debug(f"Added message to session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error adding message to session {session_id}: {e}")
            return False
    
    def get_active_sessions(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get all sessions active within the last N hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        active_sessions = []
        
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, "r") as f:
                    session_data = json.load(f)
                
                last_active = datetime.fromisoformat(session_data["last_active"])
                if last_active >= cutoff:
                    active_sessions.append(session_data)
            except Exception as e:
                logger.error(f"Error reading session file {session_file}: {e}")
        
        return active_sessions
    
    def cleanup_old_sessions(self, hours: int = 72) -> int:
        """Remove sessions older than the specified hours"""
        cutoff = datetime.now() - timedelta(hours=hours)
        count = 0
        
        for session_file in self.sessions_dir.glob("*.json"):
            try:
                with open(session_file, "r") as f:
                    session_data = json.load(f)
                
                last_active = datetime.fromisoformat(session_data["last_active"])
                if last_active < cutoff:
                    session_file.unlink()
                    count += 1
            except Exception as e:
                logger.error(f"Error cleaning up session file {session_file}: {e}")
        
        if count > 0:
            logger.info(f"Cleaned up {count} old sessions")
        
        return count