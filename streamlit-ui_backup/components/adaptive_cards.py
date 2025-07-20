import streamlit as st
from datetime import datetime
import json

class AdaptiveCard:
    def render_pipeline_failure(self, failure_data: dict):
        """Render pipeline failure as an adaptive card"""
        with st.container():
            # Card header
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### 🚨 Pipeline Failed: {failure_data['project_name']}")
            with col2:
                st.markdown(f"**{failure_data.get('ref', 'main')}**")
            
            # Card body
            st.markdown(f"""
            **Pipeline ID:** `{failure_data['pipeline_id']}`  
            **Commit:** `{failure_data['sha'][:8]}` - {failure_data['commit']['message']}  
            **Author:** {failure_data['user']['name']} ({failure_data['user']['email']})  
            **Failed at:** {failure_data.get('created_at', datetime.now().isoformat())}
            """)
            
            # Status indicator
            st.error("Pipeline Status: FAILED")
            
            # Expandable details
            with st.expander("View Details"):
                st.json(failure_data)
            
            st.divider()
    
    def render_quality_issue(self, issue_data: dict):
        """Render quality issue as an adaptive card"""
        with st.container():
            # Card header
            quality_status = issue_data['quality_gate']['status']
            status_emoji = "❌" if quality_status == "FAILURE" else "⚠️"
            
            st.markdown(f"### {status_emoji} Quality Gate: {issue_data['project_name']}")
            
            # Metrics summary
            col1, col2, col3, col4 = st.columns(4)
            
            # Extract conditions
            conditions = issue_data['quality_gate'].get('conditions', [])
            for i, condition in enumerate(conditions[:4]):
                with [col1, col2, col3, col4][i % 4]:
                    metric_name = condition.get('metric', 'Unknown')
                    actual = condition.get('actual', 'N/A')
                    threshold = condition.get('threshold', 'N/A')
                    status = condition.get('status', 'ERROR')
                    
                    if status == "ERROR":
                        st.metric(
                            metric_name,
                            actual,
                            f"Threshold: {threshold}",
                            delta_color="inverse"
                        )
            
            # Issue summary
            st.markdown(f"""
            **Branch:** {issue_data.get('branch', 'main')}  
            **Analyzed at:** {issue_data.get('analyzed_at', datetime.now().isoformat())}
            """)
            
            # Expandable details
            with st.expander("View All Conditions"):
                st.json(conditions)
            
            st.divider()
    
    def render_fix_suggestion(self, fix_data: dict):
        """Render fix suggestion as an adaptive card"""
        with st.container():
            # Confidence indicator
            confidence = fix_data.get('confidence', 0)
            confidence_color = "green" if confidence >= 80 else "orange" if confidence >= 60 else "red"
            confidence_text = "High" if confidence >= 80 else "Medium" if confidence >= 60 else "Low"
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### 🛠️ {fix_data['title']}")
            with col2:
                st.markdown(f"**Confidence:** ::{confidence_color}[{confidence_text} ({confidence}%)]")
            
            # Description
            st.markdown(fix_data['description'])
            
            # Code changes
            if 'changes' in fix_data:
                st.markdown("**Proposed Changes:**")
                for change in fix_data['changes']:
                    with st.expander(f"📄 {change['file_path']}"):
                        st.code(change['content'], language='python')
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button("Apply Fix", key=f"apply_{fix_data.get('id', '')}"):
                    st.success("Creating merge request...")
            with col2:
                if st.button("View Details", key=f"details_{fix_data.get('id', '')}"):
                    st.info("Loading details...")
            with col3:
                if st.button("Dismiss", key=f"dismiss_{fix_data.get('id', '')}"):
                    st.warning("Fix dismissed")
            
            st.divider()