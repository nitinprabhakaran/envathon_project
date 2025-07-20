import os
import logging
import json
from typing import Dict, Any, List
import redis
import time

logger = logging.getLogger(__name__)

class WebhookReceiver:
    """Receives and manages webhook events for Streamlit UI"""

    def __init__(self):
        """Initialize the webhook receiver with Redis connection"""
        self.redis_host = os.environ.get("REDIS_HOST", "redis")
        self.redis_port = int(os.environ.get("REDIS_PORT", 6379))
        self.redis_client = None
        self._connect_redis()
    
    def _connect_redis(self) -> bool:
        """Connect to Redis with retry logic"""
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.redis_client = redis.Redis(
                    host=self.redis_host, 
                    port=self.redis_port, 
                    decode_responses=True
                )
                self.redis_client.ping()
                logger.info(f"WebhookReceiver connected to Redis at {self.redis_host}:{self.redis_port}")
                return True
            except redis.ConnectionError as e:
                retry_count += 1
                logger.warning(f"Redis connection attempt {retry_count}/{max_retries} failed: {e}")
                time.sleep(2)
        
        logger.error(f"Failed to connect to Redis after {max_retries} attempts")
        return False

    def get_gitlab_failures(self) -> List[Dict[str, Any]]:
        """Fetch all pending GitLab pipeline failures from Redis"""
        if not self.redis_client:
            logger.error("Redis client not available")
            return []
        
        failures = []
        try:
            # Get all failures from the list
            while True:
                failure_json = self.redis_client.rpop('gitlab_failures')
                if not failure_json:
                    break
                
                try:
                    failure_data = json.loads(failure_json)
                    # Add timestamp if not present
                    if 'timestamp' not in failure_data:
                        failure_data['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    failures.append(failure_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing GitLab failure JSON: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching GitLab failures: {e}")
        
        if failures:
            logger.info(f"Retrieved {len(failures)} GitLab failures")
        
        return failures

    def get_sonarqube_issues(self) -> List[Dict[str, Any]]:
        """Fetch all pending SonarQube issues from Redis"""
        if not self.redis_client:
            logger.error("Redis client not available")
            return []
        
        issues = []
        try:
            # Get all issues from the list
            while True:
                issue_json = self.redis_client.rpop('sonarqube_issues')
                if not issue_json:
                    break
                
                try:
                    issue_data = json.loads(issue_json)
                    # Add timestamp if not present
                    if 'timestamp' not in issue_data:
                        issue_data['timestamp'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    issues.append(issue_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing SonarQube issue JSON: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching SonarQube issues: {e}")
        
        if issues:
            logger.info(f"Retrieved {len(issues)} SonarQube issues")
        
        return issues

    def get_events_by_type(self, event_type: str) -> List[Dict[str, Any]]:
        """Fetch events of a specific type from Redis"""
        if not self.redis_client:
            logger.error("Redis client not available")
            return []
        
        events = []
        key = f"{event_type}_events"
        try:
            while True:
                event_json = self.redis_client.rpop(key)
                if not event_json:
                    break
                
                try:
                    events.append(json.loads(event_json))
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing {event_type} event JSON: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error fetching {event_type} events: {e}")
        
        return events

    def store_event(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """Store a generic event in Redis (for testing purposes)"""
        if not self.redis_client:
            logger.error("Redis client not available")
            return False
        
        key = f"{event_type}_events"
        try:
            self.redis_client.lpush(key, json.dumps(event_data))
            logger.info(f"Stored {event_type} event: {event_data.get('id', '')}")
            return True
        except Exception as e:
            logger.error(f"Error storing {event_type} event: {e}")
            return False

    def health(self) -> bool:
        """Check if Redis is reachable"""
        if not self.redis_client:
            return self._connect_redis()
        
        try:
            return bool(self.redis_client.ping())
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            # Try to reconnect
            return self._connect_redis()
    
    def get_queue_lengths(self) -> Dict[str, int]:
        """Get the current lengths of all queues"""
        if not self.redis_client:
            return {}
        
        try:
            return {
                "gitlab_failures": self.redis_client.llen("gitlab_failures"),
                "sonarqube_issues": self.redis_client.llen("sonarqube_issues")
            }
        except Exception as e:
            logger.error(f"Error getting queue lengths: {e}")
            return {}