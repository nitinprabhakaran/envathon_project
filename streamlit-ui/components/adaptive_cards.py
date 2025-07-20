from typing import Dict, List, Optional
import html
from datetime import datetime

class AdaptiveCards:
    """Create adaptive cards for different types of content with color coding"""

    @staticmethod
    def create_failure_card(failure: Dict) -> str:
        """Create an adaptive card for pipeline failure (HTML for st.markdown)"""
        status = failure.get('status', 'failed')
        status_color = {
            'failed': '#dc3545',
            'success': '#28a745',
            'running': '#007bff',
            'pending': '#ffc107',
            'canceled': '#6c757d'
        }.get(status, '#dc3545')

        # Calculate duration if start and end times available
        duration = failure.get('duration', 'N/A')
        if duration == 'N/A' and failure.get('started_at') and failure.get('finished_at'):
            try:
                start = datetime.fromisoformat(failure['started_at'].replace('Z', '+00:00'))
                end = datetime.fromisoformat(failure['finished_at'].replace('Z', '+00:00'))
                duration_seconds = (end - start).total_seconds()
                duration = f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s"
            except Exception:
                duration = "N/A"

        # Priority indicator
        priority = failure.get('priority', 'normal')
        priority_badge = ""
        if priority == 'high':
            priority_badge = (
                '<span style="background-color: #ff0000; color: white; padding: 2px 6px; '
                'border-radius: 3px; font-size: 10px; margin-left: 10px;">HIGH PRIORITY</span>'
            )

        # Error snippet if available
        error_snippet = ""
        if failure.get('error_log'):
            error_lines = failure['error_log'].split('\n')
            display_lines = error_lines[:3]
            more_lines = len(error_lines) - 3
            more_lines_html = f'<br><em>... and {more_lines} more lines</em>' if more_lines > 0 else ''
            error_snippet = (
                "<div style='margin-top: 10px; padding: 10px; background-color: #2d2d2d; color: #f8f8f2; "
                "border-radius: 4px; font-family: monospace; font-size: 12px;'>"
                "<strong style='color: #ff6b6b;'>Error Output:</strong><br>"
                f"{'<br>'.join(html.escape(line) for line in display_lines)}"
                f"{more_lines_html}"
                "</div>"
            )

        # Author formatting
        author = failure.get('commit', {}).get('author', 'unknown')
        if isinstance(author, dict):
            author = html.escape(str(author))
        else:
            author = html.escape(author)

        # Commit message formatting
        commit_msg = failure.get('commit', {}).get('message', 'No message')
        commit_msg = html.escape(commit_msg[:100]) + "..."

        return (
            f"<div style='border: 2px solid {status_color}; border-radius: 8px; padding: 15px; margin: 10px 0; "
            "background-color: #f8f9fa; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
            "<div style='display: flex; justify-content: space-between; align-items: center;'>"
            f"<h4 style='margin: 0; color: #333;'>Pipeline #{failure.get('pipeline_id', 'Unknown')}{priority_badge}</h4>"
            f"<span style='background-color: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;'>"
            f"{status.upper()}</span></div>"
            "<hr style='margin: 10px 0; border-color: #e0e0e0;'>"
            "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 10px;'>"
            "<div>"
            f"<strong>🌿 Branch:</strong> <code>{html.escape(failure.get('branch', 'unknown'))}</code><br>"
            f"<strong>📦 Stage:</strong> <span style='color: {status_color}; font-weight: bold;'>{html.escape(failure.get('failed_stage', 'unknown'))}</span><br>"
            f"<strong>👤 Author:</strong> {author}"
            "</div>"
            "<div>"
            f"<strong>🔗 Commit:</strong> <code>{html.escape(failure.get('commit', {}).get('sha', '')[:8])}</code><br>"
            f"<strong>🕐 Time:</strong> {html.escape(failure.get('timestamp', '')[:19])}<br>"
            f"<strong>⏱️ Duration:</strong> {duration}"
            "</div></div>"
            "<div style='margin-top: 10px; padding: 10px; background-color: #e9ecef; border-radius: 4px;'>"
            "<strong>💬 Commit Message:</strong><br>"
            f"<em>{commit_msg}</em>"
            "</div>"
            f"{error_snippet}"
            "</div>"
        )
    
    @staticmethod
    def create_sonarqube_card(issue: Dict) -> str:
        """Create an adaptive card for SonarQube issues"""
        qg_status = issue.get('quality_gate_status', 'ERROR')
        qg_color = {
            'OK': '#28a745',
            'WARN': '#ffc107',
            'ERROR': '#dc3545',
            'NONE': '#6c757d'
        }.get(qg_status, '#dc3545')
        
        # Metrics with thresholds
        metrics_html = ""
        key_metrics = ['bugs', 'vulnerabilities', 'code_smells', 'coverage', 'duplicated_lines_density']
        
        for metric in key_metrics:
            value = issue.get('metrics', {}).get(metric, 'N/A')
            threshold = issue.get('thresholds', {}).get(metric)
            
            if value != 'N/A':
                icon = AdaptiveCards._get_metric_icon(metric)
                color = AdaptiveCards._get_metric_color(metric, value, threshold)
                
                metrics_html += f"""
                <div style="text-align: center; padding: 10px; background-color: white; border-radius: 6px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
                    <div style="font-size: 20px;">{icon}</div>
                    <div style="font-size: 24px; font-weight: bold; color: {color};">
                        {value}{'%' if metric in ['coverage', 'duplicated_lines_density'] else ''}
                    </div>
                    <div style="font-size: 12px; color: #6c757d;">{metric.replace('_', ' ').title()}</div>
                </div>
                """
        
        # Failed conditions
        conditions_html = ""
        for condition in issue.get('conditions', []):
            condition_status = condition.get('status', 'ERROR')
            condition_color = '#dc3545' if condition_status == 'ERROR' else '#ffc107'
            
            conditions_html += f"""
            <div style="padding: 8px; margin: 5px 0; background-color: {condition_color}20; border-left: 4px solid {condition_color}; border-radius: 4px;">
                <strong>{condition.get('metric', 'unknown').replace('_', ' ').title()}:</strong> 
                {condition.get('actual', 'N/A')} 
                <span style="color: #6c757d;">(threshold: {condition.get('threshold', 'N/A')})</span>
            </div>
            """
        
        return f"""
        <div style="border: 2px solid {qg_color}; border-radius: 8px; padding: 15px; margin: 10px 0; background-color: #f8f9fa; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <h4 style="margin: 0; color: #333;">
                    {issue.get('project_name', 'Unknown Project')}
                </h4>
                <span style="background-color: {qg_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px;">
                    Quality Gate: {qg_status}
                </span>
            </div>
            <div style="font-size: 12px; color: #6c757d; margin-top: 5px;">
                Project Key: <code>{issue.get('project_key', 'unknown')}</code> | 
                Last Analysis: {issue.get('timestamp', 'unknown')[:19]}
            </div>
            <hr style="margin: 10px 0; border-color: #e0e0e0;">
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; margin: 15px 0;">
                {metrics_html}
            </div>
            
            {f'''
            <div style="margin-top: 15px;">
                <strong>❌ Failed Conditions:</strong>
                {conditions_html if conditions_html else '<div style="padding: 10px; color: #6c757d;">No specific conditions failed</div>'}
            </div>
            ''' if conditions_html else ''}
        </div>
        """
    
    @staticmethod
    def create_analysis_card(analysis: Dict) -> str:
        """Create a card for analysis results"""
        confidence = analysis.get('confidence', 0)
        confidence_color = AdaptiveCards._get_confidence_color(confidence)
        
        # Root cause section
        root_cause_html = f"""
        <div style="padding: 15px; background-color: #f0f0f0; border-radius: 6px; margin: 10px 0;">
            <h4 style="margin: 0 0 10px 0; color: #333;">🎯 Root Cause Analysis</h4>
            <p style="margin: 0; color: #555;">{html.escape(analysis.get('root_cause', 'Unable to determine root cause'))}</p>
        </div>
        """
        
        # Affected files
        affected_files_html = ""
        if analysis.get('affected_files'):
            files_list = ''.join([f'<li><code>{html.escape(file)}</code></li>' for file in analysis['affected_files'][:5]])
            affected_files_html = f"""
            <div style="padding: 15px; background-color: #fff3cd; border-radius: 6px; margin: 10px 0;">
                <h4 style="margin: 0 0 10px 0; color: #856404;">📁 Affected Files</h4>
                <ul style="margin: 0; padding-left: 20px;">
                    {files_list}
                    {f'<li><em>... and {len(analysis["affected_files"]) - 5} more files</em></li>' if len(analysis.get("affected_files", [])) > 5 else ''}
                </ul>
            </div>
            """
        
        return f"""
        <div style="border: 2px solid {confidence_color}; border-radius: 8px; padding: 20px; margin: 15px 0; background-color: white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 20px;">
                <h3 style="margin: 0; color: {confidence_color};">
                    {'✅' if confidence >= 80 else '⚠️' if confidence >= 60 else '❌'} 
                    Confidence Score: {confidence}%
                </h3>
                <div style="width: 100%; height: 10px; background-color: #e0e0e0; border-radius: 5px; margin-top: 10px;">
                    <div style="width: {confidence}%; height: 100%; background-color: {confidence_color}; border-radius: 5px;"></div>
                </div>
            </div>
            
            {root_cause_html}
            {affected_files_html}
            
            <div style="margin-top: 15px; padding: 10px; background-color: #d4edda; border-radius: 6px;">
                <strong>💡 Recommendations:</strong> {len(analysis.get('fixes', []))} fixes available
            </div>
        </div>
        """
    
    @staticmethod
    def _get_metric_icon(metric: str) -> str:
        """Get icon for metric type"""
        icons = {
            "bugs": "🐛",
            "vulnerabilities": "🔒",
            "code_smells": "👃",
            "coverage": "📊",
            "duplicated_lines_density": "📄",
            "security_hotspots": "🔥",
            "reliability_rating": "⭐",
            "security_rating": "🛡️",
            "maintainability_rating": "🔧"
        }
        return icons.get(metric, "📌")
    
    @staticmethod
    def _get_metric_color(metric: str, value: any, threshold: any = None) -> str:
        """Get color based on metric value and threshold"""
        try:
            val = float(str(value).replace('%', ''))
            
            if metric in ['bugs', 'vulnerabilities', 'code_smells']:
                if val == 0:
                    return '#28a745'
                elif val <= 5:
                    return '#ffc107'
                else:
                    return '#dc3545'
            elif metric == 'coverage':
                if val >= 80:
                    return '#28a745'
                elif val >= 60:
                    return '#ffc107'
                else:
                    return '#dc3545'
            elif metric == 'duplicated_lines_density':
                if val <= 3:
                    return '#28a745'
                elif val <= 5:
                    return '#ffc107'
                else:
                    return '#dc3545'
        except:
            pass
        
        return '#6c757d'  # Default gray
    
    @staticmethod
    def _get_confidence_color(confidence: int) -> str:
        """Get color for confidence score"""
        if confidence >= 80:
            return '#28a745'  # Green
        elif confidence >= 60:
            return '#ffc107'  # Yellow
        else:
            return '#dc3545'  # Red