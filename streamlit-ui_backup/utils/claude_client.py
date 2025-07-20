# streamlit-ui/utils/claude_client.py
import os
import json
import asyncio
from typing import Dict, List, Any, Optional
from anthropic import AsyncAnthropic
import httpx

class ClaudeClient:
    def __init__(self):
        self.client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
        self.gitlab_mcp_url = os.environ.get("GITLAB_MCP_URL", "http://gitlab-mcp:8000")
        self.sonarqube_mcp_url = os.environ.get("SONARQUBE_MCP_URL", "http://sonarqube-mcp:8000")
        
    async def call_mcp_tool(self, mcp_url: str, tool_name: str, args: Dict) -> Dict:
        """Call MCP tool via HTTP"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            # FastMCP HTTP endpoint format
            response = await client.post(
                f"{mcp_url}/tools/{tool_name}",
                json={"arguments": args}
            )
            response.raise_for_status()
            return response.json()
    
    async def analyze_pipeline_failure(self, failure_data: Dict) -> Dict:
        """Progressive analysis with confidence scores from Claude"""
        context_levels = ["diff", "file", "related", "project", "variables"]
        current_level_idx = 0
        confidence = 0
        all_analyses = []
        
        while confidence < 80 and current_level_idx < len(context_levels):
            # Get context from GitLab MCP
            context = await self.call_mcp_tool(
                self.gitlab_mcp_url,
                "get_progressive_context",
                {
                    "project_id": failure_data["project_id"],
                    "pipeline_id": failure_data["pipeline_id"],
                    "commit_sha": failure_data["commit_sha"],
                    "context_level": context_levels[current_level_idx]
                }
            )
            
            # Get pipeline details
            pipeline_details = await self.call_mcp_tool(
                self.gitlab_mcp_url,
                "get_pipeline_failure_details",
                {
                    "project_id": failure_data["project_id"],
                    "pipeline_id": failure_data["pipeline_id"]
                }
            )
            
            # Build prompt
            prompt = self._build_analysis_prompt(
                failure_data,
                pipeline_details,
                context,
                context_levels[current_level_idx],
                all_analyses
            )
            
            # Call Claude for analysis
            response = await self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4000,
                temperature=0.2,
                system=self._get_system_prompt(),
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            analysis = self._parse_claude_response(response.content[0].text)
            analysis["context_level"] = context_levels[current_level_idx]
            all_analyses.append(analysis)
            
            confidence = analysis.get("confidence", 0)
            
            if confidence < 80:
                current_level_idx += 1
            else:
                break
        
        # Return best analysis
        best_analysis = max(all_analyses, key=lambda x: x.get("confidence", 0))
        best_analysis["all_attempts"] = all_analyses
        best_analysis["final_context_level"] = context_levels[min(current_level_idx, len(context_levels)-1)]
        
        return best_analysis
    
    async def analyze_quality_issues(self, issue_data: Dict) -> Dict:
        """Analyze SonarQube quality issues"""
        # Get project issues
        issues = await self.call_mcp_tool(
            self.sonarqube_mcp_url,
            "get_project_issues",
            {
                "project_key": issue_data["project_key"],
                "severity": ["BLOCKER", "CRITICAL", "MAJOR"]
            }
        )
        
        # Get quality gate status
        quality_gate = await self.call_mcp_tool(
            self.sonarqube_mcp_url,
            "get_quality_gate_status",
            {"project_key": issue_data["project_key"]}
        )
        
        # Get project measures
        measures = await self.call_mcp_tool(
            self.sonarqube_mcp_url,
            "get_project_measures",
            {"project_key": issue_data["project_key"]}
        )
        
        # Select top issues
        top_issues = self._select_top_issues(issues, limit=10)
        
        if top_issues:
            # Get detailed fix suggestions
            issue_keys = [issue["key"] for issue in top_issues]
            fix_details = await self.call_mcp_tool(
                self.sonarqube_mcp_url,
                "suggest_fixes_for_issues",
                {
                    "project_key": issue_data["project_key"],
                    "issue_keys": issue_keys
                }
            )
            
            # Build prompt for Claude
            prompt = self._build_quality_analysis_prompt(
                issue_data["project_key"],
                quality_gate,
                measures,
                fix_details
            )
            
            response = await self.client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4000,
                temperature=0.2,
                system=self._get_quality_system_prompt(),
                messages=[{"role": "user", "content": prompt}]
            )
            
            analysis = self._parse_claude_response(response.content[0].text)
            analysis["total_issues"] = issues.get("total", 0)
            analysis["analyzed_issues"] = len(top_issues)
            
            return analysis
        
        return {
            "summary": "No critical issues found",
            "quality_gate_status": quality_gate.get("status", "UNKNOWN"),
            "fixes": [],
            "overall_confidence": 100
        }
    
    async def generate_fixes(self, failure_data: Dict) -> Dict:
        """Generate specific code fixes for pipeline failures"""
        # First analyze to understand the issue
        analysis = await self.analyze_pipeline_failure(failure_data)
        
        if analysis.get("confidence", 0) < 50:
            return {
                "error": "Cannot generate fixes - insufficient confidence in analysis",
                "analysis": analysis
            }
        
        # Generate fix prompt
        prompt = f"""Based on this analysis, generate specific code fixes:

