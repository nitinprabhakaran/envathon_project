import streamlit as st
import asyncio
from datetime import datetime
from typing import List, Dict, Optional
import logging
import json

logger = logging.getLogger(__name__)

class ChatInterface:
    """Chat interface for interacting with the AI assistant"""
    
    def __init__(self, llm_client, session_manager):
        self.llm_client = llm_client
        self.session_manager = session_manager
    
    def render(self, session_id: str):
        """Render the complete chat interface"""
        st.markdown("### 💬 AI Assistant Chat")
        
        # Initialize chat messages in session state
        if "chat_messages" not in st.session_state:
            st.session_state.chat_messages = []
            # Add welcome message
            st.session_state.chat_messages.append({
                "role": "assistant",
                "content": "Hello! I'm your DevOps AI Assistant. I can help you analyze pipeline failures, understand code quality issues, and suggest fixes. What would you like to know?",
                "timestamp": datetime.now().isoformat()
            })
        
        # Chat context indicator
        if hasattr(st.session_state, 'chat_context') and st.session_state.chat_context:
            context_type = st.session_state.chat_context.get('type', 'unknown')
            if context_type == 'fix_discussion':
                st.info(f"💬 Discussing fix: {st.session_state.chat_context['fix'].get('description', 'Selected fix')}")
            elif context_type == 'failure_analysis':
                st.info(f"💬 Discussing pipeline failure #{st.session_state.chat_context.get('pipeline_id', 'Unknown')}")
        
        # Display chat history
        chat_container = st.container()
        with chat_container:
            for message in st.session_state.chat_messages:
                self._render_message(message)
        
        # Chat input
        if prompt := st.chat_input("Ask about failures, request analysis, or get help with fixes..."):
            # Add user message
            user_message = {
                "role": "user",
                "content": prompt,
                "timestamp": datetime.now().isoformat()
            }
            st.session_state.chat_messages.append(user_message)
            
            # Display user message immediately
            with chat_container:
                self._render_message(user_message)
            
            # Get and display assistant response
            with chat_container:
                with st.chat_message("assistant"):
                    response_placeholder = st.empty()
                    
                    # Show thinking indicator
                    with response_placeholder.container():
                        st.markdown("🤔 Thinking...")
                    
                    # Get response
                    response = asyncio.run(self._get_assistant_response(prompt))
                    
                    # Update with actual response
                    with response_placeholder.container():
                        self._render_assistant_content(response)
            
            # Add assistant message to history
            assistant_message = {
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            }
            st.session_state.chat_messages.append(assistant_message)
            
            # Save to session
            self.session_manager.add_message(session_id, {
                "type": "chat",
                "timestamp": datetime.now().isoformat(),
                "user_message": prompt,
                "assistant_response": response
            })
        
        # Quick actions
        st.markdown("---")
        st.markdown("**Quick Actions:**")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📊 Summarize Failures", use_container_width=True):
                self._add_system_prompt("Please summarize all current pipeline failures and issues.")
        
        with col2:
            if st.button("💡 Best Practices", use_container_width=True):
                self._add_system_prompt("What are the best practices to avoid the current types of failures?")
        
        with col3:
            if st.button("🔍 Deep Analysis", use_container_width=True):
                self._add_system_prompt("Perform a deep analysis of the most recent failure with root cause analysis.")
    
    def _render_message(self, message: Dict):
        """Render a single message"""
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            else:
                self._render_assistant_content(message["content"])
            
            # Show timestamp in small text
            timestamp = datetime.fromisoformat(message["timestamp"])
            st.caption(f"{timestamp.strftime('%I:%M %p')}")
    
    def _render_assistant_content(self, content: str):
        """Render assistant message with proper formatting for code blocks"""
        import re
        
        # Split content by code blocks
        code_pattern = r'```(\w*)\n(.*?)```'
        parts = re.split(code_pattern, content, flags=re.DOTALL)
        
        i = 0
        while i < len(parts):
            if i % 3 == 0:  # Text part
                if parts[i].strip():
                    st.markdown(parts[i])
            elif i % 3 == 1:  # Language identifier
                language = parts[i] if parts[i] else 'python'
                code = parts[i + 1] if i + 1 < len(parts) else ''
                if code.strip():
                    st.code(code.strip(), language=language)
                i += 1  # Skip the code content part
            i += 1
    
    async def _get_assistant_response(self, prompt: str) -> str:
        """Get response from LLM with context awareness"""
        try:
            # Build context
            context = self._build_context()
            
            # Include chat context if available
            if hasattr(st.session_state, 'chat_context') and st.session_state.chat_context:
                context += f"\n\nCurrent context: {json.dumps(st.session_state.chat_context, indent=2)}"
            
            # Create enhanced prompt
            enhanced_prompt = f"{context}\n\nUser question: {prompt}"
            
            # Get recent chat history for context
            recent_messages = st.session_state.chat_messages[-10:]  # Last 10 messages
            
            # Call LLM
            response = await self.llm_client.chat(enhanced_prompt, recent_messages)
            
            # Clear chat context after use
            if hasattr(st.session_state, 'chat_context'):
                delattr(st.session_state, 'chat_context')
            
            return response
            
        except Exception as e:
            logger.error(f"Error getting assistant response: {e}")
            return f"I apologize, but I encountered an error: {str(e)}. Please try again or rephrase your question."
    
    def _build_context(self) -> str:
        """Build context about current failures and issues"""
        context_parts = ["Current system status:"]
        
        # GitLab failures
        if hasattr(st.session_state, 'gitlab_failures') and st.session_state.gitlab_failures:
            context_parts.append(f"\nActive GitLab Pipeline Failures ({len(st.session_state.gitlab_failures)}):")
            for failure in st.session_state.gitlab_failures[:3]:  # Top 3
                context_parts.append(
                    f"- {failure['project_name']}: Pipeline #{failure['pipeline_id']} "
                    f"failed at '{failure.get('failed_stage', 'unknown')}' stage"
                )
            if len(st.session_state.gitlab_failures) > 3:
                context_parts.append(f"- ... and {len(st.session_state.gitlab_failures) - 3} more failures")
        
        # SonarQube issues
        if hasattr(st.session_state, 'sonarqube_issues') and st.session_state.sonarqube_issues:
            context_parts.append(f"\nActive SonarQube Issues ({len(st.session_state.sonarqube_issues)}):")
            for issue in st.session_state.sonarqube_issues[:3]:  # Top 3
                context_parts.append(
                    f"- {issue['project_name']}: Quality gate {issue['quality_gate_status']} "
                    f"with {issue.get('total_issues', 0)} issues"
                )
            if len(st.session_state.sonarqube_issues) > 3:
                context_parts.append(f"- ... and {len(st.session_state.sonarqube_issues) - 3} more projects")
        
        # Recent analyses
        if hasattr(st.session_state, 'active_analyses') and st.session_state.active_analyses:
            context_parts.append(f"\nRecent Analyses ({len(st.session_state.active_analyses)}):")
            for key, analysis in list(st.session_state.active_analyses.items())[-3:]:  # Last 3
                context_parts.append(
                    f"- Analysis {key}: Confidence {analysis.get('confidence', 0)}%, "
                    f"{len(analysis.get('fixes', []))} fixes suggested"
                )
        
        return "\n".join(context_parts)
    
    def _add_system_prompt(self, prompt: str):
        """Add a system-generated prompt to the chat"""
        # Simulate user asking the question
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt,
            "timestamp": datetime.now().isoformat()
        })
        st.rerun()