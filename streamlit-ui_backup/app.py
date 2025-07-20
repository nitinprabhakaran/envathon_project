# streamlit-ui/app.py
import streamlit as st
import os
import asyncio
from datetime import datetime
import json
from pathlib import Path
import logging

# Import LLM clients
from utils.base_llm_client import BaseLLMClient
from utils.webhook_receiver import WebhookReceiver
from utils.snooze_manager import SnoozeManager
from utils.cache_manager import AnalysisCache

# Initialize components
logger = logging.getLogger(__name__)
@st.cache_resource
def init_llm_client():
    """Initialize LLM client based on environment settings"""
    llm_provider = os.environ.get("LLM_PROVIDER", "claude")
    logger.info(f"Initializing LLM client with provider: {llm_provider}")
    
    try:
        if llm_provider == "claude":
            from utils.claude_client import ClaudeClient
            logger.info("Claude client initialized successfully")
            return ClaudeClient()
        elif llm_provider == "openai":
            from utils.openai_client import OpenAIClient
            return OpenAIClient()
        elif llm_provider == "gemini":
            from utils.gemini_client import GeminiClient
            return GeminiClient()
        elif llm_provider == "ollama":
            from utils.ollama_client import OllamaClient
            return OllamaClient()
        elif llm_provider == "multi":
            from utils.multi_llm_client import MultiLLMClient
            return MultiLLMClient()
        else:
            # Default to multi-client with fallback
            from utils.multi_llm_client import MultiLLMClient
            return MultiLLMClient()
    except Exception as e:
        logger.error(f"Failed to initialize {llm_provider} client: {str(e)}")
        st.error(f"Failed to initialize LLM client: {e}")
        # Try multi-client as last resort
        try:
            from utils.multi_llm_client import MultiLLMClient
            return MultiLLMClient()
        except:
            raise

# Initialize services
llm_client = init_llm_client()
webhook_receiver = WebhookReceiver()
snooze_manager = SnoozeManager()
cache = AnalysisCache() if os.environ.get("ENABLE_CACHE", "true").lower() == "true" else None

