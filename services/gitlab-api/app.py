# services/gitlab-api/app.py - FIXED VERSION with proper MR creation
from fastapi import FastAPI, HTTPException
import gitlab
import os
import json
import base64
from typing import Dict, List, Any, Optional

app = FastAPI(title="GitLab API Service", version="1.0.0")

# GitLab configuration
GITLAB_URL = os.environ.get("GITLAB_URL", "http://gitlab:80")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")

# Initialize GitLab client
gl = None
try:
    if GITLAB_TOKEN:
        gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
        gl.auth()
        print(f"✅ GitLab client initialized successfully")
except Exception as e:
    print(f"❌ GitLab client initialization failed: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if gl:
        try:
            gl.auth()
            return {
                "status": "healthy",
                "gitlab_url": GITLAB_URL,
                "version": gl.version()[0] if hasattr(gl, 'version') else "unknown",
                "user": gl.user.username if hasattr(gl, 'user') else "unknown"
            }
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    return {"status": "unhealthy", "error": "GitLab client not initialized - check GITLAB_TOKEN"}

@app.get("/projects")
async def list_projects():
    """List all accessible GitLab projects"""
    if not gl:
        raise HTTPException(status_code=500, detail="GitLab client not initialized")
    
    try:
        projects = gl.projects.list(all=True)
        return [{"id": p.id, "name": p.name, "path": p.path_with_namespace} for p in projects]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects/{project_id}/context")
async def get_progressive_context(
    project_id: int,
    pipeline_id: int,
    commit_sha: str,
    context_level: str = "diff",
    previous_sha: Optional[str] = None
):
    """Get progressive context for pipeline failure analysis - PURE DATA, NO ANALYSIS"""
    if not gl:
        raise HTTPException(status_code=500, detail="GitLab client not initialized")
    
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
                try:
                    # Find previous successful pipeline on same branch
                    commit = project.commits.get(commit_sha)
                    if commit.refs:
                        pipelines = project.pipelines.list(
                            ref=commit.refs[0],
                            status="success",
                            order_by="id",
                            sort="desc"
                        )
                        if pipelines:
                            previous_sha = pipelines[0].sha
                        else:
                            # Fallback to parent commit
                            previous_sha = commit.parent_ids[0] if commit.parent_ids else None
                    else:
                        # Fallback to parent commit
                        previous_sha = commit.parent_ids[0] if commit.parent_ids else None
                except Exception as e:
                    print(f"Warning: Could not find previous commit: {e}")
                    # Use a simple fallback
                    commit = project.commits.get(commit_sha)
                    previous_sha = commit.parent_ids[0] if commit.parent_ids else None
            
            if previous_sha:
                try:
                    diff = project.commits.diff(previous_sha, commit_sha)
                    context["data"]["diff"] = diff
                except Exception as e:
                    print(f"Warning: Could not get diff: {e}")
                    context["data"]["diff"] = []
        
        # Level 2: Full file content
        if context_level in ["file", "related", "project", "variables"]:
            files_content = []
            for file_diff in context["data"].get("diff", []):
                try:
                    file_path = file_diff.get("new_path") or file_diff.get("old_path")
                    if file_path:
                        file_content = project.files.get(file_path, ref=commit_sha)
                        files_content.append({
                            "path": file_path,
                            "content": base64.b64decode(file_content.content).decode('utf-8'),
                            "diff": file_diff
                        })
                except Exception as e:
                    print(f"Warning: Error getting file {file_path}: {e}")
            context["data"]["files"] = files_content
        
        return context
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_id}/pipeline/{pipeline_id}/failure-details")
async def get_pipeline_failure_details(project_id: int, pipeline_id: int):
    """Get detailed pipeline failure information including logs - PURE DATA"""
    if not gl:
        raise HTTPException(status_code=500, detail="GitLab client not initialized")
    
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
            try:
                job_details = project.jobs.get(job.id)
                trace = ""
                try:
                    trace_data = job_details.trace()
                    if isinstance(trace_data, bytes):
                        trace = trace_data.decode('utf-8')
                    else:
                        trace = str(trace_data)
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
                    "artifacts": [{"name": a.get("filename", ""), "size": a.get("size", 0)} for a in getattr(job, "artifacts", [])]
                })
            except Exception as e:
                print(f"Warning: Error getting job details for {job.id}: {e}")
        
        # Get commit message
        try:
            commit = project.commits.get(pipeline.sha)
            details["commit"] = {
                "sha": commit.id,
                "message": commit.message,
                "author": commit.author_name,
                "author_email": commit.author_email,
                "created_at": commit.created_at
            }
        except Exception as e:
            print(f"Warning: Could not get commit details: {e}")
            details["commit"] = {
                "sha": pipeline.sha,
                "message": "Could not retrieve commit message",
                "author": "Unknown",
                "author_email": "",
                "created_at": ""
            }
        
        return details
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects/{project_id}/merge-request")
async def create_merge_request_with_fix(project_id: int, request_data: Dict[str, Any]):
    """Create a merge request with proposed fixes - CORRECTED VERSION"""
    if not gl:
        raise HTTPException(status_code=500, detail="GitLab client not initialized")
    
    try:
        # Extract data from request body
        source_branch = request_data.get("source_branch")
        title = request_data.get("title")
        changes = request_data.get("changes", [])
        target_branch = request_data.get("target_branch", "main")
        description = request_data.get("description", "")
        assign_to_author = request_data.get("assign_to_author", True)
        
        # Validate required fields
        if not source_branch:
            raise HTTPException(status_code=400, detail="source_branch is required")
        if not title:
            raise HTTPException(status_code=400, detail="title is required")
        
        print(f"🔀 Creating merge request for project {project_id}")
        print(f"   Source branch: {source_branch}")
        print(f"   Target branch: {target_branch}")
        print(f"   Title: {title}")
        print(f"   Changes: {len(changes)} files")
        
        project = gl.projects.get(project_id)
        
        # Step 1: Create branch if it doesn't exist
        try:
            project.branches.create({
                'branch': source_branch,
                'ref': target_branch
            })
            print(f"✅ Created branch {source_branch}")
        except gitlab.exceptions.GitlabCreateError as e:
            if "already exists" not in str(e):
                print(f"❌ Error creating branch: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to create branch: {str(e)}")
            print(f"ℹ️ Branch {source_branch} already exists")
        
        # Step 2: Apply changes to the branch
        if changes:
            try:
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
                print(f"✅ Created commit {commit.id}")
                
            except Exception as e:
                print(f"❌ Error creating commit: {e}")
                raise HTTPException(status_code=400, detail=f"Failed to create commit: {str(e)}")
        
        # Step 3: Create merge request with correct API format
        try:
            # GitLab API requires these specific fields
            mr_data = {
                'source_branch': source_branch,
                'target_branch': target_branch,
                'title': title,
                'description': description,
                'remove_source_branch': True
            }
            
            # Optional: assign to author if requested
            if assign_to_author:
                try:
                    # Get the author of the latest commit on source branch
                    commits = project.commits.list(ref_name=source_branch, per_page=1)
                    if commits:
                        author_email = commits[0].author_email
                        # Find user by email
                        users = gl.users.list(search=author_email)
                        if users:
                            mr_data['assignee_id'] = users[0].id
                            print(f"ℹ️ Assigned MR to {users[0].username}")
                except Exception as e:
                    print(f"⚠️ Could not assign to author: {e}")
            
            print(f"📝 Creating MR with data: {mr_data}")
            
            # Create the merge request using python-gitlab
            mr = project.mergerequests.create(mr_data)
            print(f"✅ Created merge request {mr.iid}")
            
            return {
                "merge_request_id": mr.id,
                "merge_request_iid": mr.iid,
                "merge_request_url": mr.web_url,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "title": title,
                "description": description,
                "success": True
            }
            
        except gitlab.exceptions.GitlabCreateError as e:
            print(f"❌ GitLab API error creating MR: {e}")
            error_message = str(e)
            
            # Parse common GitLab errors
            if "422" in error_message:
                if "already exists" in error_message.lower():
                    raise HTTPException(status_code=409, detail="Merge request already exists for this branch")
                elif "source branch" in error_message.lower():
                    raise HTTPException(status_code=400, detail="Source branch is invalid or does not exist")
                elif "target branch" in error_message.lower():
                    raise HTTPException(status_code=400, detail="Target branch is invalid or does not exist")
                else:
                    raise HTTPException(status_code=422, detail=f"GitLab validation error: {error_message}")
            else:
                raise HTTPException(status_code=500, detail=f"GitLab API error: {error_message}")
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        print(f"❌ Unexpected error creating merge request: {e}")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Starting GitLab API service on port 8081")
    print(f"📡 GitLab URL: {GITLAB_URL}")
    print(f"🔑 Token configured: {'Yes' if GITLAB_TOKEN else 'No'}")
    uvicorn.run(app, host="0.0.0.0", port=8081)