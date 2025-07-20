import streamlit as st
from datetime import datetime
import re

class ChatInterface:
    def render(self, messages: list):
        """Render chat messages with proper formatting"""
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            timestamp = message.get("timestamp", "")
            
            with st.chat_message(role):
                # Parse content for special formatting
                self._render_formatted_content(content)
                
                # Show timestamp
                if timestamp:
                    dt = datetime.fromisoformat(timestamp)
                    st.caption(dt.strftime("%I:%M %p"))
    
    def _render_formatted_content(self, content: str):
        """Render content with code blocks and formatting"""
        # Check if content is JSON (for structured responses)
        try:
            import json
            data = json.loads(content)
            self._render_structured_response(data)
            return
        except:
            pass
        
        # Split content by code blocks
        code_pattern = r'```(\w+)?\n(.*?)```'
        parts = re.split(code_pattern, content, flags=re.DOTALL)
        
        i = 0
        while i < len(parts):
            if i % 3 == 0:
                # Regular text
                if parts[i].strip():
                    st.markdown(parts[i])
            elif i % 3 == 1:
                # Language identifier
                lang = parts[i] if parts[i] else 'text'
            else:
                # Code block
                st.code(parts[i], language=lang)
            i += 1
    
    def _render_structured_response(self, data: dict):
        """Render structured JSON responses nicely"""
        if 'analysis' in data:
            st.markdown(f"**Analysis:** {data['analysis']}")
            
            if 'root_cause' in data:
                st.warning(f"**Root Cause:** {data['root_cause']}")
            
            if 'confidence' in data:
                confidence = data['confidence']
                color = "green" if confidence >= 80 else "orange" if confidence >= 60 else "red"
                st.markdown(f"**Confidence:** :{color}[{confidence}%]")
            
            if 'need_more_context' in data and data['need_more_context']:
                st.info(f"**Additional context needed:** {', '.join(data.get('context_needed', []))}")
        
        elif 'fixes' in data:
            st.markdown("### Suggested Fixes:")
            for i, fix in enumerate(data['fixes']):
                with st.expander(f"{i+1}. {fix.get('title', 'Fix')} (Confidence: {fix.get('confidence', 0)}%)"):
                    st.markdown(fix.get('description', ''))
                    
                    if 'changes' in fix:
                        st.markdown("**Code changes:**")
                        for change in fix['changes']:
                            st.markdown(f"File: `{change['file_path']}`")
                            st.code(change['content'], language='python')
        
        else:
            # Fallback to JSON display
            st.json(data)