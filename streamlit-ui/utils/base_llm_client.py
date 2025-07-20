from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import httpx
import json
import uuid
import os
import logging

logger = logging.getLogger(__name__)

class BaseLLMClient(ABC):
    """Base class for all LLM clients"""
    
    def __init__(self):
        self.gitlab_mcp_url = os.environ.get("GITLAB_MCP_URL", "http://gitlab-mcp:8000")
        self.sonarqube_mcp_url = os.environ.get("SONARQUBE_MCP_URL", "http://sonarqube-mcp:8000")
        self.min_confidence = int(os.environ.get("MIN_CONFIDENCE_THRESHOLD", "80"))
        # Session IDs for MCP connections
        self.mcp_sessions = {}
    
    @abstractmethod
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Analyze pipeline failure and return analysis"""
        pass
    
    @abstractmethod
    async def analyze_sonarqube_issues(self, project_key: str, severity_threshold: str = "MAJOR") -> Dict:
        """Analyze SonarQube issues and suggest fixes"""
        pass
    
    @abstractmethod
    async def chat(self, user_input: str, chat_history: List[Dict]) -> str:
        """Chat interface for general queries"""
        pass
    
    async def get_mcp_session(self, mcp_url: str) -> str:
        """Get or create an MCP session"""
        if mcp_url not in self.mcp_sessions:
            self.mcp_sessions[mcp_url] = str(uuid.uuid4())
        return self.mcp_sessions[mcp_url]
    
    async def call_mcp_tool(self, mcp_url: str, tool_name: str, args: Dict) -> Dict:
        """Call MCP tool via HTTP using JSON-RPC format with session support"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Get or create session ID
            session_id = await self.get_mcp_session(mcp_url)
            
            # FastMCP HTTP uses JSON-RPC format
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": args
                },
                "id": 1
            }
            
            try:
                # Add /mcp/ to the URL if not present
                full_url = f"{mcp_url}/mcp/" if not mcp_url.endswith('/mcp/') else mcp_url
                
                # Include SSE headers and session ID
                headers = {
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "X-Session-ID": session_id
                }
                
                response = await client.post(
                    full_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                # Handle SSE response
                if response.headers.get("content-type", "").startswith("text/event-stream"):
                    # Parse SSE stream
                    result = None
                    for line in response.text.split('\n'):
                        if line.startswith('data: '):
                            data = line[6:]  # Remove 'data: ' prefix
                            if data.strip():
                                try:
                                    json_data = json.loads(data)
                                    if "result" in json_data:
                                        result = json_data
                                        break
                                except json.JSONDecodeError:
                                    continue
                    
                    if result and "error" in result:
                        logger.error(f"MCP Error: {result['error']}")
                        raise Exception(f"MCP Error: {result['error']}")
                    
                    return result.get("result", {}) if result else {}
                else:
                    # Regular JSON response
                    result = response.json()
                    if "error" in result:
                        logger.error(f"MCP Error: {result['error']}")
                        raise Exception(f"MCP Error: {result['error']}")
                    
                    return result.get("result", {})
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error calling MCP: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Error calling MCP tool {tool_name}: {str(e)}")
                raise
    
    def get_system_prompt(self) -> str:
        """Get the system prompt for the LLM"""
        return """You are an expert DevOps engineer analyzing CI/CD pipeline failures and code quality issues.

When analyzing failures:
1. First, identify the root cause from the error logs
2. Then, examine the code changes that triggered the failure
3. Provide specific fixes with code snippets
4. Rate your confidence (0-100) based on how certain you are about the fix
5. If confidence is low, explain what additional context would help

Always return your analysis in this JSON format:
{
    "root_cause": "Clear explanation of what caused the failure",
    "affected_files": ["list", "of", "files"],
    "fixes": [
        {
            "file_path": "path/to/file",
            "description": "What to fix",
            "code_snippet": "The actual fix",
            "line_numbers": [start, end],
            "explanation": "Why this fixes the issue"
        }
    ],
    "confidence": 85,
    "reasoning": "Why you're confident or not",
    "additional_context_needed": ["what else would help"]
}"""
    
    def parse_llm_response(self, response_text: str) -> Dict:
        """Parse LLM response, extracting JSON if present"""
        try:
            # Try to find JSON in the response
            import re
            
            # Look for JSON blocks in various formats
            json_patterns = [
                r'```json\s*(.*?)\s*```',  # JSON in code blocks
                r'```\s*(.*?)\s*```',       # Code blocks without language
                r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'  # Raw JSON
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, response_text, re.DOTALL)
                if matches:
                    for match in matches:
                        try:
                            # Clean the match
                            json_str = match.strip()
                            # Try to parse it
                            parsed = json.loads(json_str)
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            continue
            
            # If no JSON found, structure the response
            return {
                "root_cause": "Unable to parse structured response",
                "response_text": response_text,
                "confidence": 50,
                "fixes": [],
                "reasoning": "Response was not in expected JSON format"
            }
            
        except Exception as e:
            logger.error(f"Error parsing LLM response: {e}")
            return {
                "error": str(e),
                "response_text": response_text,
                "confidence": 0
            }