# streamlit-ui/utils/llm_providers.py - COMPLETE REWRITTEN FILE
import os
import json
import logging
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import httpx

logger = logging.getLogger(__name__)

class BaseLLMProvider(ABC):
    """Base class for all LLM providers - ZERO hardcoded logic"""
    
    def __init__(self):
        self.gitlab_api_url = os.environ.get("GITLAB_API_URL", "http://gitlab-api:8081")
        self.sonarqube_api_url = os.environ.get("SONARQUBE_API_URL", "http://sonarqube-api:8082")
        logger.info(f"GitLab API URL: {self.gitlab_api_url}")
        logger.info(f"SonarQube API URL: {self.sonarqube_api_url}")
    
    @abstractmethod
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Analyze pipeline failure - ALL analysis from LLM"""
        pass
    
    @abstractmethod
    async def analyze_sonarqube_issues(self, project_key: str, severity_threshold: str = "MAJOR") -> Dict:
        """Analyze SonarQube issues - ALL analysis from LLM"""
        pass
    
    @abstractmethod
    async def chat(self, user_input: str, chat_history: List[Dict], context: Optional[Dict] = None) -> str:
        """Chat interface"""
        pass
    
    async def get_gitlab_data(self, endpoint: str, **params) -> Dict:
        """Get data from GitLab API service with better error handling"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            try:
                url = f"{self.gitlab_api_url}/{endpoint.lstrip('/')}"
                logger.info(f"Making request to: {url}")
                
                if params and any(isinstance(v, (dict, list)) for v in params.values()):
                    response = await client.post(url, json=params)
                else:
                    response = await client.get(url, params=params)
                
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.error(f"GitLab API error: {e}")
                raise Exception(f"Failed to get GitLab data: {str(e)}")
    
    async def get_sonarqube_data(self, endpoint: str, **params) -> Dict:
        """Get data from SonarQube API service with better error handling"""
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            try:
                url = f"{self.sonarqube_api_url}/{endpoint.lstrip('/')}"
                logger.info(f"Making request to: {url}")
                
                if params and any(isinstance(v, (dict, list)) for v in params.values()):
                    response = await client.post(url, json=params)
                else:
                    response = await client.get(url, params=params)
                
                response.raise_for_status()
                return response.json()
                
            except Exception as e:
                logger.error(f"SonarQube API error: {e}")
                raise Exception(f"Failed to get SonarQube data: {str(e)}")
    
    async def test_connectivity(self) -> Dict[str, bool]:
        """Test connectivity to both API services"""
        results = {}
        
        try:
            await self.get_gitlab_data("health")
            results["gitlab_api"] = True
            logger.info("✅ GitLab API connectivity: OK")
        except Exception as e:
            results["gitlab_api"] = False
            logger.error(f"❌ GitLab API connectivity: {e}")
        
        try:
            await self.get_sonarqube_data("health")
            results["sonarqube_api"] = True
            logger.info("✅ SonarQube API connectivity: OK")
        except Exception as e:
            results["sonarqube_api"] = False
            logger.error(f"❌ SonarQube API connectivity: {e}")
        
        return results
    
    def get_system_prompt(self) -> str:
        """System prompt for analysis - NO HARDCODED CONFIDENCE LOGIC"""
        return """You are an expert DevOps engineer analyzing CI/CD pipeline failures and code quality issues.

CRITICAL: ALL analysis, confidence scoring, and fix generation must come from your reasoning. 
Do NOT use any hardcoded patterns or rules.

When analyzing failures:
1. Examine the error logs, code changes, and context provided
2. Determine the root cause using your expertise
3. Generate specific fixes with code snippets
4. Rate your confidence (0-100) based on:
   - How clear the error message is
   - How much context you have
   - How certain you are about the fix
   - Your understanding of the failure pattern

ALWAYS return your analysis in this JSON format:
{
    "root_cause": "Clear explanation of what caused the failure",
    "affected_files": ["list", "of", "files"],
    "fixes": [
        {
            "file_path": "path/to/file",
            "description": "What to fix",
            "code_snippet": "The actual fix",
            "line_numbers": [start, end],
            "explanation": "Why this fixes the issue",
            "language": "programming language"
        }
    ],
    "confidence": 85,
    "reasoning": "Detailed explanation of your confidence level",
    "additional_context_needed": ["what else would help if confidence < 80"]
}"""

    def parse_llm_response(self, response_text: str) -> Dict:
        """Parse LLM response, extracting JSON if present"""
        try:
            import re
            
            json_patterns = [
                r'```json\s*(.*?)\s*```',
                r'```\s*(.*?)\s*```',
                r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})'
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, response_text, re.DOTALL)
                if matches:
                    for match in matches:
                        try:
                            json_str = match.strip()
                            parsed = json.loads(json_str)
                            if isinstance(parsed, dict):
                                return parsed
                        except json.JSONDecodeError:
                            continue
            
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


