from flask import Flask, request, jsonify
import os
import json
import logging
import redis
from datetime import datetime
import threading
from typing import Dict, Any

app = Flask(__name__)

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
logger = logging.getLogger("webhook-handler")

# Redis configuration
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

def push_event_to_redis(event_data: Dict[str, Any], list_name: str):
    """Push event to Redis for Streamlit UI polling"""
    try:
        event_data['timestamp'] = datetime.utcnow().isoformat()
        redis_client.lpush(list_name, json.dumps(event_data))
        logger.info(f"Event pushed to Redis list '{list_name}': {event_data}")
    except Exception as e:
        logger.error(f"Error pushing event to Redis: {e}")

@app.route('/webhook/gitlab', methods=['POST'])
def gitlab_webhook():
    """Handle GitLab webhook events"""
    event_type = request.headers.get('X-Gitlab-Event')
    data = request.json
    logger.info(f"Received GitLab event: {event_type}")

    if event_type == 'Pipeline Hook':
        if data.get('object_attributes', {}).get('status') == 'failed':
            pipeline_data = {
                'event_type': 'pipeline_failure',
                'project_id': data['project']['id'],
                'project_name': data['project']['name'],
                'pipeline_id': data['object_attributes']['id'],
                'ref': data['object_attributes']['ref'],
                'sha': data['object_attributes']['sha'],
                'source': data['object_attributes']['source'],
                'created_at': data['object_attributes']['created_at'],
                'user': {
                    'name': data['user']['name'],
                    'username': data['user']['username'],
                    'email': data['user']['email']
                },
                'commit': {
                    'id': data['commit']['id'],
                    'message': data['commit']['message'],
                    'author': data['commit']['author']
                }
            }
            threading.Thread(target=push_event_to_redis, args=(pipeline_data, 'gitlab_failures')).start()
            logger.info("GitLab pipeline failure event processed and pushed to Redis.")
    elif event_type == 'Push Hook':
        logger.info("Received GitLab push event (not processed).")
    else:
        logger.info("Received other GitLab event (not processed).")

    return jsonify({"status": "received"}), 200

@app.route('/webhook/sonarqube', methods=['POST'])
def sonarqube_webhook():
    """Handle SonarQube webhook events"""
    data = request.json
    logger.info("Received SonarQube event.")

    if data.get('status') == 'FAILURE':
        analysis_data = {
            'event_type': 'quality_gate_failure',
            'project_key': data['project']['key'],
            'project_name': data['project']['name'],
            'task_id': data['taskId'],
            'analyzed_at': data['analysedAt'],
            'quality_gate': {
                'status': data['qualityGate']['status'],
                'conditions': data['qualityGate'].get('conditions', [])
            },
            'branch': data.get('branch', {}).get('name', 'main')
        }
        threading.Thread(target=push_event_to_redis, args=(analysis_data, 'sonarqube_issues')).start()
        logger.info("SonarQube failure event processed and pushed to Redis.")

    return jsonify({"status": "received"}), 200

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)