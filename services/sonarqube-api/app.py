# services/sonarqube-api/app.py
from fastapi import FastAPI, HTTPException
import requests
import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta

app = FastAPI(title="SonarQube API Service", version="1.0.0")

# SonarQube configuration
SONARQUBE_URL = os.environ.get("SONARQUBE_URL", "http://sonarqube:9000")
SONARQUBE_TOKEN = os.environ.get("SONARQUBE_TOKEN", "")

# Headers for API requests
headers = {
    "Authorization": f"Bearer {SONARQUBE_TOKEN}" if SONARQUBE_TOKEN else ""
}

@app.get("/health")
async def health_check():
    """Check if SonarQube connection is healthy"""
    try:
        response = requests.get(
            f"{SONARQUBE_URL}/api/system/status",
            headers=headers
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Get version
        version_response = requests.get(
            f"{SONARQUBE_URL}/api/server/version",
            headers=headers
        )
        version = version_response.text.strip()
        
        return {
            "status": "healthy",
            "sonarqube_url": SONARQUBE_URL,
            "version": version,
            "system_status": data["status"]
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.get("/projects")
async def list_projects():
    """List all SonarQube projects"""
    try:
        response = requests.get(
            f"{SONARQUBE_URL}/api/projects/search",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/issues")
async def get_project_issues(
    project_key: str,
    severity: Optional[List[str]] = None,
    types: Optional[List[str]] = None,
    resolved: bool = False,
    file_path: Optional[str] = None
):
    """Get issues for a project with filtering options - PURE DATA"""
    try:
        params = {
            "componentKeys": project_key,
            "resolved": str(resolved).lower(),
            "ps": 500  # Page size
        }
        
        if severity:
            params["severities"] = ",".join(severity)
        if types:
            params["types"] = ",".join(types)
        if file_path:
            params["componentKeys"] = f"{project_key}:{file_path}"
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Group issues by file
        issues_by_file = {}
        for issue in data.get("issues", []):
            file_path = issue.get("component", "").replace(f"{project_key}:", "")
            if file_path not in issues_by_file:
                issues_by_file[file_path] = []
            
            issues_by_file[file_path].append({
                "key": issue["key"],
                "rule": issue["rule"],
                "severity": issue["severity"],
                "type": issue["type"],
                "message": issue["message"],
                "line": issue.get("line"),
                "effort": issue.get("effort"),
                "debt": issue.get("debt"),
                "status": issue["status"],
                "author": issue.get("author"),
                "tags": issue.get("tags", []),
                "creation_date": issue["creationDate"],
                "update_date": issue.get("updateDate")
            })
        
        return {
            "project_key": project_key,
            "total": data["total"],
            "issues_by_file": issues_by_file,
            "facets": data.get("facets", [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/quality-gate")
async def get_quality_gate_status(project_key: str):
    """Get quality gate status for a project - PURE DATA"""
    try:
        response = requests.get(
            f"{SONARQUBE_URL}/api/qualitygates/project_status",
            headers=headers,
            params={"projectKey": project_key}
        )
        response.raise_for_status()
        
        data = response.json()
        status = data["projectStatus"]
        
        # Parse conditions
        conditions = []
        for condition in status.get("conditions", []):
            conditions.append({
                "metric": condition["metricKey"],
                "status": condition["status"],
                "actual_value": condition.get("actualValue"),
                "error_threshold": condition.get("errorThreshold"),
                "comparator": condition.get("comparator")
            })
        
        return {
            "project_key": project_key,
            "status": status["status"],
            "conditions": conditions,
            "period": status.get("period")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/measures")
async def get_project_measures(
    project_key: str,
    metrics: Optional[List[str]] = None
):
    """Get project metrics/measures - PURE DATA"""
    try:
        # Default metrics if none specified
        if not metrics:
            metrics = [
                "bugs", "vulnerabilities", "code_smells",
                "coverage", "duplicated_lines_density",
                "ncloc", "complexity", "violations",
                "reliability_rating", "security_rating",
                "maintainability_rating", "technical_debt"
            ]
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/measures/component",
            headers=headers,
            params={
                "component": project_key,
                "metricKeys": ",".join(metrics)
            }
        )
        response.raise_for_status()
        
        data = response.json()
        component = data["component"]
        
        # Parse measures
        measures = {}
        for measure in component.get("measures", []):
            measures[measure["metric"]] = {
                "value": measure.get("value"),
                "period": measure.get("period"),
                "best_value": measure.get("bestValue", False)
            }
        
        return {
            "project_key": project_key,
            "measures": measures,
            "component": {
                "name": component.get("name"),
                "qualifier": component.get("qualifier"),
                "language": component.get("language")
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/hotspots")
async def get_hotspots(
    project_key: str,
    status: Optional[str] = None,
    resolution: Optional[str] = None
):
    """Get security hotspots for a project - PURE DATA"""
    try:
        params = {
            "projectKey": project_key,
            "ps": 500
        }
        
        if status:
            params["status"] = status
        if resolution:
            params["resolution"] = resolution
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/hotspots/search",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Group hotspots by file
        hotspots_by_file = {}
        for hotspot in data.get("hotspots", []):
            file_path = hotspot.get("component", "").replace(f"{project_key}:", "")
            if file_path not in hotspots_by_file:
                hotspots_by_file[file_path] = []
            
            hotspots_by_file[file_path].append({
                "key": hotspot["key"],
                "rule": hotspot["ruleKey"],
                "vulnerability_probability": hotspot["vulnerabilityProbability"],
                "status": hotspot["status"],
                "resolution": hotspot.get("resolution"),
                "message": hotspot["message"],
                "line": hotspot.get("line"),
                "author": hotspot.get("author"),
                "creation_date": hotspot["creationDate"]
            })
        
        return {
            "project_key": project_key,
            "total": len(data.get("hotspots", [])),
            "hotspots_by_file": hotspots_by_file
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/duplications")
async def get_duplications(project_key: str, file_path: Optional[str] = None):
    """Get code duplications for a project or file - PURE DATA"""
    try:
        component = f"{project_key}:{file_path}" if file_path else project_key
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/duplications/show",
            headers=headers,
            params={"key": component}
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Parse duplications
        duplications = []
        for dup in data.get("duplications", []):
            blocks = []
            for block in dup.get("blocks", []):
                blocks.append({
                    "from": block["from"],
                    "to": block["to"],
                    "size": block["size"],
                    "file": block["_ref"]
                })
            duplications.append({"blocks": blocks})
        
        return {
            "component": component,
            "duplications": duplications,
            "files": data.get("files", {})
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/projects/{project_key}/analyses")
async def get_recent_analyses(
    project_key: str,
    branch: Optional[str] = None,
    limit: int = 10
):
    """Get recent analyses for a project - PURE DATA"""
    try:
        params = {
            "project": project_key,
            "ps": limit
        }
        
        if branch:
            params["branch"] = branch
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/project_analyses/search",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        data = response.json()
        
        analyses = []
        for analysis in data.get("analyses", []):
            analyses.append({
                "key": analysis["key"],
                "date": analysis["date"],
                "events": analysis.get("events", []),
                "project_version": analysis.get("projectVersion"),
                "build_string": analysis.get("buildString"),
                "revision": analysis.get("revision"),
                "manual_new_code_period_baseline": analysis.get("manualNewCodePeriodBaseline", False)
            })
        
        return analyses
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/projects/{project_key}/issue-details")
async def get_issues_detail(
    project_key: str,
    issue_keys: List[str]
):
    """Get detailed information about specific issues - PURE DATA"""
    try:
        issues_detail = []
        
        for issue_key in issue_keys:
            # Get issue details
            response = requests.get(
                f"{SONARQUBE_URL}/api/issues/search",
                headers=headers,
                params={"issues": issue_key, "additionalFields": "_all"}
            )
            response.raise_for_status()
            
            data = response.json()
            if data["issues"]:
                issue = data["issues"][0]
                
                # Get rule details
                rule_response = requests.get(
                    f"{SONARQUBE_URL}/api/rules/show",
                    headers=headers,
                    params={"key": issue["rule"]}
                )
                rule_response.raise_for_status()
                rule_data = rule_response.json()
                
                issues_detail.append({
                    "issue": {
                        "key": issue["key"],
                        "rule": issue["rule"],
                        "severity": issue["severity"],
                        "type": issue["type"],
                        "message": issue["message"],
                        "component": issue["component"],
                        "line": issue.get("line"),
                        "text_range": issue.get("textRange"),
                        "flows": issue.get("flows", [])
                    },
                    "rule": {
                        "key": rule_data["rule"]["key"],
                        "name": rule_data["rule"]["name"],
                        "description": rule_data["rule"].get("htmlDesc", ""),
                        "severity": rule_data["rule"]["severity"],
                        "type": rule_data["rule"]["type"],
                        "tags": rule_data["rule"].get("tags", []),
                        "remediation_function": rule_data["rule"].get("remFnType"),
                        "remediation_base_effort": rule_data["rule"].get("remFnBaseEffort")
                    }
                })
        
        return {
            "project_key": project_key,
            "issues_detail": issues_detail
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)