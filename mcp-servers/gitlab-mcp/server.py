# mcp-servers/gitlab-mcp/server.py
import os
import json
import logging
import base64
from typing import Dict, List, Any, Optional
import gitlab
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("gitlab-mcp")

# GitLab configuration
GITLAB_URL = os.environ.get("GITLAB_URL", "http://gitlab:80")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")

# Initialize GitLab client
gl = None
try:
    if GITLAB_TOKEN:
        gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
        gl.auth()
        logger.info("GitLab client initialized successfully")
    else:
        logger.warning("GITLAB_TOKEN not provided")
except Exception as e:
    logger.warning(f"GitLab client initialization failed: {e}")

@mcp.tool()
def get_pipeline_failure_details(project_id: int, pipeline_id: int) -> Dict[str, Any]:
    """Get detailed pipeline failure information including logs"""
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
        logger.info(f"Getting pipeline details for project {project_id}, pipeline {pipeline_id}")
        
        project = gl.projects.get(project_id)
        pipeline = project.pipelines.get(pipeline_id)
        
        jobs = pipeline.jobs.list(all=True)
        failed_jobs = [job for job in jobs if job.status == "failed"]
        
        details = {
            "pipeline": {
                "id": pipeline.id,
                "status": pipeline.status,
                "ref": pipeline.ref,
                "sha": pipeline.sha,
                "created_at": pipeline.created_at,
                "finished_at": pipeline.finished_at,
                "duration": pipeline.duration,
                "user": {
                    "name": pipeline.user["name"] if pipeline.user else "System",
                    "username": pipeline.user["username"] if pipeline.user else "system",
                    "email": pipeline.user.get("email", "") if pipeline.user else ""
                },
                "source": pipeline.source,
                "web_url": pipeline.web_url
            },
            "failed_jobs": []
        }
        
        for job in failed_jobs:
            try:
                job_details = project.jobs.get(job.id)
                trace = ""
                try:
                    trace_bytes = job_details.trace()
                    if trace_bytes:
                        trace = trace_bytes.decode('utf-8') if isinstance(trace_bytes, bytes) else str(trace_bytes)
                        # Get last 50 lines for relevance
                        trace_lines = trace.split('\n')
                        if len(trace_lines) > 50:
                            trace = '\n'.join(trace_lines[-50:])
                except Exception as trace_error:
                    logger.warning(f"Could not get trace for job {job.id}: {trace_error}")
                    trace = "Log not available"
                
                details["failed_jobs"].append({
                    "id": job.id,
                    "name": job.name,
                    "stage": job.stage,
                    "status": job.status,
                    "failure_reason": getattr(job, "failure_reason", "Unknown"),
                    "started_at": job.started_at,
                    "finished_at": job.finished_at,
                    "duration": job.duration,
                    "log": trace,
                    "web_url": job.web_url
                })
            except Exception as job_error:
                logger.error(f"Error getting details for job {job.id}: {job_error}")
                details["failed_jobs"].append({
                    "id": job.id,
                    "name": job.name,
                    "stage": job.stage,
                    "status": job.status,
                    "error": str(job_error)
                })
        
        # Get commit details
        try:
            commit = project.commits.get(pipeline.sha)
            details["commit"] = {
                "sha": commit.id,
                "message": commit.message,
                "author": commit.author_name,
                "author_email": commit.author_email,
                "created_at": commit.created_at
            }
        except Exception as commit_error:
            logger.warning(f"Could not get commit details: {commit_error}")
            details["commit"] = {
                "sha": pipeline.sha,
                "message": "Could not retrieve commit message",
                "author": "Unknown",
                "author_email": "",
                "created_at": pipeline.created_at
            }
        
        logger.info(f"Successfully retrieved pipeline details for {project_id}/{pipeline_id}")
        return details
        
    except Exception as e:
        logger.error(f"Error getting pipeline failure details: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_progressive_context(
    project_id: int,
    pipeline_id: int,
    commit_sha: str,
    context_level: str = "diff",
    previous_sha: Optional[str] = None
) -> Dict[str, Any]:
    """Get progressive context for pipeline failure analysis"""
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
        logger.info(f"Getting {context_level} context for project {project_id}, commit {commit_sha}")
        
        project = gl.projects.get(project_id)
        context = {
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "commit_sha": commit_sha,
            "context_level": context_level,
            "data": {}
        }
        
        # Level 1: Diff only
        if context_level in ["diff", "file", "related", "project"]:
            if not previous_sha:
                # Find previous commit
                try:
                    commit = project.commits.get(commit_sha)
                    if commit.parent_ids:
                        previous_sha = commit.parent_ids[0]
                    else:
                        # Try to find previous successful pipeline
                        pipelines = project.pipelines.list(
                            ref=commit.refs[0] if hasattr(commit, 'refs') and commit.refs else 'main',
                            status="success",
                            order_by="id",
                            sort="desc",
                            per_page=5
                        )
                        if pipelines and len(pipelines) > 0:
                            prev_pipeline = pipelines[0]
                            previous_sha = prev_pipeline.sha
                except Exception as e:
                    logger.warning(f"Could not find previous commit: {e}")
            
            if previous_sha and previous_sha != commit_sha:
                try:
                    diff = project.repository_compare(previous_sha, commit_sha)
                    context["data"]["diff"] = diff.get("diffs", [])
                    logger.info(f"Found {len(context['data']['diff'])} changed files")
                except Exception as e:
                    logger.warning(f"Could not get diff: {e}")
                    context["data"]["diff"] = []
        
        # Level 2: Full file content
        if context_level in ["file", "related", "project"]:
            files_content = []
            for file_diff in context["data"].get("diff", [])[:5]:  # Limit to 5 files
                try:
                    file_path = file_diff.get("new_path") or file_diff.get("old_path")
                    if file_path and not file_diff.get("deleted_file", False):
                        file_content = project.files.get(file_path, ref=commit_sha)
                        content = base64.b64decode(file_content.content).decode('utf-8')
                        # Limit content size
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (content truncated)"
                        
                        files_content.append({
                            "path": file_path,
                            "content": content,
                            "diff": file_diff
                        })
                except Exception as e:
                    logger.warning(f"Error getting file {file_path}: {e}")
            
            context["data"]["files"] = files_content
        
        # Level 3: Project structure (limited)
        if context_level == "project":
            try:
                tree = project.repository_tree(recursive=False, ref=commit_sha)
                # Limit tree size
                context["data"]["project_structure"] = tree[:20]
            except Exception as e:
                logger.warning(f"Could not get project structure: {e}")
                context["data"]["project_structure"] = []
        
        logger.info(f"Successfully retrieved {context_level} context")
        return context
        
    except Exception as e:
        logger.error(f"Error getting progressive context: {e}")
        return {"error": str(e)}