class MockProvider(BaseLLMProvider):
    """Mock LLM provider for testing without external API calls"""
    
    def __init__(self):
        super().__init__()
        logger.info("✅ Initialized Mock LLM provider")
    
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Mock analysis for testing"""
        import random
        await asyncio.sleep(1)
        
        confidence = random.randint(70, 95)
        
        return {
            "root_cause": f"Mock analysis: Build failure in project {failure_data.get('project_name', 'unknown')}. Common causes include syntax errors, missing dependencies, or configuration issues.",
            "affected_files": ["scripts/build.sh", "package.json", "Dockerfile"],
            "fixes": [
                {
                    "file_path": "scripts/build.sh",
                    "description": "Fix shell script syntax and add error handling",
                    "code_snippet": "#!/bin/bash\nset -e\necho 'Starting build...'\nnpm install\nnpm run build\necho 'Build completed successfully'",
                    "line_numbers": [1, 6],
                    "explanation": "Added proper shebang, error handling with 'set -e', and informative logging",
                    "language": "bash"
                }
            ],
            "confidence": confidence,
            "reasoning": f"Mock analysis with {confidence}% confidence based on common pipeline failure patterns",
            "llm_provider": "mock",
            "project_id": failure_data.get('project_id')
        }
    
    async def analyze_sonarqube_issues(self, project_key: str, severity_threshold: str = "MAJOR") -> Dict:
        """Mock SonarQube analysis"""
        await asyncio.sleep(1)
        
        return {
            "root_cause": f"Mock analysis: Code quality issues detected in {project_key}",
            "summary": "Mock quality analysis found several issues",
            "quality_gate_status": "FAILED",
            "fixes": [
                {
                    "file_path": "src/main.py",
                    "description": "Remove unused variable",
                    "code_snippet": "# Remove unused variable\n# old_var = 'unused'",
                    "explanation": "Removing unused variables improves code maintainability",
                    "language": "python"
                }
            ],
            "confidence": 85,
            "reasoning": "Mock analysis with high confidence",
            "llm_provider": "mock",
            "project_key": project_key
        }
    
    async def chat(self, user_input: str, chat_history: List[Dict], context: Optional[Dict] = None) -> str:
        """Mock chat response"""
        await asyncio.sleep(0.5)
        return f"Mock response to: '{user_input}'\n\nThis is a simulated AI response for testing purposes."


class ClaudeProvider(BaseLLMProvider):
    """Claude (Anthropic) provider - FIXED VERSION"""
    
    def __init__(self):
        super().__init__()
        try:
            import anthropic
            
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            
            # Initialize Claude client with proper headers
            self.client = anthropic.Anthropic(
                api_key=api_key,
                default_headers={
                    "anthropic-version": "2023-06-01"
                }
            )
            self.model = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
            
            logger.info(f"✅ Initialized Claude provider")
            logger.info(f"🔑 Model: {self.model}")
            logger.info(f"🔑 API Key: {api_key[:15]}...")
            
            # Test the connection
            self._test_connection()
            
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Claude provider: {e}")
            raise
    
    def _test_connection(self):
        """Test the connection with a simple request"""
        try:
            logger.info("🧪 Testing Claude API connection...")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=5,
                messages=[{"role": "user", "content": "Hi"}]
            )
            logger.info("✅ Claude API connection successful!")
        except Exception as e:
            logger.warning(f"⚠️ Claude API test failed: {e}")
    
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Progressive analysis with ALL confidence scoring from Claude"""
        try:
            logger.info("🚀 Starting Claude pipeline failure analysis...")
            
            # Test API connectivity first
            connectivity = await self.test_connectivity()
            if not connectivity.get("gitlab_api", False):
                return {
                    "error": "Cannot connect to GitLab API service",
                    "root_cause": "API connectivity issue", 
                    "confidence": 0,
                    "llm_provider": "claude"
                }
            
            # Get pipeline details
            logger.info(f"📊 Getting pipeline details...")
            try:
                pipeline_details = await self.get_gitlab_data(
                    f"projects/{failure_data['project_id']}/pipeline/{failure_data['pipeline_id']}/failure-details"
                )
            except Exception as e:
                logger.error(f"Failed to get pipeline details: {e}")
                return {
                    "error": f"Failed to get pipeline details: {str(e)}",
                    "root_cause": "Cannot fetch pipeline data",
                    "confidence": 0,
                    "llm_provider": "claude"
                }
            
            # Get context
            logger.info(f"📁 Getting code context...")
            try:
                context = await self.get_gitlab_data(
                    f"projects/{failure_data['project_id']}/context",
                    pipeline_id=failure_data['pipeline_id'],
                    commit_sha=failure_data.get('commit_sha', ''),
                    context_level="diff"
                )
            except Exception as e:
                logger.error(f"Failed to get context: {e}")
                context = {"data": {}, "context_level": "minimal"}
            
            # Build prompt
            prompt = f"""Analyze this CI/CD pipeline failure and provide specific fixes.

Pipeline Details:
{json.dumps(pipeline_details, indent=2)}

Code Context:
{json.dumps(context, indent=2)}

Failure Data:
{json.dumps(failure_data, indent=2)}

{self.get_system_prompt()}

Analyze this failure and provide your response in the exact JSON format specified."""

            # Call Claude with retry logic
            logger.info("🤖 Calling Claude API...")
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=4000,
                        temperature=0.1,
                        messages=[
                            {"role": "user", "content": prompt}
                        ]
                    )
                    logger.info(f"✅ Claude API call successful on attempt {attempt + 1}")
                    break
                    
                except Exception as e:
                    logger.warning(f"⚠️ Claude API attempt {attempt + 1} failed: {e}")
                    if attempt == max_retries - 1:
                        return {
                            "error": f"Claude API unavailable: {str(e)}",
                            "root_cause": "Pipeline failure detected - Claude API service unavailable",
                            "confidence": 30,
                            "fixes": [{
                                "file_path": "unknown",
                                "description": "Manual investigation required",
                                "code_snippet": "# Check pipeline logs for specific error details\n# Common issues: syntax errors, missing dependencies, configuration problems",
                                "explanation": "AI analysis unavailable - please review pipeline logs manually",
                                "language": "text"
                            }],
                            "reasoning": "Claude API service unavailable - providing basic guidance",
                            "llm_provider": "claude",
                            "fallback_mode": True,
                            "project_id": failure_data.get('project_id')
                        }
                    await asyncio.sleep(2 ** attempt)
            
            # Parse response
            analysis = self.parse_llm_response(response.content[0].text)
            analysis["llm_provider"] = "claude"
            analysis["model"] = self.model
            analysis["project_id"] = failure_data.get('project_id')
            
            logger.info(f"✅ Claude analysis complete with confidence: {analysis.get('confidence', 0)}%")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Claude analysis failed: {e}")
            return {
                "error": str(e),
                "root_cause": "Claude analysis service unavailable",
                "confidence": 0,
                "llm_provider": "claude",
                "project_id": failure_data.get('project_id')
            }
    
    async def analyze_sonarqube_issues(self, project_key: str, severity_threshold: str = "MAJOR") -> Dict:
        """Analyze SonarQube issues with ALL scoring from Claude"""
        try:
            logger.info(f"🔍 Starting Claude SonarQube analysis for {project_key}...")
            
            connectivity = await self.test_connectivity()
            if not connectivity.get("sonarqube_api", False):
                return {
                    "error": "Cannot connect to SonarQube API service",
                    "summary": "API connectivity issue",
                    "confidence": 0,
                    "llm_provider": "claude",
                    "project_key": project_key
                }
            
            # Get SonarQube data
            try:
                issues = await self.get_sonarqube_data(
                    f"projects/{project_key}/issues", 
                    severity=["BLOCKER", "CRITICAL", "MAJOR"]
                )
                quality_gate = await self.get_sonarqube_data(f"projects/{project_key}/quality-gate")
            except Exception as e:
                logger.error(f"Failed to get SonarQube data: {e}")
                return {
                    "error": f"Failed to get SonarQube data: {str(e)}",
                    "summary": "Cannot fetch quality data",
                    "confidence": 0,
                    "llm_provider": "claude",
                    "project_key": project_key
                }
            
            # Build prompt for Claude
            prompt = f"""Analyze these SonarQube quality issues and provide specific fixes.

Project: {project_key}
Quality Gate Status: {quality_gate}
Issues Data: {issues}

{self.get_system_prompt().replace('pipeline failures', 'code quality issues')}

For each critical issue, provide:
1. Clear explanation of the problem
2. Specific code fix with proper syntax
3. Why this fix resolves the issue
4. Your confidence in this fix (0-100)

Return analysis in the same JSON format as pipeline analysis, but adapted for quality issues."""

            # Call Claude
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4000,
                    temperature=0.1,
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
                
                # Parse response
                analysis = self.parse_llm_response(response.content[0].text)
                analysis["llm_provider"] = "claude"
                analysis["project_key"] = project_key
                
                logger.info(f"✅ Claude SonarQube analysis complete")
                return analysis
                
            except Exception as e:
                logger.error(f"Claude API call failed for SonarQube: {e}")
                return {
                    "error": f"Claude API unavailable: {str(e)}",
                    "summary": "Quality issues detected - Claude API unavailable for detailed analysis",
                    "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
                    "fixes": [{
                        "file_path": "unknown",
                        "description": "Manual review required",
                        "code_snippet": "# Please review SonarQube dashboard for specific issues",
                        "explanation": "Claude analysis unavailable",
                        "language": "text"
                    }],
                    "confidence": 30,
                    "reasoning": "Claude API service unavailable",
                    "llm_provider": "claude",
                    "project_key": project_key,
                    "fallback_mode": True
                }
            
        except Exception as e:
            logger.error(f"Claude SonarQube analysis failed: {e}")
            return {
                "error": str(e),
                "summary": "Analysis failed",
                "quality_gate_status": "UNKNOWN",
                "fixes": [],
                "confidence": 0,
                "llm_provider": "claude",
                "project_key": project_key
            }
    
    async def chat(self, user_input: str, chat_history: List[Dict], context: Optional[Dict] = None) -> str:
        """Chat interface using Claude"""
        try:
            logger.info(f"💬 Processing Claude chat message...")
            
            # Build conversation context
            messages = []
            for msg in chat_history[-10:]:  # Last 10 messages
                role = "user" if msg["role"] == "user" else "assistant"
                messages.append({
                    "role": role,
                    "content": msg["content"]
                })
            
            # Add current context if available
            if context:
                context_prompt = f"Current system context:\n{json.dumps(context, indent=2)}\n\nUser question: {user_input}"
            else:
                context_prompt = user_input
            
            # Add current message
            messages.append({
                "role": "user",
                "content": context_prompt
            })
            
            # System prompt for chat
            system_prompt = """You are a helpful DevOps AI assistant. You help with:
- Analyzing CI/CD pipeline failures
- Understanding code quality issues
- Suggesting fixes and improvements
- Explaining DevOps best practices

When discussing failures or issues, reference the specific details from the system context.
Provide clear, actionable advice with code examples when appropriate."""

            # Call Claude
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=2000,
                    temperature=0.3,
                    system=system_prompt,
                    messages=messages
                )
                
                logger.info("✅ Claude chat response generated")
                return response.content[0].text
                
            except Exception as e:
                logger.error(f"Claude chat API failed: {e}")
                return f"I apologize, but I'm currently unable to process your request due to a service issue: {str(e)}. Please try again in a moment."
            
        except Exception as e:
            logger.error(f"Claude chat failed: {e}")
            return f"I encountered an error: {str(e)}"


class LLMProviderFactory:
    """Factory to create LLM providers based on configuration"""
    
    @staticmethod
    def create_provider() -> BaseLLMProvider:
        """Create LLM provider based on environment variables"""
        provider_name = os.environ.get("LLM_PROVIDER", "claude").lower()
        
        logger.info(f"🔧 Creating LLM provider: {provider_name}")
        
        if provider_name == "claude":
            return ClaudeProvider()
        elif provider_name == "mock":
            return MockProvider()
        else:
            logger.warning(f"Unknown provider '{provider_name}', falling back to mock")
            return MockProvider()
    
    @staticmethod
    def get_available_providers() -> List[str]:
        """Get list of available providers"""
        return ["claude", "mock"]