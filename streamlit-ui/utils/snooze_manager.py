import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Set
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class SnoozeManager:
    """Manages snoozed projects and branches"""
    
    def __init__(self):
        """Initialize the snooze manager"""
        self.snooze_file = Path("/app/data/snooze/snoozes.json")
        os.makedirs(self.snooze_file.parent, exist_ok=True)
        
        # Initialize file if it doesn't exist
        if not self.snooze_file.exists():
            with open(self.snooze_file, "w") as f:
                json.dump([], f)
        
        logger.info(f"SnoozeManager initialized at {self.snooze_file}")
    
    def snooze_project(self, project_id: str, branch: str = "main", hours: int = 8) -> bool:
        """Snooze a project branch for the specified number of hours"""
        try:
            snoozes = self._read_snoozes()
            
            # Remove any existing snooze for this project/branch
            snoozes = [s for s in snoozes 
                      if not (s["project_id"] == project_id and s["branch"] == branch)]
            
            # Add new snooze
            expiry = datetime.now() + timedelta(hours=hours)
            snoozes.append({
                "project_id": project_id,
                "branch": branch,
                "snoozed_at": datetime.now().isoformat(),
                "expires_at": expiry.isoformat(),
                "hours": hours
            })
            
            # Save updated snoozes
            self._write_snoozes(snoozes)
            logger.info(f"Snoozed project {project_id} branch {branch} for {hours} hours")
            
            return True
        except Exception as e:
            logger.error(f"Error snoozing project {project_id}: {e}")
            return False
    
    def is_snoozed(self, project_id: str, branch: str = "main") -> bool:
        """Check if a project branch is currently snoozed"""
        try:
            snoozes = self._read_snoozes()
            now = datetime.now()
            
            for snooze in snoozes:
                if snooze["project_id"] == project_id and snooze["branch"] == branch:
                    expires_at = datetime.fromisoformat(snooze["expires_at"])
                    if expires_at > now:
                        logger.debug(f"Project {project_id} branch {branch} is snoozed until {expires_at}")
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error checking snooze for project {project_id}: {e}")
            return False
    
    def get_active_snoozes(self) -> List[Dict]:
        """Get all active snoozes"""
        try:
            snoozes = self._read_snoozes()
            now = datetime.now()
            
            active_snoozes = []
            for snooze in snoozes:
                expires_at = datetime.fromisoformat(snooze["expires_at"])
                if expires_at > now:
                    # Add remaining time
                    remaining = expires_at - now
                    snooze["remaining_hours"] = round(remaining.total_seconds() / 3600, 1)
                    active_snoozes.append(snooze)
            
            return active_snoozes
        except Exception as e:
            logger.error(f"Error getting active snoozes: {e}")
            return []
    
    def get_active_count(self) -> int:
        """Get count of active snoozes"""
        return len(self.get_active_snoozes())
    
    def unsnooze_project(self, project_id: str, branch: str = "main") -> bool:
        """Remove snooze for a project branch"""
        try:
            snoozes = self._read_snoozes()
            
            # Filter out the snooze
            original_count = len(snoozes)
            snoozes = [s for s in snoozes 
                      if not (s["project_id"] == project_id and s["branch"] == branch)]
            
            if len(snoozes) < original_count:
                self._write_snoozes(snoozes)
                logger.info(f"Unsnoozed project {project_id} branch {branch}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Error unsnoozing project {project_id}: {e}")
            return False
    
    def cleanup_expired_snoozes(self) -> int:
        """Remove expired snoozes, returns number removed"""
        try:
            snoozes = self._read_snoozes()
            now = datetime.now()
            
            active_snoozes = []
            expired_count = 0
            
            for snooze in snoozes:
                expires_at = datetime.fromisoformat(snooze["expires_at"])
                if expires_at > now:
                    active_snoozes.append(snooze)
                else:
                    expired_count += 1
            
            if expired_count > 0:
                self._write_snoozes(active_snoozes)
                logger.info(f"Cleaned up {expired_count} expired snoozes")
            
            return expired_count
        except Exception as e:
            logger.error(f"Error cleaning up snoozes: {e}")
            return 0
    
    def _read_snoozes(self) -> List[Dict]:
        """Read snoozes from file"""
        try:
            with open(self.snooze_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading snoozes: {e}")
            return []
    
    def _write_snoozes(self, snoozes: List[Dict]):
        """Write snoozes to file"""
        try:
            with open(self.snooze_file, "w") as f:
                json.dump(snoozes, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing snoozes: {e}")