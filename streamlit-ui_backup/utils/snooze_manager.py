import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional

class SnoozeManager:
    def __init__(self, snooze_dir: str = "/app/snooze"):
        self.snooze_dir = snooze_dir
        os.makedirs(snooze_dir, exist_ok=True)
        self.snooze_file = os.path.join(snooze_dir, "snooze_data.json")
        self._load_snooze_data()
    
    def _load_snooze_data(self):
        """Load snooze data from file"""
        if os.path.exists(self.snooze_file):
            with open(self.snooze_file, 'r') as f:
                self.snooze_data = json.load(f)
        else:
            self.snooze_data = {}
    
    def _save_snooze_data(self):
        """Save snooze data to file"""
        with open(self.snooze_file, 'w') as f:
            json.dump(self.snooze_data, f)
    
    def snooze_project(self, project_id: int, branch: str, hours: int):
        """Snooze alerts for a project/branch combination"""
        key = f"{project_id}_{branch}"
        snooze_until = datetime.now() + timedelta(hours=hours)
        
        self.snooze_data[key] = {
            "project_id": project_id,
            "branch": branch,
            "snoozed_at": datetime.now().isoformat(),
            "snooze_until": snooze_until.isoformat(),
            "hours": hours
        }
        
        self._save_snooze_data()
    
    def is_snoozed(self, project_id: int, branch: str) -> bool:
        """Check if a project/branch is currently snoozed"""
        key = f"{project_id}_{branch}"
        
        if key in self.snooze_data:
            snooze_until = datetime.fromisoformat(self.snooze_data[key]["snooze_until"])
            if datetime.now() < snooze_until:
                return True
            else:
                # Remove expired snooze
                del self.snooze_data[key]
                self._save_snooze_data()
        
        return False
    
    def get_snooze_info(self, project_id: int, branch: str) -> Optional[Dict]:
        """Get snooze information for a project/branch"""
        key = f"{project_id}_{branch}"
        
        if key in self.snooze_data and self.is_snoozed(project_id, branch):
            return self.snooze_data[key]
        
        return None
    
    def remove_snooze(self, project_id: int, branch: str):
        """Remove snooze for a project/branch"""
        key = f"{project_id}_{branch}"
        
        if key in self.snooze_data:
            del self.snooze_data[key]
            self._save_snooze_data()
    
    def cleanup_expired_snoozes(self):
        """Remove all expired snoozes"""
        current_time = datetime.now()
        keys_to_remove = []
        
        for key, data in self.snooze_data.items():
            snooze_until = datetime.fromisoformat(data["snooze_until"])
            if current_time >= snooze_until:
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.snooze_data[key]
        
        if keys_to_remove:
            self._save_snooze_data()