# Streamlit configuration
st.set_page_config(
    page_title="DevOps AI Assistant",
    page_icon="🤖",
    layout="wide"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stAlert {
        margin-top: 1rem;
    }
    .analysis-card {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
        background-color: #f8f9fa;
    }
    .confidence-high {
        color: #28a745;
        font-weight: bold;
    }
    .confidence-medium {
        color: #ffc107;
        font-weight: bold;
    }
    .confidence-low {
        color: #dc3545;
        font-weight: bold;
    }
    .code-block {
        background-color: #f5f5f5;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        overflow-x: auto;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("🔧 Configuration")
    
    # LLM Provider Information
    st.subheader("LLM Settings")
    current_provider = os.environ.get("LLM_PROVIDER", "gemini")
    current_model = ""
    
    if current_provider == "gemini":
        current_model = os.environ.get("GEMINI_MODEL", "gemini-1.5-pro")
    elif current_provider == "claude":
        current_model = os.environ.get("CLAUDE_MODEL", "claude-3-sonnet-20240229")
    elif current_provider == "openai":
        current_model = os.environ.get("OPENAI_MODEL", "gpt-4-turbo-preview")
    
    st.info(f"**Provider:** {current_provider.upper()}\n\n**Model:** {current_model}")

    # Debug section
    with st.expander("🐛 Debug Info"):
        st.subheader("Session State")
        st.json({
            "messages_count": len(st.session_state.messages),
            "failures_count": {
                "gitlab": len(st.session_state.failures.get("gitlab", [])),
                "sonarqube": len(st.session_state.failures.get("sonarqube", []))
            },
            "active_analysis": bool(st.session_state.active_analysis)
        })
        
        # Show recent logs
        if st.button("Show Recent Logs"):
            log_file = "/app/streamlit.log"  # You'll need to configure this
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    logs = f.readlines()[-50:]  # Last 50 lines
                    st.text_area("Recent Logs", value="".join(logs), height=300)
        
        # Test connections
        if st.button("Test Connections"):
            col1, col2 = st.columns(2)
            with col1:
                try:
                    import httpx
                    response = httpx.get(f"{os.environ.get('GITLAB_MCP_URL')}/health")
                    st.success(f"GitLab MCP: {response.status_code}")
                except Exception as e:
                    st.error(f"GitLab MCP: {str(e)}")
            
            with col2:
                try:
                    # Test Gemini
                    test_response = genai.GenerativeModel('gemini-pro').generate_content("Hello")
                    st.success("Gemini API: Connected")
                except Exception as e:
                    st.error(f"Gemini API: {str(e)}")
    
    # Dynamic LLM switching
    with st.expander("Change LLM Provider"):
        new_provider = st.selectbox(
            "Select Provider",
            ["gemini", "claude", "openai", "multi"],
            index=["gemini", "claude", "openai", "multi"].index(current_provider)
        )
        
        if new_provider == "gemini":
            new_model = st.selectbox(
                "Select Model",
                ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
                index=0
            )
        elif new_provider == "claude":
            new_model = st.selectbox(
                "Select Model",
                ["claude-3-opus-20240229", "claude-3-sonnet-20240229", "claude-3-haiku-20240307"],
                index=1
            )
        elif new_provider == "openai":
            new_model = st.selectbox(
                "Select Model",
                ["gpt-4-turbo-preview", "gpt-3.5-turbo"],
                index=0
            )
        else:
            new_model = "auto"
        
        if st.button("Apply Changes"):
            os.environ["LLM_PROVIDER"] = new_provider
            if new_provider == "gemini":
                os.environ["GEMINI_MODEL"] = new_model
            elif new_provider == "claude":
                os.environ["CLAUDE_MODEL"] = new_model
            elif new_provider == "openai":
                os.environ["OPENAI_MODEL"] = new_model
            st.rerun()
    
    st.divider()
    
    # System Status
    st.subheader("System Status")
    
    # Check service health
    import httpx
    
    async def check_health(url):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{url}/health", timeout=2.0)
                return response.status_code == 200
        except:
            return False
    
    # Run health checks
    gitlab_healthy = asyncio.run(check_health(os.environ.get("GITLAB_MCP_URL", "http://gitlab-mcp:8000")))
    sonar_healthy = asyncio.run(check_health(os.environ.get("SONARQUBE_MCP_URL", "http://sonarqube-mcp:8000")))
    
    st.metric("GitLab MCP", "🟢 Online" if gitlab_healthy else "🔴 Offline")
    st.metric("SonarQube MCP", "🟢 Online" if sonar_healthy else "🔴 Offline")
    
    # Cache statistics
    if cache:
        st.divider()
        st.subheader("Cache Statistics")
        cache_stats = cache.get_stats()
        st.metric("Cache Hits", cache_stats.get("hits", 0))
        st.metric("Cache Size", f"{cache_stats.get('size', 0)} MB")
        
        if st.button("Clear Cache"):
            cache.clear()
            st.success("Cache cleared!")

# Main content
st.title("🤖 DevOps AI Assistant")
st.markdown("Intelligent CI/CD failure analysis and code quality improvement")

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "failures" not in st.session_state:
    st.session_state.failures = {"gitlab": [], "sonarqube": []}
if "active_analysis" not in st.session_state:
    st.session_state.active_analysis = None

# Tabs for different views
tab1, tab2, tab3, tab4 = st.tabs(["🚨 Active Issues", "💬 Chat", "📊 Analytics", "📚 History"])

with tab1:
    search_query = st.text_input("🔍 Search by Pipeline ID or Project Name", placeholder="Enter pipeline ID or project name...")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔴 GitLab Pipeline Failures")
        
        failures = webhook_receiver.get_recent_failures("gitlab", limit=10)
        
        # Filter failures based on search
        if search_query:
            failures = [f for f in failures if 
                       search_query.lower() in str(f.get('pipeline_id', '')).lower() or
                       search_query.lower() in f.get('project_name', '').lower()]
        
        if not failures:
            st.info("No pipeline failures found" + (f" matching '{search_query}'" if search_query else ""))
        
        for failure in failures:
            if not snooze_manager.is_snoozed(failure["project_id"], failure["branch"]):
                # Use pipeline ID as the main identifier
                with st.expander(f"Pipeline #{failure['pipeline_id']} - {failure['project_name']}", expanded=True):
                    st.write(f"**Branch:** `{failure['branch']}`")
                    st.write(f"**Commit:** `{failure['commit_sha'][:8]}`")
                    st.write(f"**Author:** {failure['author']}")
                    st.write(f"**Time:** {failure['timestamp']}")
                    
                    col_actions = st.columns(4)
                    
                    with col_actions[0]:
                        if st.button("🔍 Analyze", key=f"analyze_gitlab_{failure['pipeline_id']}"):
                            with st.spinner(f"Analyzing with {os.environ.get('LLM_PROVIDER', 'gemini').upper()}..."):
                                # Check cache first
                                if cache:
                                    cached_analysis = cache.get_cached_analysis(failure)
                                    if cached_analysis:
                                        st.info("Using cached analysis")
                                        analysis = cached_analysis
                                    else:
                                        analysis = asyncio.run(llm_client.analyze_pipeline_failure(failure))
                                        cache.save_analysis(failure, analysis)
                                else:
                                    analysis = asyncio.run(llm_client.analyze_pipeline_failure(failure))
                                
                                st.session_state.active_analysis = analysis
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": format_pipeline_analysis(analysis),
                                    "type": "analysis",
                                    "data": analysis,
                                    "timestamp": datetime.now().isoformat()
                                })
                                st.rerun()
                    
                    with col_actions[1]:
                        if st.button("🛠️ Auto-Fix", key=f"fix_gitlab_{failure['pipeline_id']}"):
                            if st.session_state.active_analysis and st.session_state.active_analysis.get("confidence", 0) >= 80:
                                # Create MR with fixes
                                st.info("Creating merge request with fixes...")
                            else:
                                st.warning("Please analyze first or confidence too low")
                    
                    with col_actions[2]:
                        snooze_hours = st.number_input(
                            "Hours",
                            min_value=1,
                            max_value=168,
                            value=8,
                            key=f"snooze_hours_{failure['pipeline_id']}"
                        )
                    
                    with col_actions[3]:
                        if st.button("😴 Snooze", key=f"snooze_gitlab_{failure['pipeline_id']}"):
                            snooze_manager.snooze(failure["project_id"], failure["branch"], snooze_hours)
                            st.success(f"Snoozed for {snooze_hours} hours")
                            st.rerun()
    
    with col2:
        st.subheader("⚠️ SonarQube Quality Issues")

        # Add auto-refresh toggle
        auto_refresh = st.checkbox("🔄 Auto-refresh (every 30s)", key="sonar_auto_refresh")

        # Add refresh button
        if st.button("🔄 Refresh Now", key="refresh_sonar"):
            st.rerun()

        sonar_issues = webhook_receiver.get_recent_failures("sonarqube", limit=10)

        # Filter based on search
        if search_query:
            sonar_issues = [i for i in sonar_issues if 
                            search_query.lower() in i.get('project_key', '').lower() or
                            search_query.lower() in i.get('project_name', '').lower()]

        for issue in sonar_issues:
            if not snooze_manager.is_snoozed(issue["project_key"], "main"):
                with st.expander(f"Project: {issue['project_name']} ({issue['project_key']})", expanded=True):
                    st.write(f"**Quality Gate:** {issue['quality_gate_status']}")
                    st.write(f"**Issues:** {issue['total_issues']}")
                    st.write(f"**Last Analysis:** {issue['timestamp']}")

                    col_actions = st.columns(3)

                    with col_actions[0]:
                        if st.button("🔍 Analyze", key=f"analyze_sonar_{issue['project_key']}"):
                            with st.spinner("Analyzing quality issues..."):
                                analysis = asyncio.run(llm_client.analyze_sonarqube_issues(issue['project_key']))
                                st.session_state.active_sonar_analysis = analysis
                                st.rerun()

                    with col_actions[1]:
                        if st.button("🛠️ Generate Fixes", key=f"fix_sonar_{issue['project_key']}"):
                            if hasattr(st.session_state, 'active_sonar_analysis'):
                                st.info("Generating fix recommendations...")
                                # Store fixes in session state
                                st.session_state.sonar_fixes = st.session_state.active_sonar_analysis.get('fixes', [])
                            else:
                                st.warning("Please analyze first")

                    with col_actions[2]:
                        if st.button("📝 Create MR", key=f"mr_sonar_{issue['project_key']}"):
                            if hasattr(st.session_state, 'sonar_fixes') and st.session_state.sonar_fixes:
                                # Show MR creation dialog
                                st.session_state.show_mr_dialog = issue['project_key']
                                st.rerun()
                            else:
                                st.warning("Generate fixes first")

                    # Show analysis results if available
                    if hasattr(st.session_state, 'active_sonar_analysis') and st.session_state.active_sonar_analysis.get('project_key') == issue['project_key']:
                        st.markdown("### 📊 Analysis Results")
                        analysis = st.session_state.active_sonar_analysis
                        st.write(f"**Summary:** {analysis.get('summary', 'N/A')}")
                        st.write(f"**Confidence:** {analysis.get('overall_confidence', 0)}%")

                        if analysis.get('fixes'):
                            st.markdown("#### Recommended Fixes:")
                            for idx, fix in enumerate(analysis['fixes'][:3]):  # Show top 3 fixes
                                st.markdown(f"**{idx+1}. {fix.get('problem', 'Issue')}**")
                                st.code(fix.get('fix', {}).get('code', ''), language=fix.get('language', 'python'))

