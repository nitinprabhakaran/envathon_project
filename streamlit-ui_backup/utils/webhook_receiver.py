import os
import logging
import json
from typing import Dict, Any, List
import redis

logger = logging.getLogger(__name__)

class WebhookReceiver:
    """Receives and manages webhook events for Streamlit UI"""

    def __init__(self):
        self.redis_host = os.environ.get("REDIS_HOST", "redis")
        self.redis_port = int(os.environ.get("REDIS_PORT", 6379))
        self.redis = redis.Redis(host=self.redis_host, port=self.redis_port, decode_responses=True)
        logger.info(f"WebhookReceiver connected to Redis at {self.redis_host}:{self.redis_port}")

    def get_gitlab_failures(self) -> List[Dict[str, Any]]:
        """Fetch all pending GitLab pipeline failures from Redis"""
        failures = []
        while True:
            failure_json = self.redis.rpop('gitlab_failures')
            if not failure_json:
                break
            try:
                failures.append(json.loads(failure_json))
            except Exception as e:
                logger.error(f"Error parsing GitLab failure: {e}")
        return failures

    def get_sonarqube_issues(self) -> List[Dict[str, Any]]:
        """Fetch all pending SonarQube issues from Redis"""
        issues = []
        while True:
            issue_json = self.redis.rpop('sonarqube_issues')
            if not issue_json:
                break
            try:
                issues.append(json.loads(issue_json))
            except Exception as e:
                logger.error(f"Error parsing SonarQube issue: {e}")
        return issues

    def store_event(self, event_type: str, event_data: Dict[str, Any]):
        """Store a generic event in Redis (for future extensibility)"""
        key = f"{event_type}_events"
        self.redis.lpush(key, json.dumps(event_data))
        logger.info(f"Stored event in {key}: {event_data.get('project_name', '')}")

    def health(self) -> bool:
        """Check if Redis is reachable"""
        try:
            return self.redis.ping()
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False