Analysis:
{json.dumps(analysis, indent=2)}

Generate executable fixes that can be applied directly. For each fix:
1. Provide the exact file path
2. Show the complete fixed code (not just snippets)
3. Explain why this fix resolves the issue
4. Include any necessary configuration changes

Return as JSON:
{{
    "fixes": [
        {{
            "file_path": "path/to/file",
            "action": "update",
            "content": "complete file content with fix",
            "explanation": "why this fixes the issue",
            "confidence": 90
        }}
    ],
    "merge_request_title": "Fix: <clear title>",
    "merge_request_description": "detailed description",
    "overall_confidence": 85
}}"""
        
        response = await self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=4000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        
        fixes = self._parse_claude_response(response.content[0].text)
        fixes["original_analysis"] = analysis
        
        return fixes
    
    async def generate_quality_fixes(self, issue_data: Dict) -> Dict:
        """Generate fixes for SonarQube quality issues"""
        # First analyze the issues
        analysis = await self.analyze_quality_issues(issue_data)
        
        if not analysis.get("fixes"):
            return {
                "error": "No issues to fix",
                "analysis": analysis
            }
        
        # Generate detailed fixes
        prompt = f"""Generate specific code fixes for these quality issues:

Analysis:
{json.dumps(analysis, indent=2)}

For each issue, provide:
1. The complete fixed code
2. Step-by-step implementation
3. Test cases to verify the fix

Return as JSON:
{{
    "fixes": [
        {{
            "issue_key": "issue-key",
            "file_path": "path/to/file",
            "original_code": "problematic code",
            "fixed_code": "corrected code",
            "explanation": "detailed explanation",
            "test_cases": ["test case 1", "test case 2"],
            "confidence": 90
        }}
    ],
    "implementation_order": ["issue-key-1", "issue-key-2"],
    "overall_confidence": 85
}}"""
        
        response = await self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=4000,
            temperature=0.1,
            messages=[{"role": "user", "content": prompt}]
        )
        
        fixes = self._parse_claude_response(response.content[0].text)
        fixes["original_analysis"] = analysis
        
        return fixes
    
    async def chat(self, user_input: str, chat_history: List[Dict]) -> str:
        """General chat interface for DevOps queries"""
        # Build conversation history
        messages = []
        for msg in chat_history[-10:]:  # Last 10 messages for context
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        messages.append({"role": "user", "content": user_input})
        
        response = await self.client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=2000,
            temperature=0.3,
            system="""You are a DevOps AI assistant helping with CI/CD pipelines and code quality.
            You have access to GitLab and SonarQube data. Provide helpful, specific advice.
            When discussing code or configurations, use proper formatting and be precise.""",
            messages=messages
        )
        
        return response.content[0].text
    
    def _get_system_prompt(self) -> str:
        """System prompt for pipeline analysis"""
        return """You are an expert DevOps engineer analyzing CI/CD pipeline failures.

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
            "line_numbers": [start, end]
        }
    ],
    "confidence": 85,
    "reasoning": "Why you're confident or not",
    "additional_context_needed": ["what else would help"] // only if confidence < 80
}"""
    
    def _get_quality_system_prompt(self) -> str:
        """System prompt for quality analysis"""
        return """You are a code quality expert analyzing SonarQube issues.

For each issue:
1. Understand the specific quality problem
2. Provide the exact fix with proper code
3. Explain why this improves code quality
4. Rate your confidence in the fix

Return analysis as JSON:
{
    "summary": "Overall code quality summary",
    "quality_gate_status": "PASSED/FAILED",
    "fixes": [
        {
            "issue_key": "issue-key",
            "file_path": "path/to/file",
            "line": 123,
            "problem": "Clear explanation",
            "fix": {
                "code": "Fixed code snippet",
                "explanation": "Why this fixes it"
            },
            "confidence": 90
        }
    ],
    "overall_confidence": 85,
    "priority_order": ["issue-key-1", "issue-key-2"]
}"""
    
    def _build_analysis_prompt(
        self,
        failure_data: Dict,
        pipeline_details: Dict,
        context: Dict,
        context_level: str,
        previous_analyses: List[Dict]
    ) -> str:
        """Build progressive analysis prompt"""
        prompt = f"""Pipeline Failure Analysis

Project: {failure_data.get('project_name', 'Unknown')}
Pipeline ID: {failure_data.get('pipeline_id')}
Commit: {failure_data.get('commit_sha')}
Branch: {pipeline_details.get('pipeline', {}).get('ref', 'Unknown')}
Author: {pipeline_details.get('commit', {}).get('author', 'Unknown')}