with tab2:
    # Chat interface
    st.subheader("💬 AI Assistant Chat")
    
    # Display chat messages
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("type") == "analysis":
                # Display formatted analysis
                st.markdown(message["content"])
                
                # Show confidence score with color
                confidence = message["data"].get("confidence", 0)
                confidence_class = "high" if confidence >= 80 else "medium" if confidence >= 60 else "low"
                st.markdown(f"<p class='confidence-{confidence_class}'>Confidence: {confidence}%</p>", unsafe_allow_html=True)
                
                # Show which LLM was used
                if message["data"].get("llm_provider"):
                    st.caption(f"Analysis by: {message['data']['llm_provider'].upper()}")
                
            else:
                st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("Ask about failures, request analysis, or get help..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                # Process user request
                response = asyncio.run(process_user_request(prompt, llm_client))
                st.markdown(response)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": datetime.now().isoformat()
                })

with tab3:
    # Analytics Dashboard
    st.subheader("📊 Analytics Dashboard")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_failures = len(st.session_state.failures.get("gitlab", []))
        st.metric("Total Pipeline Failures", total_failures)
    
    with col2:
        analyzed = sum(1 for msg in st.session_state.messages if msg.get("type") == "analysis")
        st.metric("Analyses Performed", analyzed)
    
    with col3:
        if analyzed > 0:
            avg_confidence = sum(msg["data"].get("confidence", 0) for msg in st.session_state.messages if msg.get("type") == "analysis") / analyzed
            st.metric("Average Confidence", f"{avg_confidence:.1f}%")
        else:
            st.metric("Average Confidence", "N/A")
    
    with col4:
        st.metric("Active Snoozes", snooze_manager.get_active_count())
    
    # Add charts here using plotly or matplotlib

