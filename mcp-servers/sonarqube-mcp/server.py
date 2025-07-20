# mcp-servers/sonarqube-mcp/server.py
import os
import json
import logging
from typing import Dict, List, Any, Optional
import requests
from fastmcp import FastMCP
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("sonarqube-mcp")

# SonarQube configuration
SONARQUBE_URL = os.environ.get("SONARQUBE_URL", "http://sonarqube:9000")
SONARQUBE_TOKEN = os.environ.get("SONARQUBE_TOKEN", "")

# Headers for API requests
headers = {}
if SONARQUBE_TOKEN:
    headers["Authorization"] = f"Bearer {SONARQUBE_TOKEN}"
    logger.info("SonarQube token configured")
else:
    logger.warning("SonarQube token not configured - some operations may fail")

@mcp.tool()
def get_project_issues(
    project_key: str,
    severity: List[str] = None,
    types: List[str] = None,
    resolved: bool = False
) -> Dict[str, Any]:
    """Get issues for a project with filtering options"""
    try:
        logger.info(f"Getting issues for project {project_key}")
        
        params = {
            "componentKeys": project_key,
            "resolved": str(resolved).lower(),
            "ps": 100  # Page size
        }
        
        if severity:
            params["severities"] = ",".join(severity)
        if types:
            params["types"] = ",".join(types)
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/issues/search",
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Group issues by file for better organization
        issues_by_file = {}
        total_issues = data.get("total", 0)
        
        for issue in data.get("issues", []):
            file_path = issue.get("component", "").replace(f"{project_key}:", "")
            if not file_path:
                file_path = "project_root"
            
            if file_path not in issues_by_file:
                issues_by_file[file_path] = []
            
            # Clean up issue data
            clean_issue = {
                "key": issue["key"],
                "rule": issue["rule"],
                "severity": issue["severity"],
                "type": issue["type"],
                "message": issue["message"],
                "line": issue.get("line"),
                "effort": issue.get("effort"),
                "status": issue["status"],
                "creation_date": issue["creationDate"],
                "update_date": issue.get("updateDate"),
                "tags": issue.get("tags", [])
            }
            
            issues_by_file[file_path].append(clean_issue)
        
        logger.info(f"Found {total_issues} issues for project {project_key}")
        
        return {
            "project_key": project_key,
            "total": total_issues,
            "issues_by_file": issues_by_file,
            "summary": {
                "files_with_issues": len(issues_by_file),
                "total_issues": total_issues
            }
        }
        
    except requests.RequestException as e:
        logger.error(f"HTTP error getting issues: {e}")
        return {"error": f"HTTP error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error getting project issues: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_quality_gate_status(project_key: str) -> Dict[str, Any]:
    """Get quality gate status for a project"""
    try:
        logger.info(f"Getting quality gate status for project {project_key}")
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/qualitygates/project_status",
            headers=headers,
            params={"projectKey": project_key},
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        project_status = data.get("projectStatus", {})
        
        # Parse conditions for better readability
        conditions = []
        for condition in project_status.get("conditions", []):
            conditions.append({
                "metric": condition["metricKey"],
                "status": condition["status"],
                "actual_value": condition.get("actualValue"),
                "error_threshold": condition.get("errorThreshold"),
                "warning_threshold": condition.get("warningThreshold"),
                "comparator": condition.get("comparator")
            })
        
        result = {
            "project_key": project_key,
            "status": project_status.get("status", "UNKNOWN"),
            "conditions": conditions,
            "period": project_status.get("period")
        }
        
        logger.info(f"Quality gate status for {project_key}: {result['status']}")
        return result
        
    except requests.RequestException as e:
        logger.error(f"HTTP error getting quality gate: {e}")
        return {"error": f"HTTP error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error getting quality gate status: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_project_measures(
    project_key: str,
    metrics: List[str] = None
) -> Dict[str, Any]:
    """Get project metrics/measures"""
    try:
        logger.info(f"Getting measures for project {project_key}")
        
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
            },
            timeout=30
        )
        response.raise_for_status()
        
        data = response.json()
        component = data.get("component", {})
        
        # Parse measures into a more usable format
        measures = {}
        for measure in component.get("measures", []):
            metric_key = measure["metric"]
            measures[metric_key] = {
                "value": measure.get("value"),
                "period": measure.get("period"),
                "best_value": measure.get("bestValue", False)
            }
        
        result = {
            "project_key": project_key,
            "measures": measures,
            "component": {
                "name": component.get("name"),
                "qualifier": component.get("qualifier"),
                "language": component.get("language")
            }
        }
        
        logger.info(f"Retrieved {len(measures)} measures for project {project_key}")
        return result
        
    except requests.RequestException as e:
        logger.error(f"HTTP error getting measures: {e}")
        return {"error": f"HTTP error: {str(e)}"}
    except Exception as e:
        logger.error(f"Error getting project measures: {e}")
        return {"error": str(e)}