Failed Jobs:
"""
        
        for job in pipeline_details.get('failed_jobs', []):
            prompt += f"\n- Job: {job['name']} (Stage: {job['stage']})"
            prompt += f"\n  Status: {job['status']}"
            if job.get('failure_reason'):
                prompt += f"\n  Failure Reason: {job['failure_reason']}"
            prompt += f"\n  Error Log (last 100 lines):\n{self._get_last_lines(job.get('log', ''), 100)}\n"
        
        prompt += f"\n\nContext Level: {context_level}\n"
        
        if context_level == "diff":
            prompt += "\nCode Changes (Diff):\n"
            for diff in context.get('data', {}).get('diff', []):
                prompt += f"\nFile: {diff.get('new_path', diff.get('old_path'))}\n"
                prompt += f"Diff:\n{diff.get('diff', 'No diff available')}\n"
        
        elif context_level == "file":
            prompt += "\nChanged Files (Full Content):\n"
            for file in context.get('data', {}).get('files', [])[:5]:  # Limit to 5 files
                prompt += f"\nFile: {file['path']}\n"
                prompt += f"Content:\n{file['content'][:2000]}\n"  # Limit content
        
        elif context_level == "related":
            prompt += "\nRelated Files:\n"
            for file in context.get('data', {}).get('related_files', [])[:3]:  # Limit to 3 files
                prompt += f"\nFile: {file['path']}\n"
                prompt += f"Content (excerpt):\n{file['content'][:1000]}\n"
        
        elif context_level == "project":
            prompt += "\nProject Structure:\n"
            structure = context.get('data', {}).get('project_structure', [])
            prompt += json.dumps(structure[:50], indent=2)  # Limit items
        
        elif context_level == "variables":
            prompt += "\nCI/CD Variables:\n"
            for var in context.get('data', {}).get('variables', []):
                prompt += f"- {var['key']}: {var['value']} (scope: {var['scope']})\n"
        
        if previous_analyses:
            prompt += "\n\nPrevious Analysis Attempts:\n"
            for i, analysis in enumerate(previous_analyses[-2:]):  # Last 2 attempts
                prompt += f"\nAttempt {i+1} (Context: {analysis.get('context_level')}, Confidence: {analysis.get('confidence')}%):\n"
                prompt += f"- Root Cause: {analysis.get('root_cause', 'Unknown')}\n"
                if analysis.get('additional_context_needed'):
                    prompt += f"- Needed: {', '.join(analysis.get('additional_context_needed', []))}\n"
        
        prompt += "\n\nProvide your analysis based on the available context."
        
        return prompt
    
    def _build_quality_analysis_prompt(
        self,
        project_key: str,
        quality_gate: Dict,
        measures: Dict,
        fix_details: Dict
    ) -> str:
        """Build quality analysis prompt"""
        prompt = f"""Analyze these SonarQube issues and provide specific fixes:

Project: {project_key}
Quality Gate: {quality_gate.get('status', 'UNKNOWN')}

Key Metrics:
- Technical Debt: {measures.get('measures', {}).get('technical_debt', {}).get('value', 'Unknown')}
- Coverage: {measures.get('measures', {}).get('coverage', {}).get('value', 'Unknown')}%
- Bugs: {measures.get('measures', {}).get('bugs', {}).get('value', 'Unknown')}
- Vulnerabilities: {measures.get('measures', {}).get('vulnerabilities', {}).get('value', 'Unknown')}
- Code Smells: {measures.get('measures', {}).get('code_smells', {}).get('value', 'Unknown')}

Issues to fix:
{json.dumps(fix_details, indent=2)}

For each issue, provide:
1. A clear explanation of the problem
2. The specific code fix
3. Why this fix resolves the issue
4. Confidence score (0-100)"""
        
        return prompt
    
    def _parse_claude_response(self, response_text: str) -> Dict:
        """Parse Claude's response, extracting JSON if present"""
        try:
            # Look for JSON blocks in the response
            import re
            
            # Try to find JSON between ```json and ``` or just {}
            json_pattern = r'```json\s*(.*?)\s*```|(\{[^{}]*\})'
            matches = re.findall(json_pattern, response_text, re.DOTALL)
            
            if matches:
                for match in matches:
                    json_str = match[0] if match[0] else match[1]
                    try:
                        # Clean up the JSON string
                        json_str = json_str.strip()
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        continue
            
            # Try to parse the entire response as JSON
            try:
                return json.loads(response_text)
            except:
                pass
            
            # Fallback: return as text with low confidence
            return {
                "response": response_text,
                "confidence": 50,
                "parse_error": True
            }
        except Exception as e:
            return {
                "error": str(e),
                "response": response_text,
                "confidence": 0
            }
    
    def _get_last_lines(self, text: str, n: int = 100) -> str:
        """Get last n lines of text"""
        lines = text.strip().split('\n')
        return '\n'.join(lines[-n:])
    
    def _select_top_issues(self, issues_data: Dict, limit: int = 10) -> List[Dict]:
        """Select top issues based on severity and type"""
        all_issues = []
        for file_path, issues in issues_data.get('issues_by_file', {}).items():
            all_issues.extend(issues)
        
        # Sort by severity (BLOCKER > CRITICAL > MAJOR > MINOR > INFO)
        severity_order = {"BLOCKER": 0, "CRITICAL": 1, "MAJOR": 2, "MINOR": 3, "INFO": 4}
        all_issues.sort(key=lambda x: (severity_order.get(x['severity'], 5), x['creation_date']))
        
        return all_issues[:limit]