with tab4:
    st.subheader("📚 Analysis History")
    
    # Group messages by pipeline ID
    pipeline_analyses = {}
    
    for message in st.session_state.messages:
        if message.get("type") == "analysis" and message.get("data"):
            pipeline_id = message["data"].get("pipeline_id", "Unknown")
            if pipeline_id not in pipeline_analyses:
                pipeline_analyses[pipeline_id] = []
            pipeline_analyses[pipeline_id].append(message)
    
    if pipeline_analyses:
        # Search in history
        history_search = st.text_input("Search history by Pipeline ID", key="history_search")
        
        for pipeline_id, analyses in sorted(pipeline_analyses.items(), reverse=True):
            if history_search and history_search.lower() not in str(pipeline_id).lower():
                continue
                
            with st.expander(f"Pipeline #{pipeline_id} ({len(analyses)} analyses)"):
                for analysis in analyses:
                    st.markdown(f"**Time:** {analysis.get('timestamp', 'Unknown')}")
                    st.markdown(f"**Confidence:** {analysis['data'].get('confidence', 0)}%")
                    st.markdown(f"**Root Cause:** {analysis['data'].get('root_cause', 'Unknown')}")
                    
                    if st.button(f"View Details", key=f"view_{pipeline_id}_{analysis.get('timestamp')}"):
                        st.json(analysis['data'])
    else:
        st.info("No analysis history yet.")

