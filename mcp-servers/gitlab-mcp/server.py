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
mcp.description = "GitLab MCP server for progressive context retrieval"

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
except Exception as e:
    logger.warning(f"GitLab client initialization failed: {e}")

@mcp.resource("gitlab://projects")
async def list_projects() -> str:
    """List all accessible GitLab projects"""
    if not gl:
        return json.dumps({"error": "GitLab client not initialized"})
    
    try:
        projects = gl.projects.list(all=True)
        project_list = [{"id": p.id, "name": p.name, "path": p.path_with_namespace} for p in projects]
        return json.dumps(project_list)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
async def get_progressive_context(
    project_id: int,
    pipeline_id: int,
    commit_sha: str,
    context_level: str = "diff",
    previous_sha: Optional[str] = None,
    file_paths: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get progressive context for pipeline failure analysis.
    
    Levels:
    - diff: Just the commit diff
    - file: Full content of changed files
    - related: Related files (imports, dependencies)
    - project: Full project structure
    - variables: Include CI/CD variables
    """
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
        project = gl.projects.get(project_id)
        context = {
            "project_id": project_id,
            "pipeline_id": pipeline_id,
            "commit_sha": commit_sha,
            "context_level": context_level,
            "data": {}
        }
        
        # Level 1: Diff only
        if context_level in ["diff", "file", "related", "project", "variables"]:
            if not previous_sha:
                # Find previous successful pipeline on same branch
                pipelines = project.pipelines.list(
                    ref=project.commits.get(commit_sha).refs[0],
                    status="success",
                    order_by="id",
                    sort="desc"
                )
                if pipelines:
                    previous_sha = pipelines[0].sha
                else:
                    # Fallback to parent commit
                    commit = project.commits.get(commit_sha)
                    previous_sha = commit.parent_ids[0] if commit.parent_ids else None
            
            if previous_sha:
                diff = project.commits.diff(previous_sha, commit_sha)
                context["data"]["diff"] = diff
        
        # Level 2: Full file content
        if context_level in ["file", "related", "project", "variables"]:
            files_content = []
            for file_diff in context["data"].get("diff", []):
                try:
                    file_path = file_diff["new_path"]
                    file_content = project.files.get(file_path, ref=commit_sha)
                    files_content.append({
                        "path": file_path,
                        "content": base64.b64decode(file_content.content).decode('utf-8'),
                        "diff": file_diff
                    })
                except Exception as e:
                    logger.error(f"Error getting file {file_path}: {e}")
            context["data"]["files"] = files_content
        
        # Level 3: Related files (imports, configs)
        if context_level in ["related", "project", "variables"]:
            # Analyze imports and dependencies
            related_files = set()
            for file_data in context["data"].get("files", []):
                content = file_data.get("content", "")
                
                # Python imports
                if file_data["path"].endswith(".py"):
                    import re
                    imports = re.findall(r'(?:from|import)\s+([^\s]+)', content)
                    for imp in imports:
                        potential_file = imp.replace(".", "/") + ".py"
                        related_files.add(potential_file)
                
                # Java imports
                elif file_data["path"].endswith(".java"):
                    import re
                    imports = re.findall(r'import\s+([^;]+);', content)
                    for imp in imports:
                        potential_file = imp.replace(".", "/") + ".java"
                        related_files.add(potential_file)
            
            # Get related files content
            related_content = []
            for rel_file in related_files:
                try:
                    file_content = project.files.get(rel_file, ref=commit_sha)
                    related_content.append({
                        "path": rel_file,
                        "content": base64.b64decode(file_content.content).decode('utf-8')
                    })
                except:
                    pass
            context["data"]["related_files"] = related_content
        
        # Level 4: Project structure
        if context_level in ["project", "variables"]:
            tree = project.repository_tree(all=True, recursive=True, ref=commit_sha)
            context["data"]["project_structure"] = tree
        
        # Level 5: CI/CD variables
        if context_level == "variables":
            variables = []
            
            # Project variables
            project_vars = project.variables.list(all=True)
            for var in project_vars:
                variables.append({
                    "key": var.key,
                    "value": var.value if not var.masked else "***MASKED***",
                    "protected": var.protected,
                    "masked": var.masked,
                    "scope": "project"
                })
            
            # Group variables if available
            if hasattr(project, 'namespace'):
                try:
                    group = gl.groups.get(project.namespace['id'])
                    group_vars = group.variables.list(all=True)
                    for var in group_vars:
                        variables.append({
                            "key": var.key,
                            "value": var.value if not var.masked else "***MASKED***",
                            "protected": var.protected,
                            "masked": var.masked,
                            "scope": "group"
                        })
                except:
                    pass
            
            context["data"]["variables"] = variables
        
        return context
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_pipeline_failure_details(project_id: int, pipeline_id: int) -> Dict[str, Any]:
    """Get detailed pipeline failure information including logs"""
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
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
                    "name": pipeline.user["name"],
                    "username": pipeline.user["username"],
                    "email": pipeline.user.get("email", "")
                } if pipeline.user else None,
                "source": pipeline.source,
                "web_url": pipeline.web_url
            },
            "failed_jobs": []
        }
        
        for job in failed_jobs:
            job_details = project.jobs.get(job.id)
            trace = ""
            try:
                trace = job_details.trace().decode('utf-8')
            except:
                trace = "Log not available"
            
            details["failed_jobs"].append({
                "id": job.id,
                "name": job.name,
                "stage": job.stage,
                "status": job.status,
                "failure_reason": getattr(job, "failure_reason", None),
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "duration": job.duration,
                "log": trace,
                "web_url": job.web_url,
                "artifacts": [{"name": a["filename"], "size": a["size"]} for a in getattr(job, "artifacts", [])]
            })
        
        # Get commit message
        commit = project.commits.get(pipeline.sha)
        details["commit"] = {
            "sha": commit.id,
            "message": commit.message,
            "author": commit.author_name,
            "author_email": commit.author_email,
            "created_at": commit.created_at
        }
        
        return details
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def create_merge_request_with_fix(
    project_id: int,
    source_branch: str,
    title: str,
    changes: List[Dict[str, str]],
    target_branch: str = "main",
    description: str = "",
    assign_to_author: bool = True
) -> Dict[str, Any]:
    """Create a merge request with proposed fixes"""
    if not gl:
        return {"error": "GitLab client not initialized"}
    
    try:
        project = gl.projects.get(project_id)
        
        # Create branch if it doesn't exist
        try:
            project.branches.create({
                'branch': source_branch,
                'ref': target_branch
            })
        except gitlab.exceptions.GitlabCreateError as e:
            if "already exists" not in str(e):
                raise
        
        # Apply changes
        actions = []
        for change in changes:
            actions.append({
                'action': 'update' if change.get("action") != "create" else "create",
                'file_path': change["file_path"],
                'content': change["content"]
            })
        
        # Create commit
        commit = project.commits.create({
            'branch': source_branch,
            'commit_message': f"Fix: {title}",
            'actions': actions
        })
        
        # Create merge request
        mr_data = {
            'source_branch': source_branch,
            'target_branch': target_branch,
            'title': title,
            'description': description,
            'remove_source_branch': True
        }
        
        # Assign to original author if requested
        if assign_to_author:
            # Get the last pipeline to find the author
            pipelines = project.pipelines.list(per_page=1)
            if pipelines and pipelines[0].user:
                try:
                    user = gl.users.list(username=pipelines[0].user["username"])[0]
                    mr_data['assignee_id'] = user.id
                except:
                    pass
        
        mr = project.mergerequests.create(mr_data)
        
        return {
            "merge_request_id": mr.id,
            "merge_request_iid": mr.iid,
            "merge_request_url": mr.web_url,
            "commit_sha": commit.id,
            "source_branch": source_branch,
            "target_branch": target_branch
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_recent_pipelines(project_id: int, ref: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent pipelines for a project"""
    if not gl:
        return [{"error": "GitLab client not initialized"}]
    
    try:
        project = gl.projects.get(project_id)
        params = {"per_page": limit}
        if ref:
            params["ref"] = ref
        
        pipelines = project.pipelines.list(**params)
        
        pipeline_list = []
        for pipeline in pipelines:
            pipeline_list.append({
                "id": pipeline.id,
                "status": pipeline.status,
                "ref": pipeline.ref,
                "sha": pipeline.sha,
                "created_at": pipeline.created_at,
                "finished_at": pipeline.finished_at,
                "duration": pipeline.duration,
                "web_url": pipeline.web_url,
                "user": pipeline.user["name"] if pipeline.user else "System"
            })
        
        return pipeline_list
    except Exception as e:
        return [{"error": str(e)}]

# Health check
@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """Check if GitLab connection is healthy"""
    if gl:
        try:
            gl.auth()
            return {
                "status": "healthy",
                "gitlab_url": GITLAB_URL,
                "version": gl.version()[0],
                "user": gl.user.username
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    return {"status": "unhealthy", "error": "GitLab client not initialized"}

if __name__ == "__main__":
    import sys
    
    # Check if we should run in HTTP mode
    if os.environ.get("MCP_MODE") == "http":
        port = int(os.environ.get("PORT", 8000))
        mcp.run(
            transport="http",
            host="0.0.0.0",
            port=port,
            log_level="info"
        )
    else:
        # Run in STDIO mode (default)
        mcp.run()