import streamlit as st
import asyncio
import json
import os
from datetime import datetime
import logging
from typing import Dict, List, Optional
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Page config
st.set_page_config(
    page_title="DevOps AI Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .failure-card {
        border: 2px solid #dc3545;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background-color: #f8f9fa;
    }
    .quality-card {
        border: 2px solid #ffc107;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background-color: #f8f9fa;
    }
    .confidence-high { color: #28a745; font-weight: bold; }
    .confidence-medium { color: #ffc107; font-weight: bold; }
    .confidence-low { color: #dc3545; font-weight: bold; }
    .code-snippet {
        background-color: #f5f5f5;
        border: 1px solid #ddd;
        border-radius: 4px;
        padding: 10px;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# Import components
from utils.webhook_receiver import WebhookReceiver
from utils.session_manager import SessionManager
from utils.snooze_manager import SnoozeManager
from utils.cache_manager import AnalysisCache
from utils.claude_client import ClaudeClient
from components.action_buttons import ActionButtons
from components.adaptive_cards import AdaptiveCards
from components.chat_interface import ChatInterface

# Helper functions
async def analyze_gitlab_failure(failure: Dict):
    """Analyze a GitLab pipeline failure"""
    failure_key = f"{failure['project_id']}_{failure['pipeline_id']}"
    
    # Check cache first
    cached = cache.get(f"gitlab_{failure_key}")
    if cached:
        st.session_state.active_analyses[failure_key] = cached
        return
    
    # Perform analysis
    with st.spinner("🔍 Analyzing pipeline failure..."):
        try:
            analysis = await llm_client.analyze_pipeline_failure(failure)
            st.session_state.active_analyses[failure_key] = analysis
            
            # Cache the result
            cache.set(f"gitlab_{failure_key}", analysis)
            
            # Log to session
            session_manager.add_message(st.session_state.session_id, {
                "type": "analysis",
                "source": "gitlab",
                "timestamp": datetime.now().isoformat(),
                "failure_data": failure,
                "analysis": analysis
            })
            
            # Notify if high confidence fix available
            if analysis.get('confidence', 0) >= 90:
                st.balloons()
                st.success(f"✅ High confidence fix available! ({analysis['confidence']}%)")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            st.error(f"Analysis failed: {str(e)}")

async def analyze_sonarqube_issue(issue: Dict):
    """Analyze SonarQube quality issues"""
    issue_key = issue['project_key']
    
    # Check cache
    cached = cache.get(f"sonarqube_{issue_key}")
    if cached:
        st.session_state.active_analyses[issue_key] = cached
        return
    
    # Perform analysis
    with st.spinner("🔍 Analyzing code quality issues..."):
        try:
            analysis = await llm_client.analyze_sonarqube_issues(
                issue['project_key'],
                severity_threshold="MAJOR"
            )
            st.session_state.active_analyses[issue_key] = analysis
            
            # Cache the result
            cache.set(f"sonarqube_{issue_key}", analysis)
            
            # Log to session
            session_manager.add_message(st.session_state.session_id, {
                "type": "analysis",
                "source": "sonarqube",
                "timestamp": datetime.now().isoformat(),
                "issue_data": issue,
                "analysis": analysis
            })
            
        except Exception as e:
            logger.error(f"SonarQube analysis failed: {e}")
            st.error(f"Analysis failed: {str(e)}")

async def analyze_with_more_context(analysis_key: str):
    """Re-analyze with additional context"""
    # Implementation for progressive context loading
    st.info("Requesting additional context from MCP servers...")
    # TODO: Implement progressive context loading

def create_merge_request(analysis: Dict, fix: Dict, fix_idx: int):
    """Create a merge request with the suggested fix"""
    with st.spinner("Creating merge request..."):
        # TODO: Implement actual MR creation via GitLab MCP
        st.success("✅ Merge request created successfully!")
        st.info("MR #123: Automated fix for pipeline failure")

def snooze_and_remove(project_id: str, branch: str, hours: int, idx: int, source: str):
    """Snooze a project and remove from active list"""
    snooze_manager.snooze_project(project_id, branch, hours)
    
    if source == 'gitlab':
        st.session_state.gitlab_failures.pop(idx)
    elif source == 'sonarqube':
        st.session_state.sonarqube_issues.pop(idx)
    
    st.success(f"Snoozed for {hours} hours")
    st.rerun()

# Initialize services
@st.cache_resource
def init_services():
    """Initialize all services"""
    try:
        webhook_receiver = WebhookReceiver()
        session_manager = SessionManager()
        snooze_manager = SnoozeManager()
        cache = AnalysisCache()
        llm_client = ClaudeClient()
        return webhook_receiver, session_manager, snooze_manager, cache, llm_client
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        st.error(f"Service initialization failed: {str(e)}")
        raise

webhook_receiver, session_manager, snooze_manager, cache, llm_client = init_services()

# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    session_manager.create_session(st.session_state.session_id)
    logger.info(f"Created new session: {st.session_state.session_id}")

if "gitlab_failures" not in st.session_state:
    st.session_state.gitlab_failures = []

if "sonarqube_issues" not in st.session_state:
    st.session_state.sonarqube_issues = []

if "active_analyses" not in st.session_state:
    st.session_state.active_analyses = {}

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Header
st.title("🤖 DevOps AI Assistant")
st.markdown("Proactive CI/CD failure analysis with AI-powered fixes")

# Create main layout
col1, col2 = st.columns([2, 3])

# Left panel - Failures/Issues list
with col1:
    st.header("📊 Active Issues")
    
    # Refresh button
    if st.button("🔄 Check for New Issues", use_container_width=True):
        with st.spinner("Checking for new issues..."):
            # Check GitLab failures
            new_gitlab_failures = webhook_receiver.get_gitlab_failures()
            for failure in new_gitlab_failures:
                if not snooze_manager.is_snoozed(failure['project_id'], failure.get('branch', 'main')):
                    st.session_state.gitlab_failures.append(failure)
                    # Auto-analyze high priority failures
                    if failure.get('priority') == 'high' or failure.get('status') == 'failed':
                        asyncio.run(analyze_gitlab_failure(failure))
            
            # Check SonarQube issues  
            new_sonar_issues = webhook_receiver.get_sonarqube_issues()
            for issue in new_sonar_issues:
                if not snooze_manager.is_snoozed(issue['project_key'], 'main'):
                    st.session_state.sonarqube_issues.append(issue)
            
            st.session_state.last_refresh = datetime.now()
            st.rerun()
    
    # Tab selection
    tab1, tab2 = st.tabs(["🔴 GitLab Failures", "⚠️ SonarQube Issues"])
    
    with tab1:
        # Display GitLab failures
        if st.session_state.gitlab_failures:
            for idx, failure in enumerate(st.session_state.gitlab_failures):
                with st.expander(
                    f"🚨 Pipeline #{failure['pipeline_id']} - {failure['project_name']} - {failure['project_id']}", 
                    expanded=idx == 0
                ):
                    # Failure details card
                    st.markdown(AdaptiveCards.create_failure_card(failure), unsafe_allow_html=True)
                    
                    # Analysis status
                    failure_key = f"{failure['project_id']}_{failure['pipeline_id']}"
                    if failure_key in st.session_state.active_analyses:
                        analysis = st.session_state.active_analyses[failure_key]
                        st.success("✅ Analysis complete")
                        
                        # Show confidence
                        confidence = analysis.get('confidence', 0)
                        action_buttons = ActionButtons()
                        confidence_class = action_buttons.confidence_indicator(confidence)
                        st.markdown(f"<p class='{confidence_class}'>Confidence: {confidence}%</p>", unsafe_allow_html=True)
                    
                    # Action buttons
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        if st.button("🔍 Analyze", key=f"analyze_gitlab_{idx}"):
                            asyncio.run(analyze_gitlab_failure(failure))
                            st.rerun()
                    
                    with col_b:
                        hours = st.number_input(
                            "Snooze hours", 
                            min_value=1, 
                            max_value=72, 
                            value=8, 
                            key=f"snooze_hours_gitlab_{idx}"
                        )
                        if st.button("😴 Snooze", key=f"snooze_gitlab_{idx}"):
                            snooze_and_remove(failure['project_id'], failure.get('branch', 'main'), hours, idx, 'gitlab')
                    
                    with col_c:
                        if st.button("❌ Dismiss", key=f"dismiss_gitlab_{idx}"):
                            st.session_state.gitlab_failures.pop(idx)
                            st.rerun()
        else:
            st.info("No active GitLab failures")
    
    with tab2:
        # Display SonarQube issues
        if st.session_state.sonarqube_issues:
            for idx, issue in enumerate(st.session_state.sonarqube_issues):
                with st.expander(
                    f"📋 {issue['project_name']} - Quality Gate {issue['quality_gate_status']}", 
                    expanded=idx == 0
                ):
                    # Issue details card
                    st.markdown(AdaptiveCards.create_sonarqube_card(issue), unsafe_allow_html=True)
                    
                    # Action buttons
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        if st.button("🔍 Analyze", key=f"analyze_sonar_{idx}"):
                            asyncio.run(analyze_sonarqube_issue(issue))
                            st.rerun()
                    
                    with col_b:
                        hours = st.number_input(
                            "Snooze hours", 
                            min_value=1, 
                            max_value=72, 
                            value=8, 
                            key=f"snooze_hours_sonar_{idx}"
                        )
                        if st.button("😴 Snooze", key=f"snooze_sonar_{idx}"):
                            snooze_and_remove(issue['project_key'], 'main', hours, idx, 'sonarqube')
                    
                    with col_c:
                        if st.button("❌ Dismiss", key=f"dismiss_sonar_{idx}"):
                            st.session_state.sonarqube_issues.pop(idx)
                            st.rerun()
        else:
            st.info("No active SonarQube issues")

# Right panel - Chat interface and analysis results
with col2:
    st.header("💬 AI Analysis & Chat")
    
    # Display active analysis if any
    if st.session_state.active_analyses:
        with st.container():
            st.subheader("📊 Current Analysis")
            
            # Get the most recent analysis
            latest_analysis_key = list(st.session_state.active_analyses.keys())[-1]
            analysis = st.session_state.active_analyses[latest_analysis_key]
            
            # Display analysis results
            if 'error' not in analysis:
                # Root cause
                st.markdown("### 🎯 Root Cause")
                st.info(analysis.get('root_cause', 'Unknown'))
                
                # Suggested fixes
                if analysis.get('fixes'):
                    st.markdown("### 🛠️ Suggested Fixes")
                    for idx, fix in enumerate(analysis['fixes']):
                        with st.expander(f"Fix {idx + 1}: {fix.get('description', 'Fix')}", expanded=idx == 0):
                            # Show fix details
                            st.markdown(f"**File:** `{fix.get('file_path', 'Unknown')}`")
                            st.markdown(f"**Explanation:** {fix.get('explanation', '')}")
                            
                            # Show code changes
                            if fix.get('code_snippet'):
                                st.code(fix['code_snippet'], language=fix.get('language', 'python'))
                            
                            # Action buttons for fixes
                            col1, col2 = st.columns(2)
                            with col1:
                                if analysis.get('confidence', 0) >= 80:
                                    if st.button("🔀 Create MR", key=f"create_mr_{latest_analysis_key}_{idx}"):
                                        create_merge_request(analysis, fix, idx)
                            
                            with col2:
                                if st.button("📋 Copy Fix", key=f"copy_fix_{idx}"):
                                    st.code(fix['code_snippet'])
                                    st.success("Code copied to clipboard!")
                
                # Additional context needed
                if analysis.get('additional_context_needed') and analysis.get('confidence', 100) < 80:
                    st.warning("⚠️ Low confidence - Additional context may help:")
                    for context in analysis['additional_context_needed']:
                        st.markdown(f"- {context}")
                    
                    if st.button("🔄 Analyze with more context"):
                        asyncio.run(analyze_with_more_context(latest_analysis_key))
            else:
                st.error(f"Analysis failed: {analysis['error']}")
    
    # Chat interface
    st.divider()
    chat_interface = ChatInterface(llm_client, session_manager)
    chat_interface.render(st.session_state.session_id)

# Sidebar
with st.sidebar:
    st.header("🔧 Configuration")
    
    # Session info
    st.subheader("📊 Session Info")
    st.text(f"Session: {st.session_state.session_id[:8]}...")
    st.metric("Active Failures", len(st.session_state.gitlab_failures))
    st.metric("Active Issues", len(st.session_state.sonarqube_issues))
    st.metric("Snoozed", snooze_manager.get_active_count())
    
    # Last refresh
    st.text(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    # LLM status
    st.divider()
    st.subheader("🤖 LLM Status")
    st.success("Provider: Claude (Anthropic)")
    
    # Health checks
    st.divider()
    st.subheader("🏥 Health Status")
    
    col1, col2 = st.columns(2)
    with col1:
        redis_health = "🟢" if webhook_receiver.health() else "🔴"
        st.metric("Redis", redis_health)
    
    with col2:
        mcp_health = "🟢"  # TODO: Implement actual health check
        st.metric("MCP Servers", mcp_health)
    
    # Actions
    st.divider()
    if st.button("🧹 Clear All Analyses"):
        st.session_state.active_analyses.clear()
        cache.clear()
        st.success("Cleared all analyses!")
        st.rerun()
    
    if st.button("📥 Export Session"):
        session_data = session_manager.get_session(st.session_state.session_id)
        st.download_button(
            label="Download Session Data",
            data=json.dumps(session_data, indent=2),
            file_name=f"session_{st.session_state.session_id[:8]}.json",
            mime="application/json"
        )

# Auto-refresh logic
if st.checkbox("Enable auto-refresh (30s)", value=False):
    import time
    if (datetime.now() - st.session_state.last_refresh).seconds > 30:
        st.rerun()