@mcp.tool()
def create_merge_request_with_fix(
    project_id: int,
    source_branch: str,
    title: str,
    changes: List[Dict[str, str]],
    target_branch: str = "main",
    description: str = ""
) -> Dict[str, Any]:
    """Create a merge request with proposed fixes"""
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
        logger.info(f"Creating merge request for project {project_id}")
        
        project = gl.projects.get(project_id)
        
        # Create branch if it doesn't exist
        try:
            project.branches.create({
                'branch': source_branch,
                'ref': target_branch
            })
            logger.info(f"Created branch {source_branch}")
        except gitlab.exceptions.GitlabCreateError as e:
            if "already exists" not in str(e):
                logger.error(f"Error creating branch: {e}")
                raise
            logger.info(f"Branch {source_branch} already exists")
        
        # Apply changes
        actions = []
        for change in changes:
            action_type = change.get("action", "update")
            if action_type not in ["create", "update", "delete"]:
                action_type = "update"
            
            actions.append({
                'action': action_type,
                'file_path': change["file_path"],
                'content': change["content"]
            })
        
        # Create commit with changes
        commit_data = {
            'branch': source_branch,
            'commit_message': f"Fix: {title}",
            'actions': actions
        }
        
        commit = project.commits.create(commit_data)
        logger.info(f"Created commit {commit.id}")
        
        # Create merge request
        mr_data = {
            'source_branch': source_branch,
            'target_branch': target_branch,
            'title': title,
            'description': description,
            'remove_source_branch': True
        }
        
        mr = project.mergerequests.create(mr_data)
        logger.info(f"Created merge request {mr.iid}")
        
        return {
            "merge_request_id": mr.id,
            "merge_request_iid": mr.iid,
            "merge_request_url": mr.web_url,
            "commit_sha": commit.id,
            "source_branch": source_branch,
            "target_branch": target_branch
        }
        
    except Exception as e:
        logger.error(f"Error creating merge request: {e}")
        return {"error": str(e)}

@mcp.tool()
def health_check() -> Dict[str, Any]:
    """Check if GitLab connection is healthy"""
    try:
        if gl:
            gl.auth()
            version_info = gl.version()
            user_info = gl.user
            return {
                "status": "healthy",
                "gitlab_url": GITLAB_URL,
                "version": version_info[0] if version_info else "unknown",
                "user": user_info.username if user_info else "unknown",
                "authenticated": True
            }
        else:
            return {
                "status": "unhealthy", 
                "error": "GitLab client not initialized",
                "gitlab_url": GITLAB_URL,
                "authenticated": False
            }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "gitlab_url": GITLAB_URL,
            "authenticated": False
        }

if __name__ == "__main__":
    import uvicorn
    
    # Always run in HTTP mode for container deployment
    logger.info("Starting GitLab MCP server in HTTP mode")
    logger.info(f"GitLab URL: {GITLAB_URL}")
    logger.info(f"GitLab Token configured: {'Yes' if GITLAB_TOKEN else 'No'}")
    
    # Run FastMCP in HTTP mode
    uvicorn.run(
        mcp.create_app(),
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )