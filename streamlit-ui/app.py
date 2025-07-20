# streamlit-ui/app.py - Updated without MCP dependencies
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
    .mr-preview {
        background-color: #e7f3ff;
        border: 1px solid #0066cc;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
    }
</style>
""", unsafe_allow_html=True)

# Import components
from utils.webhook_receiver import WebhookReceiver
from utils.session_manager import SessionManager
from utils.snooze_manager import SnoozeManager
from utils.cache_manager import AnalysisCache
from utils.llm_providers import LLMProviderFactory
from components.action_buttons import ActionButtons
from components.adaptive_cards import AdaptiveCards
from components.chat_interface import ChatInterface

# Initialize services
@st.cache_resource
def init_services():
    """Initialize all services"""
    try:
        webhook_receiver = WebhookReceiver()
        session_manager = SessionManager()
        snooze_manager = SnoozeManager()
        cache = AnalysisCache()
        llm_client = LLMProviderFactory.create_provider()  # Auto-detects provider from env
        return webhook_receiver, session_manager, snooze_manager, cache, llm_client
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        st.error(f"Service initialization failed: {str(e)}")
        raise

webhook_receiver, session_manager, snooze_manager, cache, llm_client = init_services()

# Helper functions
async def analyze_gitlab_failure(failure: Dict):
    """Analyze a GitLab pipeline failure - ALL analysis from LLM"""
    failure_key = f"{failure['project_id']}_{failure['pipeline_id']}"
    
    # Check cache first
    cached = cache.get(f"gitlab_{failure_key}")
    if cached:
        st.session_state.active_analyses[failure_key] = cached
        return
    
    # Perform analysis using LLM provider
    with st.spinner(f"🔍 Analyzing with {llm_client.__class__.__name__}..."):
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
            
            # Show confidence-based feedback
            confidence = analysis.get('confidence', 0)
            if confidence >= 90:
                st.balloons()
                st.success(f"✅ High confidence analysis! ({confidence}%)")
            elif confidence >= 70:
                st.warning(f"⚠️ Medium confidence analysis ({confidence}%)")
            else:
                st.info(f"💡 Low confidence analysis ({confidence}%) - Consider requesting more context")
            
        except Exception as e:
            logger.error(f"Analysis failed: {e}")
            st.error(f"Analysis failed: {str(e)}")

async def analyze_sonarqube_issue(issue: Dict):
    """Analyze SonarQube quality issues - ALL analysis from LLM"""
    issue_key = issue['project_key']
    
    # Check cache
    cached = cache.get(f"sonarqube_{issue_key}")
    if cached:
        st.session_state.active_analyses[issue_key] = cached
        return
    
    # Perform analysis using LLM provider
    with st.spinner(f"🔍 Analyzing quality issues with {llm_client.__class__.__name__}..."):
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

def show_merge_request_preview(analysis: Dict, analysis_key: str, fix_idx: int):
    """Show MR preview and creation controls - USER DECIDES"""
    fix = analysis['fixes'][fix_idx]
    
    with st.expander("📋 Merge Request Preview", expanded=True):
        st.markdown('<div class="mr-preview">', unsafe_allow_html=True)
        
        # MR Details Form
        col1, col2 = st.columns(2)
        
        with col1:
            mr_title = st.text_input(
                "MR Title", 
                value=f"Fix: {fix.get('description', 'Pipeline failure fix')}",
                key=f"mr_title_{analysis_key}_{fix_idx}"
            )
            
            target_branch = st.selectbox(
                "Target Branch",
                ["main", "develop", "master"],
                key=f"target_branch_{analysis_key}_{fix_idx}"
            )
        
        with col2:
            source_branch = st.text_input(
                "Source Branch",
                value=f"fix-pipeline-{analysis_key}-{datetime.now().strftime('%Y%m%d-%H%M')}",
                key=f"source_branch_{analysis_key}_{fix_idx}"
            )
            
            assign_to_author = st.checkbox(
                "Assign to original author",
                value=True,
                key=f"assign_author_{analysis_key}_{fix_idx}"
            )
        
        # MR Description
        mr_description = st.text_area(
            "MR Description",
            value=f"""## Automated Fix for Pipeline Failure

**Root Cause:** {analysis.get('root_cause', 'Unknown')}

**Fix Applied:** {fix.get('explanation', 'No explanation available')}

**Confidence:** {analysis.get('confidence', 0)}%

**Generated by:** {analysis.get('llm_provider', 'AI Assistant')}

## Changes Made
- {fix.get('file_path', 'Unknown file')}

Please review the changes carefully before merging.
""",
            height=150,
            key=f"mr_desc_{analysis_key}_{fix_idx}"
        )
        
        # Code Preview
        st.markdown("### 📝 Code Changes Preview")
        st.markdown(f"**File:** `{fix.get('file_path', 'Unknown')}`")
        
        if fix.get('code_snippet'):
            st.code(fix['code_snippet'], language=fix.get('language', 'python'))
        
        # Action Buttons
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button(
                "🔀 Create Merge Request", 
                key=f"create_mr_{analysis_key}_{fix_idx}",
                type="primary"
            ):
                if mr_title.strip() and source_branch.strip():
                    create_merge_request(analysis, {
                        "title": mr_title,
                        "source_branch": source_branch,
                        "target_branch": target_branch,
                        "description": mr_description,
                        "assign_to_author": assign_to_author,
                        "file_path": fix.get('file_path'),
                        "content": fix.get('code_snippet'),
                        "action": "update"
                    }, fix_idx)
                else:
                    st.error("Please provide both title and source branch name")
        
        with col2:
            if st.button(
                "📋 Copy Code", 
                key=f"copy_code_{analysis_key}_{fix_idx}"
            ):
                st.code(fix.get('code_snippet', ''), language=fix.get('language', 'text'))
                st.info("💡 Code displayed above - select and copy manually")
        
        with col3:
            if st.button(
                "💬 Discuss Fix", 
                key=f"discuss_fix_{analysis_key}_{fix_idx}"
            ):
                st.session_state.chat_context = {
                    "type": "fix_discussion",
                    "fix": fix,
                    "analysis": analysis,
                    "analysis_key": analysis_key
                }
                st.info("💬 Added to chat context - ask questions in the chat below")
        
        st.markdown('</div>', unsafe_allow_html=True)

def create_merge_request(analysis: Dict, mr_data: Dict, fix_idx: int):
    """Create merge request via API - USER INITIATED ONLY"""
    with st.spinner("Creating merge request..."):
        try:
            # Extract project info from analysis
            project_id = analysis.get('project_id')
            if not project_id:
                # Try to get from session state or failure data
                st.error("Cannot determine project ID for MR creation")
                return
            
            # Prepare changes
            changes = [{
                "file_path": mr_data["file_path"],
                "content": mr_data["content"],
                "action": mr_data.get("action", "update")
            }]
            
            # Call GitLab API to create MR
            import httpx
            async def create_mr():
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{os.environ.get('GITLAB_API_URL')}/projects/{project_id}/merge-request",
                        json={
                            "source_branch": mr_data["source_branch"],
                            "title": mr_data["title"],
                            "changes": changes,
                            "target_branch": mr_data["target_branch"],
                            "description": mr_data["description"],
                            "assign_to_author": mr_data["assign_to_author"]
                        }
                    )
                    response.raise_for_status()
                    return response.json()
            
            result = asyncio.run(create_mr())
            
            st.success("✅ Merge request created successfully!")
            st.markdown(f"**MR URL:** [View Merge Request]({result.get('merge_request_url', '#')})")
            st.markdown(f"**MR ID:** {result.get('merge_request_iid', 'Unknown')}")
            st.markdown(f"**Branch:** `{result.get('source_branch', 'Unknown')}`")
            
            # Log MR creation
            session_manager.add_message(st.session_state.session_id, {
                "type": "mr_created",
                "timestamp": datetime.now().isoformat(),
                "mr_data": result,
                "fix_data": mr_data
            })
            
        except Exception as e:
            logger.error(f"MR creation failed: {e}")
            st.error(f"❌ Failed to create merge request: {str(e)}")
            st.info("💡 You can manually apply the fix using the code snippet above")

def snooze_and_remove(project_id: str, branch: str, hours: int, idx: int, source: str):
    """Snooze a project and remove from active list"""
    snooze_manager.snooze_project(project_id, branch, hours)
    
    if source == 'gitlab':
        st.session_state.gitlab_failures.pop(idx)
    elif source == 'sonarqube':
        st.session_state.sonarqube_issues.pop(idx)
    
    st.success(f"😴 Snoozed for {hours} hours")
    st.rerun()

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
current_provider = os.environ.get('LLM_PROVIDER', 'claude').title()
st.markdown(f"Powered by **{current_provider}** • Proactive CI/CD failure analysis with AI-powered fixes")

with st.expander("🐛 Debug Info", expanded=False):
    st.subheader("Environment Variables")
    llm_provider = os.environ.get('LLM_PROVIDER', 'not-set')
    st.write(f"**LLM_PROVIDER**: {llm_provider}")
    st.write(f"**GITLAB_API_URL**: {os.environ.get('GITLAB_API_URL', 'not-set')}")
    st.write(f"**SONARQUBE_API_URL**: {os.environ.get('SONARQUBE_API_URL', 'not-set')}")
    
    st.subheader("LLM Client Info")
    try:
        st.write(f"**Client Type**: {type(llm_client).__name__}")
        st.write(f"**Client Module**: {type(llm_client).__module__}")
    except:
        st.write("**Client**: Failed to get client info")
    
    # Test connectivity
    if st.button("Test API Connectivity"):
        with st.spinner("Testing..."):
            try:
                connectivity = asyncio.run(llm_client.test_connectivity())
                st.json(connectivity)
            except Exception as e:
                st.error(f"Connectivity test failed: {e}")
                
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
                    # Auto-analyze high priority failures (if enabled in settings)
                    if failure.get('priority') == 'high' or failure.get('status') == 'failed':
                        if st.session_state.get('auto_analyze_enabled', True):
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
                    f"🚨 Pipeline #{failure['pipeline_id']} - {failure['project_name']}", 
                    expanded=idx == 0
                ):
                    # Failure details card
                    st.markdown(AdaptiveCards.create_failure_card(failure), unsafe_allow_html=True)
                    
                    # Analysis status
                    failure_key = f"{failure['project_id']}_{failure['pipeline_id']}"
                    if failure_key in st.session_state.active_analyses:
                        analysis = st.session_state.active_analyses[failure_key]
                        
                        # Show analysis results
                        if 'error' not in analysis:
                            confidence = analysis.get('confidence', 0)
                            confidence_class = "high" if confidence >= 80 else "medium" if confidence >= 60 else "low"
                            
                            st.success("✅ Analysis complete")
                            st.markdown(f"<p class='confidence-{confidence_class}'>Confidence: {confidence}% ({analysis.get('llm_provider', 'AI')})</p>", unsafe_allow_html=True)
                            
                            # Root cause
                            st.markdown("**🎯 Root Cause:**")
                            st.info(analysis.get('root_cause', 'Unknown'))
                            
                            # Show fixes with MR creation option
                            if analysis.get('fixes'):
                                st.markdown("**🛠️ Suggested Fixes:**")
                                for fix_idx, fix in enumerate(analysis['fixes']):
                                    with st.expander(f"Fix {fix_idx + 1}: {fix.get('description', 'Fix')}", expanded=fix_idx == 0):
                                        st.markdown(f"**File:** `{fix.get('file_path', 'Unknown')}`")
                                        st.markdown(f"**Explanation:** {fix.get('explanation', '')}")
                                        
                                        if fix.get('code_snippet'):
                                            st.code(fix['code_snippet'], language=fix.get('language', 'python'))
                                        
                                        # MR Creation Button - USER DECIDES
                                        if confidence >= 70:  # Only show for reasonable confidence
                                            if st.button(
                                                "🔀 Prepare Merge Request", 
                                                key=f"prep_mr_{failure_key}_{fix_idx}",
                                                help="Review and create merge request with this fix"
                                            ):
                                                st.session_state[f"show_mr_preview_{failure_key}_{fix_idx}"] = True
                                                st.rerun()
                                        
                                        # Show MR preview if requested
                                        if st.session_state.get(f"show_mr_preview_{failure_key}_{fix_idx}", False):
                                            show_merge_request_preview(analysis, failure_key, fix_idx)
                        else:
                            st.error(f"Analysis failed: {analysis['error']}")
                    
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
        # Display SonarQube issues (similar pattern)
        if st.session_state.sonarqube_issues:
            for idx, issue in enumerate(st.session_state.sonarqube_issues):
                with st.expander(
                    f"📋 {issue['project_name']} - Quality Gate {issue['quality_gate_status']}", 
                    expanded=idx == 0
                ):
                    # Issue details card
                    st.markdown(AdaptiveCards.create_sonarqube_card(issue), unsafe_allow_html=True)
                    
                    # Analysis results if available
                    if issue['project_key'] in st.session_state.active_analyses:
                        analysis = st.session_state.active_analyses[issue['project_key']]
                        if 'error' not in analysis:
                            st.success("✅ Analysis complete")
                            st.markdown(f"**Summary:** {analysis.get('summary', 'N/A')}")
                            
                            # Show priority issues with fix options
                            if analysis.get('priority_issues'):
                                st.markdown("**🔧 Priority Fixes:**")
                                for fix_idx, fix in enumerate(analysis['priority_issues'][:3]):  # Top 3
                                    with st.expander(f"Fix {fix_idx + 1}: {fix.get('problem', 'Issue')}", expanded=fix_idx == 0):
                                        st.markdown(f"**File:** `{fix.get('file_path', 'Unknown')}` (Line {fix.get('line', 'N/A')})")
                                        st.markdown(f"**Problem:** {fix.get('problem', '')}")
                                        
                                        if fix.get('fix', {}).get('code'):
                                            st.code(fix['fix']['code'], language=fix.get('language', 'python'))
                                        
                                        st.markdown(f"**Confidence:** {fix.get('confidence', 0)}%")
                    
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
    
    # Chat interface
    chat_interface = ChatInterface(llm_client, session_manager)
    chat_interface.render(st.session_state.session_id)

# Sidebar
with st.sidebar:
    st.header("🔧 Configuration")
    
    # LLM Provider Info
    st.subheader(f"🤖 Current LLM: {current_provider}")
    model_name = ""
    if current_provider.lower() == "claude":
        model_name = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")
    elif current_provider.lower() == "bedrock":
        model_name = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20241022-v2:0")
    elif current_provider.lower() == "openai":
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    st.info(f"Model: {model_name}")
    
    # Session info
    st.subheader("📊 Session Info")
    st.text(f"Session: {st.session_state.session_id[:8]}...")
    st.metric("Active Failures", len(st.session_state.gitlab_failures))
    st.metric("Active Issues", len(st.session_state.sonarqube_issues))
    st.metric("Snoozed", snooze_manager.get_active_count())
    
    # Settings
    st.subheader("⚙️ Settings")
    st.session_state.auto_analyze_enabled = st.checkbox(
        "Auto-analyze high priority failures",
        value=st.session_state.get('auto_analyze_enabled', True),
        help="Automatically analyze failures marked as high priority"
    )
    
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