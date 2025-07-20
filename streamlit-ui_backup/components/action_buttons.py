import streamlit as st
import requests
import json
from typing import Dict, Callable

class ActionButtons:
    def __init__(self, gitlab_mcp_url: str):
        self.gitlab_mcp_url = gitlab_mcp_url
    
    def create_merge_request_button(self, 
                                  project_id: int, 
                                  fixes: Dict, 
                                  button_key: str):
        """Create MR button with fix implementation"""
        if st.button("🔀 Create Merge Request", key=button_key):
            with st.spinner("Creating merge request..."):
                try:
                    # Prepare MR data
                    mr_data = {
                        "project_id": project_id,
                        "source_branch": f"fix-{button_key}",
                        "title": fixes.get('title', 'Automated fix'),
                        "description": fixes.get('description', ''),
                        "changes": fixes.get('changes', []),
                        "target_branch": "main"
                    }
                    
                    # Call GitLab MCP to create MR
                    response = requests.post(
                        f"{self.gitlab_mcp_url}/tools/create_merge_request",
                        json=mr_data,
                        headers={"Content-Type": "application/json"}
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"✅ Merge request created successfully!")
                        st.markdown(f"[View MR]({result.get('merge_request_url', '#')})")
                    else:
                        st.error(f"Failed to create MR: {response.text}")
                        
                except Exception as e:
                    st.error(f"Error creating merge request: {str(e)}")
    
    def analyze_button(self, 
                      action: Callable,
                      button_text: str = "🔍 Analyze",
                      button_key: str = None):
        """Generic analyze button"""
        if st.button(button_text, key=button_key):
            with st.spinner("Analyzing..."):
                try:
                    result = action()
                    return result
                except Exception as e:
                    st.error(f"Analysis failed: {str(e)}")
                    return None
    
    def snooze_controls(self, 
                       project_id: int, 
                       branch: str,
                       snooze_callback: Callable,
                       button_key: str):
        """Snooze controls with duration selector"""
        col1, col2 = st.columns([2, 1])
        
        with col1:
            duration = st.slider(
                "Duration (hours)",
                min_value=1,
                max_value=24,
                value=8,
                key=f"duration_{button_key}"
            )
        
        with col2:
            if st.button("😴 Snooze", key=f"snooze_{button_key}"):
                snooze_callback(project_id, branch, duration)
                st.success(f"Snoozed for {duration} hours")
                st.rerun()
    
    def confidence_indicator(self, confidence: int):
        """Display confidence indicator"""
        if confidence >= 80:
            st.success(f"High Confidence: {confidence}%")
        elif confidence >= 60:
            st.warning(f"Medium Confidence: {confidence}%")
        else:
            st.error(f"Low Confidence: {confidence}%")