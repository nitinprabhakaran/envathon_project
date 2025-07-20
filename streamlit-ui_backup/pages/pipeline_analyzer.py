import streamlit as st
import asyncio
from datetime import datetime
import json

class PipelineAnalyzer:
    def __init__(self, claude_client, session_manager):
        self.claude_client = claude_client
        self.session_manager = session_manager
    
    def render_failure_analysis(self, failure_data):
        """Render pipeline failure with progressive analysis"""
        conversation_id = f"{failure_data['project_id']}_{failure_data['pipeline_id']}"
        
        # Create expandable section for this failure
        with st.expander(f"🚨 {failure_data['project_name']} - Pipeline #{failure_data['pipeline_id']}", expanded=True):
            # Basic info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Branch", failure_data['ref'])
            with col2:
                st.metric("Commit", failure_data['sha'][:8])
            with col3:
                st.metric("Failed At", failure_data.get('created_at', 'Unknown'))
            
            st.markdown(f"**Commit Message:** {failure_data['commit']['message']}")
            st.markdown(f"**Author:** {failure_data['user']['name']} ({failure_data['user']['email']})")
            
            # Analysis section
            st.subheader("🔍 Analysis")
            
            # Check if we have existing analysis
            analysis_key = f"analysis_{conversation_id}"
            if analysis_key not in st.session_state:
                st.session_state[analysis_key] = None
            
            # Analysis controls
            col1, col2 = st.columns([3, 1])
            
            with col1:
                if st.session_state[analysis_key]:
                    analysis = st.session_state[analysis_key]
                    
                    # Show confidence with color coding
                    confidence = analysis.get('confidence', 0)
                    confidence_color = self._get_confidence_color(confidence)
                    st.markdown(f"**Confidence:** :{confidence_color}[{confidence}%]")
                    
                    # Show confidence factors if available
                    if 'confidence_factors' in analysis:
                        with st.expander("Confidence Breakdown"):
                            factors = analysis['confidence_factors']
                            st.metric("Context Completeness", f"{factors.get('context_completeness', 0)}%")
                            st.metric("Error Clarity", f"{factors.get('error_clarity', 0)}%")
                            st.metric("Fix Certainty", f"{factors.get('fix_certainty', 0)}%")
                    
                    # Show analysis
                    st.markdown("**Root Cause:**")
                    st.info(analysis.get('root_cause', 'Not identified'))
                    
                    st.markdown("**Detailed Analysis:**")
                    st.markdown(analysis.get('analysis', 'No analysis available'))
                    
                    # Show context level used
                    context_level = analysis.get('context_level_used', 1)
                    st.caption(f"Analysis performed with context level {context_level} of 4")
                    
                    # Show if more context is needed
                    if analysis.get('need_more_context', False):
                        st.warning("⚠️ Additional context may improve analysis accuracy")
                        context_needed = analysis.get('context_needed', [])
                        if context_needed:
                            st.markdown(f"**Suggested additional context:** {', '.join(context_needed)}")
            
            with col2:
                # Analysis button
                analyze_label = "🔍 Analyze" if not st.session_state[analysis_key] else "🔄 Re-analyze"
                if st.button(analyze_label, key=f"analyze_{conversation_id}"):
                    with st.spinner("Analyzing pipeline failure..."):
                        analysis = asyncio.run(
                            self.claude_client.analyze_pipeline_failure(failure_data, conversation_id)
                        )
                        st.session_state[analysis_key] = analysis
                        st.rerun()
                
                # Request more context button
                if st.session_state[analysis_key] and st.session_state[analysis_key].get('can_provide_more_context', False):
                    if st.button("📊 More Context", key=f"context_{conversation_id}"):
                        with st.spinner("Upgrading context..."):
                            result = asyncio.run(
                                self.claude_client.request_more_context(conversation_id)
                            )
                            st.success(result['message'])
                            # Re-analyze with more context
                            analysis = asyncio.run(
                                self.claude_client.analyze_pipeline_failure(failure_data, conversation_id)
                            )
                            st.session_state[analysis_key] = analysis
                            st.rerun()
            
            # Fix generation section
            if st.session_state[analysis_key]:
                st.subheader("🛠️ Fix Suggestions")
                
                fixes_key = f"fixes_{conversation_id}"
                if fixes_key not in st.session_state:
                    st.session_state[fixes_key] = None
                
                if st.button("Generate Fixes", key=f"gen_fixes_{conversation_id}"):
                    with st.spinner("Generating fix suggestions..."):
                        fixes = asyncio.run(
                            self.claude_client.generate_fixes(failure_data, conversation_id)
                        )
                        st.session_state[fixes_key] = fixes
                        st.rerun()
                
                if st.session_state[fixes_key]:
                    fixes_data = st.session_state[fixes_key]
                    
                    if 'fixes' in fixes_data:
                        for idx, fix in enumerate(fixes_data['fixes']):
                            self._render_fix_suggestion(fix, idx, conversation_id)
                    
                    # Show alternative approaches if any
                    if 'alternative_approaches' in fixes_data:
                        with st.expander("Alternative Approaches"):
                            for alt in fixes_data['alternative_approaches']:
                                st.markdown(f"**{alt['description']}**")
                                st.caption(f"Use when: {alt['when_to_use']}")
    
    def _render_fix_suggestion(self, fix, idx, conversation_id):
        """Render individual fix suggestion"""
        confidence = fix.get('confidence', 0)
        confidence_color = self._get_confidence_color(confidence)
        
        with st.container():
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.markdown(f"**Fix {idx + 1}: {fix['title']}**")
            with col2:
                st.markdown(f"Confidence: :{confidence_color}[{confidence}%]")
            
            st.markdown(fix['description'])
            
            # Show confidence reasoning
            if 'confidence_reasoning' in fix:
                with st.expander("Why this confidence?"):
                    st.markdown(fix['confidence_reasoning'])
                    if 'requires_context' in fix:
                        st.markdown(f"**Would benefit from:** {', '.join(fix['requires_context'])}")
            
            # Show code changes
            if 'changes' in fix:
                with st.expander("View Code Changes"):
                    for change in fix['changes']:
                        st.markdown(f"**File:** `{change['file_path']}`")
                        st.markdown(f"**Action:** {change['change_type']}")
                        if 'line_range' in change:
                            st.caption(f"Lines {change['line_range'][0]}-{change['line_range'][1]}")
                        st.code(change['content'], language='python')
            
            # Show warnings
            if 'potential_side_effects' in fix:
                with st.expander("⚠️ Potential Side Effects"):
                    for effect in fix['potential_side_effects']:
                        st.markdown(f"- {effect}")
            
            if 'testing_required' in fix:
                with st.expander("🧪 Testing Required"):
                    for test in fix['testing_required']:
                        st.markdown(f"- {test}")
            
            # Action buttons
            col1, col2, col3 = st.columns(3)
            with col1:
                if st.button(f"Apply Fix", key=f"apply_{conversation_id}_{idx}"):
                    st.info("Creating merge request...")
            with col2:
                if st.button(f"Test Locally", key=f"test_{conversation_id}_{idx}"):
                    st.info("Running local tests...")
            with col3:
                if confidence < 70:
                    if st.button(f"Get More Context", key=f"more_{conversation_id}_{idx}"):
                        st.info("Fetching additional context...")
            
            st.divider()
    
    def _get_confidence_color(self, confidence):
        """Get color based on confidence score"""
        if confidence >= 80:
            return "green"
        elif confidence >= 60:
            return "orange"
        else:
            return "red"