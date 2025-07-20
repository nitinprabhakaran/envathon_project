import os
import json
import anthropic
from typing import Dict, List, Any, Optional
from .base_llm_client import BaseLLMClient
import logging

logger = logging.getLogger(__name__)

class ClaudeClient(BaseLLMClient):
    def __init__(self):
        super().__init__()
        # Initialize Anthropic client
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = os.environ.get("CLAUDE_MODEL", "claude-3-opus-20240229")
        logger.info(f"Initialized Claude client with model: {self.model}")
    
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Analyze pipeline failure using Claude"""
        try:
            # Get pipeline details from GitLab MCP
            pipeline_details = await self.call_mcp_tool(
                self.gitlab_mcp_url,
                "get_pipeline_failure_details",
                {
                    "project_id": failure_data.get("project_id"),
                    "pipeline_id": failure_data.get("pipeline_id")
                }
            )
            
            # Get code context - progressive loading
            context = await self.call_mcp_tool(
                self.gitlab_mcp_url,
                "get_progressive_context",
                {
                    "project_id": failure_data.get("project_id"),
                    "pipeline_id": failure_data.get("pipeline_id"),
                    "commit_sha": failure_data.get("commit", {}).get("sha", ""),
                    "context_level": "diff"  # Start with just the diff
                }
            )
            
            # Build prompt
            prompt = f"""Analyze this CI/CD pipeline failure and provide specific fixes.

Pipeline Details:
{json.dumps(pipeline_details, indent=2)}

Code Context:
{json.dumps(context, indent=2)}

Failure Data:
{json.dumps(failure_data, indent=2)}

{self.get_system_prompt()}

Remember to:
1. Identify the exact root cause from the error logs
2. Provide specific code fixes that will resolve the issue
3. Rate your confidence based on how certain you are
4. List any additional context that would increase your confidence
"""

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            analysis = self.parse_llm_response(response.content[0].text)
            analysis["llm_provider"] = "claude"
            analysis["model"] = self.model
            
            # If confidence is low, request more context
            if analysis.get("confidence", 0) < 70:
                logger.info(f"Low confidence ({analysis['confidence']}%), requesting more context")
                # Get full file context
                more_context = await self.call_mcp_tool(
                    self.gitlab_mcp_url,
                    "get_progressive_context",
                    {
                        "project_id": failure_data.get("project_id"),
                        "pipeline_id": failure_data.get("pipeline_id"),
                        "commit_sha": failure_data.get("commit", {}).get("sha", ""),
                        "context_level": "full_files"
                    }
                )
                
                # Re-analyze with more context
                enhanced_prompt = f"{prompt}\n\nAdditional Context:\n{json.dumps(more_context, indent=2)}"
                enhanced_response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    messages=[
                        {"role": "user", "content": enhanced_prompt}
                    ]
                )
                analysis = self.parse_llm_response(enhanced_response.content[0].text)
                analysis["llm_provider"] = "claude"
                analysis["model"] = self.model
                analysis["context_level"] = "enhanced"
            
            return analysis
            
        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")
            return {
                "error": str(e),
                "root_cause": "Analysis failed",
                "confidence": 0,
                "llm_provider": "claude"
            }
    
    async def analyze_sonarqube_issues(self, project_key: str, severity_threshold: str = "MAJOR") -> Dict:
        """Analyze SonarQube issues using Claude"""
        try:
            # Get issues from SonarQube MCP
            issues = await self.call_mcp_tool(
                self.sonarqube_mcp_url,
                "get_project_issues",
                {
                    "project_key": project_key,
                    "severity": severity_threshold
                }
            )
            
            # Get quality gate status
            quality_gate = await self.call_mcp_tool(
                self.sonarqube_mcp_url,
                "get_quality_gate_status",
                {"project_key": project_key}
            )
            
            # Get code snippets for top issues
            code_contexts = []
            for issue in issues[:5]:  # Top 5 issues
                try:
                    context = await self.call_mcp_tool(
                        self.sonarqube_mcp_url,
                        "get_issue_context",
                        {
                            "issue_key": issue.get("key"),
                            "lines_before": 10,
                            "lines_after": 10
                        }
                    )
                    code_contexts.append(context)
                except:
                    pass
            
            # Build prompt
            prompt = f"""Analyze these SonarQube quality issues and provide specific fixes.

Project: {project_key}
Quality Gate Status: {quality_gate}

Issues:
{json.dumps(issues, indent=2)}

Code Contexts:
{json.dumps(code_contexts, indent=2)}

Provide specific fixes for the top issues. Return analysis in JSON format:
{{
    "summary": "Overall assessment of code quality",
    "quality_gate_status": "PASSED/FAILED",
    "fixes": [
        {{
            "issue_key": "key",
            "file_path": "path",
            "line": 123,
            "description": "What to fix",
            "code_snippet": "The fixed code",
            "explanation": "Why this fixes the issue",
            "language": "java/python/etc"
        }}
    ],
    "confidence": 85,
    "overall_confidence": 85,
    "recommendations": ["list of general recommendations"]
}}"""

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            analysis = self.parse_llm_response(response.content[0].text)
            analysis["llm_provider"] = "claude"
            
            return analysis
            
        except Exception as e:
            logger.error(f"SonarQube analysis failed: {e}")
            return {
                "error": str(e),
                "summary": "Analysis failed",
                "quality_gate_status": "UNKNOWN",
                "fixes": [],
                "overall_confidence": 0,
                "llm_provider": "claude"
            }
    
    async def chat(self, user_input: str, chat_history: List[Dict]) -> str:
        """Chat interface using Claude"""
        try:
            # Build conversation context
            messages = []
            for msg in chat_history[-10:]:  # Last 10 messages
                role = "user" if msg["role"] == "user" else "assistant"
                messages.append({
                    "role": role,
                    "content": msg["content"]
                })
            
            # Add current message
            messages.append({
                "role": "user",
                "content": user_input
            })
            
            # System prompt for chat
            system_prompt = """You are a helpful DevOps AI assistant. You help with:
- Analyzing CI/CD pipeline failures
- Understanding code quality issues
- Suggesting fixes and improvements
- Explaining DevOps best practices

Provide clear, specific advice with code examples when appropriate.
When discussing active failures or issues, reference the specific details available."""

            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=system_prompt,
                messages=messages
            )
            
            return response.content[0].text
            
        except Exception as e:
            logger.error(f"Chat failed: {e}")
            return f"I apologize, but I encountered an error: {str(e)}"