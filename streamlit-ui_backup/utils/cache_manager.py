import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class AnalysisCache:
    def __init__(self, cache_dir: str = "/app/cache", ttl_hours: int = 24):
        self.cache_dir = cache_dir
        self.ttl_hours = ttl_hours
        os.makedirs(cache_dir, exist_ok=True)
        self.stats = {"hits": 0, "misses": 0}
    
    def _get_cache_key(self, data: Dict) -> str:
        """Generate cache key from data"""
        # Create a stable string representation
        key_data = {
            "project_id": data.get("project_id"),
            "pipeline_id": data.get("pipeline_id"),
            "commit_sha": data.get("commit_sha", data.get("commit", {}).get("sha"))
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Dict]:
        """Get cached analysis"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                # Check if cache is still valid
                cached_time = datetime.fromisoformat(cached_data["cached_at"])
                if datetime.now() - cached_time < timedelta(hours=self.ttl_hours):
                    self.stats["hits"] += 1
                    logger.info(f"Cache hit for key: {key}")
                    return cached_data["data"]
                else:
                    # Cache expired
                    os.remove(cache_file)
                    logger.info(f"Cache expired for key: {key}")
            except Exception as e:
                logger.error(f"Error reading cache: {e}")
        
        self.stats["misses"] += 1
        return None
    
    def set(self, key: str, data: Dict):
        """Save analysis to cache"""
        cache_file = os.path.join(self.cache_dir, f"{key}.json")
        
        try:
            cache_data = {
                "cached_at": datetime.now().isoformat(),
                "data": data
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f)
            logger.info(f"Cached analysis for key: {key}")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def clear(self):
        """Clear all cache"""
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                os.remove(os.path.join(self.cache_dir, filename))
        self.stats = {"hits": 0, "misses": 0}
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        cache_size = sum(
            os.path.getsize(os.path.join(self.cache_dir, f))
            for f in os.listdir(self.cache_dir)
            if f.endswith('.json')
        ) / (1024 * 1024)  # Convert to MB
        
        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "size": round(cache_size, 2),
            "files": len([f for f in os.listdir(self.cache_dir) if f.endswith('.json')])
        }