"""Pipeline failures page"""
import streamlit as st
import asyncio
import json
import time
from datetime import datetime, timedelta
from utils.api_client import APIClient
from utils.logger import setup_logger

log = setup_logger()

# Page config
st.set_page_config(
    page_title="Pipeline Failures - CI/CD Assistant",
    page_icon="🚀",
    layout="wide"
)

# Initialize session state
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()
if "selected_project" not in st.session_state:
    st.session_state.selected_project = None
if "selected_failure" not in st.session_state:
    st.session_state.selected_failure = None
if "failure_groups" not in st.session_state:
    st.session_state.failure_groups = {}
if "show_chat" not in st.session_state:
    st.session_state.show_chat = {}

def calculate_time_remaining(expires_at):
    """Calculate time remaining until session expires"""
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
    
    now = datetime.utcnow()
    if expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=None)
    
    remaining = expires_at - now
    
    if remaining.total_seconds() <= 0:
        return "Expired"
    
    hours = int(remaining.total_seconds() // 3600)
    minutes = int((remaining.total_seconds() % 3600) // 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    else:
        return f"{minutes}m"

# Header
st.title("🚀 Pipeline Failures")

# Top navigation bar
col_nav1, col_nav2, col_nav3 = st.columns([2, 2, 1])
with col_nav1:
    date_range = st.date_input(
        "Date Range",
        value=(datetime.now() - timedelta(days=7), datetime.now()),
        key="date_range"
    )
with col_nav2:
    status_filter = st.multiselect(
        "Status Filter",
        ["Failed", "Analyzing", "Fixed"],
        default=["Failed", "Analyzing"],
        key="status_filter"
    )
with col_nav3:
    if st.button("🔄 Refresh", key="refresh_main"):
        st.rerun()

# Main layout - adjusted column widths
col1, col2, col3 = st.columns([1.5, 3, 1.5])

# Column 1: Project Navigator
with col1:
    st.subheader("Projects")
    
    # Fetch sessions and group by project
    async def fetch_and_group_sessions():
        sessions = await st.session_state.api_client.get_active_sessions()
        pipeline_sessions = [s for s in sessions if s.get("session_type") == "pipeline"]
        
        # Group by project and branch
        groups = {}
        for session in pipeline_sessions:
            project = session.get("project_name", "Unknown")
            branch = session.get("branch", "main")
            
            if project not in groups:
                groups[project] = {}
            if branch not in groups[project]:
                groups[project][branch] = []
            
            groups[project][branch].append(session)
        
        return groups
    
    try:
        st.session_state.failure_groups = asyncio.run(fetch_and_group_sessions())
        
        # Project selector
        projects = list(st.session_state.failure_groups.keys())
        if projects:
            selected_project = st.selectbox(
                "Select Project",
                projects,
                index=0 if st.session_state.selected_project is None else 
                      projects.index(st.session_state.selected_project) if st.session_state.selected_project in projects else 0,
                key="project_selector"
            )
            st.session_state.selected_project = selected_project
            
            # Branch expandables
            project_branches = st.session_state.failure_groups.get(selected_project, {})
            for branch, sessions in project_branches.items():
                # Count failures by status
                active_count = sum(1 for s in sessions if s.get("status") == "active")
                icon = "🔴" if active_count > 0 else "🟢"
                
                with st.expander(f"{icon} {branch} ({len(sessions)} issues)", expanded=active_count > 0):
                    for session in sessions:
                        # Get job name or use fallback
                        job_name = session.get('job_name') or session.get('failed_stage') or 'Unknown Job'
                        time_remaining = calculate_time_remaining(session.get('expires_at'))
                        
                        # Get fix attempts count
                        fix_attempts = session.get("webhook_data", {}).get("fix_attempts", [])
                        
                        # Color code based on fix status
                        if fix_attempts:
                            if any(att.get("status") == "success" for att in fix_attempts):
                                status_color = "🟢"
                            elif any(att.get("status") == "pending" for att in fix_attempts):
                                status_color = "🟡"
                            else:
                                status_color = "🔴"
                        else:
                            # Color code based on time remaining
                            if time_remaining == "Expired":
                                status_color = "🔴"
                            elif "m" in time_remaining and not "h" in time_remaining:
                                status_color = "🟡"
                            else:
                                status_color = "🟢"
                        
                        button_label = f"{status_color} {job_name}\n⏰ {time_remaining}"
                        if fix_attempts:
                            button_label += f"\n🔄 {len(fix_attempts)} fix(es)"
                        
                        if st.button(
                            button_label,
                            key=f"job_{session['id']}",
                            use_container_width=True
                        ):
                            st.session_state.selected_failure = session
                            st.rerun()
    
    except Exception as e:
        st.error(f"Failed to load projects: {e}")

# Column 2: Main Content Area (Analysis & Chat)
with col2:
    if st.session_state.selected_failure:
        session = st.session_state.selected_failure
        session_id = session["id"]
        
        st.subheader("Failure Details")
        
        # Load full session data
        try:
            full_session = asyncio.run(st.session_state.api_client.get_session(session_id))
            messages = full_session.get("conversation_history", [])
            fix_attempts = full_session.get("webhook_data", {}).get("fix_attempts", [])
            
            # Show expiration timer at top
            time_remaining = calculate_time_remaining(full_session.get('expires_at'))
            if time_remaining == "Expired":
                st.error(f"⏰ This session has expired and will be cleaned up")
            elif "m" in time_remaining and not "h" in time_remaining:
                st.warning(f"⏰ Session expires in: {time_remaining}")
            else:
                st.info(f"⏰ Session expires in: {time_remaining}")
            
            # Show fix iteration info if applicable
            if fix_attempts:
                col_iter1, col_iter2 = st.columns([3, 1])
                with col_iter1:
                    # Check if any attempts are pending
                    pending_attempts = [att for att in fix_attempts if att.get("status") == "pending"]
                    successful_attempts = [att for att in fix_attempts if att.get("status") == "success"]
                    
                    if successful_attempts:
                        st.success(f"✅ Fix Iterations: {len(fix_attempts)}/5 ({len(successful_attempts)} successful)")
                    elif pending_attempts:
                        st.warning(f"🔄 Fix Iterations: {len(fix_attempts)}/5 (Checking status...)")
                        # Auto-refresh every 5 seconds if there are pending fixes
                        time.sleep(5)
                        st.rerun()
                    else:
                        st.error(f"❌ Fix Iterations: {len(fix_attempts)}/5 (all failed)")
                
                with col_iter2:
                    with st.expander("Fix History"):
                        for i, attempt in enumerate(fix_attempts):
                            status_icon = "✅" if attempt.get("status") == "success" else "❌" if attempt.get("status") == "failed" else "⏳"
                            st.text(f"{status_icon} Attempt {i+1}: MR #{attempt['mr_id']}")
                            st.caption(f"Branch: {attempt['branch']}")
                            st.caption(f"Status: {attempt.get('status', 'pending')}")
            
            # Action buttons - Smart logic based on fix attempts
            col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
            
            mr_url = full_session.get("merge_request_url")
            
            with col_btn1:
                # Check if current branch is a fix branch created by our system
                current_branch = full_session.get("branch", "")
                is_fix_branch = current_branch.startswith("fix/pipeline_")
                
                # Check fix status
                all_successful = all(att.get("status") == "success" for att in fix_attempts) if fix_attempts else False
                
                if all_successful and mr_url:
                    st.success("✅ Fix Applied Successfully!")
                    st.link_button("📄 View MR", mr_url, use_container_width=True, type="primary")
                elif len(fix_attempts) >= 5:
                    st.error("❌ Max attempts reached")
                elif is_fix_branch and not mr_url:
                    # This is analyzing a failure on OUR fix branch - show Apply Fix
                    if st.button("🔧 Apply Fix", use_container_width=True):
                        with st.spinner("Applying fix to the existing branch..."):
                            response = asyncio.run(
                                st.session_state.api_client.send_message(
                                    session_id, 
                                    "Apply the fixes to the current feature branch. This is an iteration on our existing fix branch, so update the same branch with additional commits."
                                )
                            )
                            if response.get("merge_request_url"):
                                st.success(f"✅ Fix applied to existing MR")
                            st.rerun()
                elif len(fix_attempts) > 0 and not mr_url:
                    # Show retry button for subsequent attempts
                    if st.button("🔄 Try Another Fix", use_container_width=True):
                        with st.spinner("Analyzing latest logs and creating additional fixes..."):
                            response = asyncio.run(
                                st.session_state.api_client.send_message(
                                    session_id, 
                                    "The pipeline is still failing with the same error. Please analyze the latest logs and create another fix targeting any remaining issues."
                                )
                            )
                            if response.get("merge_request_url"):
                                st.success(f"✅ Additional fixes added to MR")
                            st.rerun()
                elif not mr_url:
                    # First attempt - create MR button
                    if st.button("🔀 Create MR", use_container_width=True):
                        with st.spinner("Creating merge request..."):
                            response = asyncio.run(
                                st.session_state.api_client.send_message(
                                    session_id, 
                                    "Create a merge request with all the fixes we discussed. Make sure to include the complete MR URL in your response."
                                )
                            )
                            if response.get("merge_request_url"):
                                st.success(f"✅ MR Created: {response['merge_request_url']}")
                            st.rerun()
                else:
                    st.link_button("📄 View MR", mr_url, use_container_width=True)
            
            with col_btn2:
                if st.button("💬 Ask Question", use_container_width=True):
                    st.session_state.show_chat[session_id] = not st.session_state.show_chat.get(session_id, False)
            
            st.divider()
            
            # Always show conversation history
            st.markdown("### 📋 Analysis & Discussion")
            
            # Create a container for messages with fixed height and scroll
            message_container = st.container(height=1400)
            
            with message_container:
                for msg in messages:
                    if msg["role"] != "system":
                        with st.chat_message(msg["role"]):
                            content = msg.get("content", "")

                            # Try to parse JSON string if it looks like JSON
                            if isinstance(content, str) and content.strip().startswith('{'):
                                try:
                                    parsed = json.loads(content)
                                    if isinstance(parsed, dict):
                                        if "text" in parsed:
                                            content = parsed["text"]
                                        elif "message" in parsed:
                                            content = parsed["message"]
                                        elif "content" in parsed:
                                            if isinstance(parsed["content"], list):
                                                content = parsed["content"][0].get("text", str(parsed))
                                            else:
                                                content = parsed["content"]
                                except json.JSONDecodeError:
                                    pass
                                    
                            st.markdown(content)
            
            # Chat input interface (only shown when chat button is clicked)
            if st.session_state.show_chat.get(session_id):
                st.divider()
                if prompt := st.chat_input("Ask about this failure..."):
                    # Add user message
                    with st.chat_message("user"):
                        st.write(prompt)
                    
                    # Get response
                    with st.chat_message("assistant"):
                        with st.spinner("Thinking..."):
                            response = asyncio.run(
                                st.session_state.api_client.send_message(session_id, prompt)
                            )
                            response_text = response.get("response", "")
                            st.write(response_text)
                            
                            if response.get("merge_request_url"):
                                st.success(f"✅ MR Created: {response['merge_request_url']}")
                    
                    st.rerun()
        
        except Exception as e:
            st.error(f"Failed to load session details: {e}")
    
    else:
        # Show job cards when no failure is selected
        st.subheader("Failure Details")
        
        if st.session_state.selected_project and st.session_state.failure_groups:
            project_data = st.session_state.failure_groups.get(st.session_state.selected_project, {})
            
            for branch, sessions in project_data.items():
                st.markdown(f"### 🌿 {branch}")
                
                # Group by job name
                job_groups = {}
                for session in sessions:
                    job_name = session.get("job_name", "Unknown")
                    if job_name not in job_groups:
                        job_groups[job_name] = []
                    job_groups[job_name].append(session)
                
                # Display job cards
                for job_name, job_sessions in job_groups.items():
                    latest_session = max(job_sessions, key=lambda x: x.get("created_at", ""))
                    status = latest_session.get("status", "active")
                    time_remaining = calculate_time_remaining(latest_session.get('expires_at'))
                    fix_attempts = latest_session.get("webhook_data", {}).get("fix_attempts", [])
                    
                    # Determine actual status based on fix attempts
                    if fix_attempts:
                        # Check if any fix is successful
                        successful_fixes = [att for att in fix_attempts if att.get("status") == "success"]
                        pending_fixes = [att for att in fix_attempts if att.get("status") == "pending"]
                        
                        if successful_fixes:
                            display_status = "fixed"
                            status_emoji = "🟢"
                            status_text = "Fixed"
                        elif pending_fixes:
                            display_status = "fixing"
                            status_emoji = "🟡"
                            status_text = "Fixing..."
                        else:
                            display_status = "failed"
                            status_emoji = "🔴"
                            status_text = f"Failed ({len(fix_attempts)} attempts)"
                    else:
                        display_status = status
                        status_emoji = "🔴" if status == "active" else "🟢" if status == "resolved" else "🟡"
                        status_text = "Failed" if status == "active" else "Fixed" if status == "resolved" else "Analyzing"
                    
                    # Create card with proper coloring
                    with st.container():
                        col_info, col_action = st.columns([4, 1])
                        
                        with col_info:
                            # Time color based on remaining time
                            if time_remaining == "Expired":
                                time_emoji = "🔴"
                            elif "m" in time_remaining and not "h" in time_remaining:
                                time_emoji = "🟡"
                            else:
                                time_emoji = "🟢"
                            
                            # Use colored text based on status
                            if display_status == "fixed":
                                st.markdown(f"""
                                **{status_emoji} {job_name}** - :green[{status_text}]
                                
                                Stage: {latest_session.get("failed_stage", "Unknown")} | 
                                {len(job_sessions)} occurrence(s) | 
                                Fixes: {len(fix_attempts)} |
                                Last: {datetime.fromisoformat(latest_session.get("created_at", datetime.now().isoformat())).strftime("%b %d, %H:%M")} |
                                {time_emoji} Expires: {time_remaining}
                                """)
                            elif display_status == "fixing":
                                st.markdown(f"""
                                **{status_emoji} {job_name}** - :orange[{status_text}]
                                
                                Stage: {latest_session.get("failed_stage", "Unknown")} | 
                                {len(job_sessions)} occurrence(s) | 
                                Fixes: {len(fix_attempts)} |
                                Last: {datetime.fromisoformat(latest_session.get("created_at", datetime.now().isoformat())).strftime("%b %d, %H:%M")} |
                                {time_emoji} Expires: {time_remaining}
                                """)
                            else:
                                st.markdown(f"""
                                **{status_emoji} {job_name}** - :red[{status_text}]
                                
                                Stage: {latest_session.get("failed_stage", "Unknown")} | 
                                {len(job_sessions)} occurrence(s) | 
                                Fixes: {len(fix_attempts)} |
                                Last: {datetime.fromisoformat(latest_session.get("created_at", datetime.now().isoformat())).strftime("%b %d, %H:%M")} |
                                {time_emoji} Expires: {time_remaining}
                                """)
                        
                        with col_action:
                            if st.button("View", key=f"view_{latest_session['id']}"):
                                st.session_state.selected_failure = latest_session
                                st.rerun()
                    
                    st.divider()
                    
            # Auto-refresh check for pending fixes
            has_pending = False
            for branch, sessions in project_data.items():
                for session in sessions:
                    fix_attempts = session.get("webhook_data", {}).get("fix_attempts", [])
                    if any(att.get("status") == "pending" for att in fix_attempts):
                        has_pending = True
                        break
                if has_pending:
                    break
            
            if has_pending:
                # Auto-refresh every 5 seconds
                time.sleep(5)
                st.rerun()
        else:
            st.info("Select a project from the left to view failures")

# Column 3: Metadata Panel
with col3:
    if st.session_state.selected_failure:
        session = st.session_state.selected_failure
        
        st.subheader("Analysis & Chat")
        
        # Session metadata
        st.markdown("**Pipeline Details:**")
        st.caption(f"Pipeline: #{session.get('pipeline_id', 'N/A')}")
        st.caption(f"Stage: {session.get('failed_stage', 'N/A')}")
        st.caption(f"Job: {session.get('job_name', 'N/A')}")
        
        # Fix attempts info
        fix_attempts = session.get("webhook_data", {}).get("fix_attempts", [])
        if fix_attempts:
            st.markdown("**Fix Information:**")
            st.caption(f"Iterations: {len(fix_attempts)}/5")
            
            successful = [att for att in fix_attempts if att.get("status") == "success"]
            if successful:
                st.success(f"✅ {len(successful)} successful fix(es)")
            
            st.caption(f"Current Branch: {fix_attempts[-1]['branch']}")
        
        # Session timing
        st.markdown("**Session Info:**")
        created_at = session.get('created_at')
        if created_at:
            created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            st.caption(f"Created: {created_time.strftime('%b %d, %H:%M')}")
        
        time_remaining = calculate_time_remaining(session.get('expires_at'))
        if time_remaining == "Expired":
            st.caption("⏰ Status: Expired")
        else:
            st.caption(f"⏰ Expires in: {time_remaining}")
        
        if url := session.get('pipeline_url'):
            st.link_button("View in GitLab", url, use_container_width=True)