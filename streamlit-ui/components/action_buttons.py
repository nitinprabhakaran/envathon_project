import streamlit as st
from typing import Callable, Optional, Dict, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

class ActionButtons:
    """Reusable action buttons for the UI"""
    
    def __init__(self, mcp_url: Optional[str] = None):
        self.mcp_url = mcp_url
    
    def analyze_button(self, analyze_func: Callable, button_key: str = "analyze") -> bool:
        """Create an analyze button with loading state"""
        if st.button("🔍 Analyze", key=button_key, use_container_width=True):
            with st.spinner("🔍 Analyzing with AI..."):
                try:
                    # Run the async analyze function
                    asyncio.run(analyze_func())
                    st.success("✅ Analysis complete!")
                    return True
                except Exception as e:
                    logger.error(f"Analysis failed: {e}")
                    st.error(f"❌ Analysis failed: {str(e)}")
                    return False
        return False
    
    def create_mr_button(self, create_mr_func: Callable, fix_data: Dict[str, Any], 
                        button_key: str = "create_mr", confidence: int = 0) -> bool:
        """Create merge request button - only enabled for high confidence fixes"""
        disabled = confidence < 80
        help_text = "Confidence must be ≥ 80% to create MR" if disabled else "Create a merge request with this fix"
        
        if st.button(
            "🔀 Create MR", 
            key=button_key, 
            disabled=disabled,
            help=help_text,
            use_container_width=True
        ):
            with st.spinner("Creating merge request..."):
                try:
                    result = create_mr_func(fix_data)
                    st.success(f"✅ MR created: {result.get('web_url', 'Check GitLab')}")
                    return True
                except Exception as e:
                    logger.error(f"MR creation failed: {e}")
                    st.error(f"❌ Failed to create MR: {str(e)}")
                    return False
        return False
    
    def snooze_controls(self, project_id: str, branch: str, snooze_func: Callable, 
                       key_prefix: str = "snooze") -> bool:
        """Create snooze controls with hours selector"""
        col1, col2 = st.columns([2, 1])
        
        with col1:
            hours = st.slider(
                "Snooze hours",
                min_value=1,
                max_value=72,
                value=8,
                key=f"{key_prefix}_hours",
                help="Hide this issue for the specified hours"
            )
        
        with col2:
            if st.button("😴 Snooze", key=f"{key_prefix}_button"):
                try:
                    snooze_func(project_id, branch, hours)
                    st.success(f"Snoozed for {hours} hours")
                    return True
                except Exception as e:
                    logger.error(f"Snooze failed: {e}")
                    st.error("Failed to snooze")
                    return False
        return False
    
    def confidence_indicator(self, confidence: int):
        """Display confidence score with color coding"""
        if confidence >= 80:
            color = "#28a745"  # Green
            emoji = "✅"
        elif confidence >= 60:
            color = "#ffc107"  # Yellow
            emoji = "⚠️"
        else:
            color = "#dc3545"  # Red
            emoji = "❌"
        
        st.markdown(
            f"""
            <div style="text-align: center; padding: 10px; background-color: #f0f0f0; border-radius: 8px;">
                <h3 style="margin: 0; color: {color};">
                    {emoji} Confidence: {confidence}%
                </h3>
            </div>
            """,
            unsafe_allow_html=True
        )
    
    def fix_action_buttons(self, fix: Dict[str, Any], analysis_key: str, fix_idx: int,
                          create_mr_func: Callable, confidence: int = 0):
        """Create action buttons for a specific fix"""
        col1, col2, col3 = st.columns(3)
        
        with col1:
            self.create_mr_button(
                lambda fix_data: create_mr_func(analysis_key, fix_data, fix_idx),
                fix,
                button_key=f"mr_{analysis_key}_{fix_idx}",
                confidence=confidence
            )
        
        with col2:
            if st.button("📋 Copy", key=f"copy_{analysis_key}_{fix_idx}"):
                # Create a text area with the code for easy copying
                st.code(fix.get('code_snippet', ''), language=fix.get('language', 'python'))
                st.info("📋 Code displayed above - select and copy")
        
        with col3:
            if st.button("💬 Discuss", key=f"discuss_{analysis_key}_{fix_idx}"):
                # Add to chat context
                st.session_state.chat_context = {
                    "type": "fix_discussion",
                    "fix": fix,
                    "analysis_key": analysis_key
                }
                st.info("💬 Added to chat context - ask questions below")
    
    def progressive_context_button(self, request_func: Callable, context_needed: list,
                                  button_key: str = "more_context"):
        """Button to request more context for low confidence analyses"""
        if st.button("🔄 Analyze with more context", key=button_key, use_container_width=True):
            with st.expander("📋 Gathering additional context...", expanded=True):
                progress = st.progress(0)
                status = st.empty()
                
                for idx, context_item in enumerate(context_needed):
                    status.text(f"Fetching: {context_item}")
                    progress.progress((idx + 1) / len(context_needed))
                
                try:
                    asyncio.run(request_func())
                    st.success("✅ Re-analysis with additional context complete!")
                    return True
                except Exception as e:
                    logger.error(f"Context gathering failed: {e}")
                    st.error(f"Failed to gather context: {str(e)}")
                    return False
        return False
    
    def auto_analyze_toggle(self, key: str = "auto_analyze") -> bool:
        """Toggle for automatic analysis of high priority issues"""
        return st.checkbox(
            "🤖 Auto-analyze high priority failures",
            value=True,
            key=key,
            help="Automatically analyze failures marked as high priority"
        )
    
    def refresh_button(self, refresh_func: Callable, button_key: str = "refresh") -> bool:
        """Create a refresh button"""
        if st.button("🔄 Refresh", key=button_key):
            with st.spinner("Checking for new issues..."):
                try:
                    count = refresh_func()
                    if count > 0:
                        st.success(f"Found {count} new issues")
                    else:
                        st.info("No new issues found")
                    return True
                except Exception as e:
                    logger.error(f"Refresh failed: {e}")
                    st.error("Failed to refresh")
                    return False
        return False