@mcp.tool()
def get_recent_analyses(
    project_key: str,
    branch: str = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """Get recent analyses for a project"""
    try:
        logger.info(f"Getting recent analyses for project {project_key}")
        
        params = {
            "project": project_key,
            "ps": limit
        }
        
        if branch:
            params["branch"] = branch
        
        response = requests.get(
            f"{SONARQUBE_URL}/api/project_analyses/search",
            headers=headers,
            params=params,
            timeout=30
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
                "revision": analysis.get("revision")
            })
        
        logger.info(f"Found {len(analyses)} recent analyses for project {project_key}")
        return analyses
        
    except requests.RequestException as e:
        logger.error(f"HTTP error getting analyses: {e}")
        return [{"error": f"HTTP error: {str(e)}"}]
    except Exception as e:
        logger.error(f"Error getting recent analyses: {e}")
        return [{"error": str(e)}]

@mcp.tool()
def suggest_fixes_for_issues(
    project_key: str,
    issue_keys: List[str]
) -> Dict[str, Any]:
    """Get detailed information about specific issues to help with fix suggestions"""
    try:
        logger.info(f"Getting fix suggestions for {len(issue_keys)} issues in project {project_key}")
        
        issues_detail = []
        
        for issue_key in issue_keys[:10]:  # Limit to 10 issues to avoid timeout
            try:
                # Get issue details
                issue_response = requests.get(
                    f"{SONARQUBE_URL}/api/issues/search",
                    headers=headers,
                    params={"issues": issue_key, "additionalFields": "_all"},
                    timeout=30
                )
                issue_response.raise_for_status()
                
                issue_data = issue_response.json()
                if not issue_data.get("issues"):
                    continue
                
                issue = issue_data["issues"][0]
                
                # Get rule details
                rule_response = requests.get(
                    f"{SONARQUBE_URL}/api/rules/show",
                    headers=headers,
                    params={"key": issue["rule"]},
                    timeout=30
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
                        "description": rule_data["rule"].get("htmlDesc", "")[:500] + "..." if rule_data["rule"].get("htmlDesc", "") else "",
                        "severity": rule_data["rule"]["severity"],
                        "type": rule_data["rule"]["type"],
                        "tags": rule_data["rule"].get("tags", [])
                    }
                })
                
            except Exception as e:
                logger.warning(f"Could not get details for issue {issue_key}: {e}")
                continue
        
        result = {
            "project_key": project_key,
            "issues_detail": issues_detail,
            "processed_count": len(issues_detail),
            "requested_count": len(issue_keys)
        }
        
        logger.info(f"Processed {len(issues_detail)} issues for fix suggestions")
        return result
        
    except Exception as e:
        logger.error(f"Error getting fix suggestions: {e}")
        return {"error": str(e)}

@mcp.tool()
def health_check() -> Dict[str, Any]:
    """Check if SonarQube connection is healthy"""
    try:
        logger.info("Performing SonarQube health check")
        
        # Check system status
        status_response = requests.get(
            f"{SONARQUBE_URL}/api/system/status",
            headers=headers,
            timeout=10
        )
        status_response.raise_for_status()
        status_data = status_response.json()
        
        # Get version
        try:
            version_response = requests.get(
                f"{SONARQUBE_URL}/api/server/version",
                headers=headers,
                timeout=10
            )
            version = version_response.text.strip() if version_response.status_code == 200 else "unknown"
        except:
            version = "unknown"
        
        result = {
            "status": "healthy",
            "sonarqube_url": SONARQUBE_URL,
            "version": version,
            "system_status": status_data.get("status", "UNKNOWN"),
            "authenticated": bool(SONARQUBE_TOKEN)
        }
        
        logger.info("SonarQube health check passed")
        return result
        
    except requests.RequestException as e:
        logger.error(f"SonarQube health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": f"HTTP error: {str(e)}",
            "sonarqube_url": SONARQUBE_URL,
            "authenticated": bool(SONARQUBE_TOKEN)
        }
    except Exception as e:
        logger.error(f"SonarQube health check failed: {e}")
        return {
            "status": "unhealthy", 
            "error": str(e),
            "sonarqube_url": SONARQUBE_URL,
            "authenticated": bool(SONARQUBE_TOKEN)
        }

if __name__ == "__main__":
    import uvicorn
    
    # Always run in HTTP mode for container deployment
    logger.info("Starting SonarQube MCP server in HTTP mode")
    logger.info(f"SonarQube URL: {SONARQUBE_URL}")
    logger.info(f"SonarQube Token configured: {'Yes' if SONARQUBE_TOKEN else 'No'}")
    
    # Run FastMCP in HTTP mode
    uvicorn.run(
        mcp.create_app(),
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )