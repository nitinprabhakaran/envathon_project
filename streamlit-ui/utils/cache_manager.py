import os
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class AnalysisCache:
    """Cache for LLM analysis results to reduce API calls"""
    
    def __init__(self):
        """Initialize the cache using file system storage"""
        self.cache_dir = Path("/app/data/cache")
        self.ttl_hours = int(os.environ.get("CACHE_TTL_HOURS", 24))
        self.enabled = os.environ.get("ENABLE_CACHE", "true").lower() == "true"
        
        if self.enabled:
            os.makedirs(self.cache_dir, exist_ok=True)
            logger.info(f"AnalysisCache initialized with TTL: {self.ttl_hours} hours")
        else:
            logger.info("AnalysisCache disabled")
    
    def _get_cache_key(self, key: str) -> str:
        """Generate a safe filename from cache key"""
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get a value from cache if it exists and is not expired"""
        if not self.enabled:
            return None
        
        cache_file = self.cache_dir / f"{self._get_cache_key(key)}.json"
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, "r") as f:
                cache_data = json.load(f)
            
            # Check if cache is expired
            cached_at = datetime.fromisoformat(cache_data["cached_at"])
            if datetime.now() - cached_at > timedelta(hours=self.ttl_hours):
                logger.debug(f"Cache expired for key: {key}")
                cache_file.unlink()
                return None
            
            logger.info(f"Cache hit for key: {key}")
            return cache_data["data"]
        except Exception as e:
            logger.error(f"Error reading cache for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Store a value in the cache"""
        if not self.enabled:
            return False
        
        cache_file = self.cache_dir / f"{self._get_cache_key(key)}.json"
        try:
            cache_data = {
                "key": key,
                "data": value,
                "cached_at": datetime.now().isoformat()
            }
            
            with open(cache_file, "w") as f:
                json.dump(cache_data, f)
            
            logger.info(f"Cached data for key: {key}")
            return True
        except Exception as e:
            logger.error(f"Error writing cache for key {key}: {e}")
            return False
    
    def invalidate(self, key: str) -> bool:
        """Remove a specific key from cache"""
        if not self.enabled:
            return False
        
        cache_file = self.cache_dir / f"{self._get_cache_key(key)}.json"
        if cache_file.exists():
            try:
                cache_file.unlink()
                logger.info(f"Invalidated cache for key: {key}")
                return True
            except Exception as e:
                logger.error(f"Error invalidating cache for key {key}: {e}")
                return False
        return False
    
    def clear(self) -> int:
        """Clear all cached data, returns number of files removed"""
        if not self.enabled:
            return 0
        
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                cache_file.unlink()
                count += 1
            except Exception as e:
                logger.error(f"Error removing cache file {cache_file}: {e}")
        
        logger.info(f"Cleared {count} cache files")
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled:
            return {"enabled": False}
        
        try:
            files = list(self.cache_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in files) / (1024 * 1024)  # MB
            
            return {
                "enabled": True,
                "files": len(files),
                "size_mb": round(total_size, 2),
                "ttl_hours": self.ttl_hours
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"enabled": True, "error": str(e)}