# Helper functions
def format_pipeline_analysis(analysis):
    """Format pipeline analysis for display"""
    lines = [
        f"### 🔍 Pipeline Failure Analysis",
        f"",
        f"**Root Cause:** {analysis.get('root_cause', 'Unknown')}",
        f"",
        f"**Context Level Used:** {analysis.get('final_context_level', 'Unknown')}",
        f"",
        f"### 📁 Affected Files:",
    ]
    
    for file in analysis.get('affected_files', []):
        lines.append(f"- `{file}`")
    
    lines.extend([
        f"",
        f"### 🛠️ Suggested Fixes:",
    ])
    
    for i, fix in enumerate(analysis.get('fixes', []), 1):
        lines.extend([
            f"",
            f"**Fix {i}: {fix.get('description', '')}**",
            f"File: `{fix.get('file_path', '')}`",
            f"```{fix.get('language', '')}",
            fix.get('code_snippet', ''),
            f"```"
        ])
    
    return "\n".join(lines)

def format_sonar_analysis(analysis):
    """Format SonarQube analysis for display"""
    lines = [
        f"### 📊 Code Quality Analysis",
        f"",
        f"**Summary:** {analysis.get('summary', 'No summary available')}",
        f"**Quality Gate:** {analysis.get('quality_gate_status', 'Unknown')}",
        f"**Total Issues Analyzed:** {analysis.get('analyzed_issues', 0)}",
        f"",
        f"### 🔧 Recommended Fixes:",
    ]
    
    for fix in analysis.get('fixes', []):
        lines.extend([
            f"",
            f"**Issue:** {fix.get('problem', '')}",
            f"File: `{fix.get('file_path', '')}` (Line {fix.get('line', 'N/A')})",
            f"```{fix.get('language', '')}",
            fix.get('fix', {}).get('code', ''),
            f"```",
            f"*Explanation:* {fix.get('fix', {}).get('explanation', '')}",
            f"*Confidence:* {fix.get('confidence', 0)}%"
        ])
    
    return "\n".join(lines)

async def process_user_request(prompt, llm_client):
    """Process natural language requests from users"""
    # This is a simplified version - you can expand this
    if "analyze" in prompt.lower() and "pipeline" in prompt.lower():
        return "Please select a pipeline failure from the Active Issues tab to analyze."
    elif "help" in prompt.lower():
        return """I can help you with:
- Analyzing pipeline failures
- Suggesting code fixes
- Reviewing SonarQube issues
- Creating merge requests with fixes
- Managing alert snoozes

Just click on any failure in the Active Issues tab to get started!"""
    else:
        return "I'm here to help with your DevOps issues. Please check the Active Issues tab for current failures."

if __name__ == "__main__":
    # This allows the app to handle incoming webhooks
    webhook_receiver.start_background_listener()
    if auto_refresh:
        import time
        time.sleep(30)
        st.rerun()