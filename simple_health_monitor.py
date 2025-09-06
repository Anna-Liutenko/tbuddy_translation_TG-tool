#!/usr/bin/env python3
"""
Simple Repository Health Monitor for Validation

A simplified version for testing the implementation.
"""

import os
import sys
import logging
from datetime import datetime
from git_analyzer import GitStatusAnalyzer


class SimpleHealthMonitor:
    """Simple health monitor for validation."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = os.path.abspath(repo_path)
        self.git_analyzer = GitStatusAnalyzer(repo_path)
        self.logger = logging.getLogger(__name__)
    
    def run_health_check(self):
        """Run basic health check."""
        health_report = {
            'timestamp': datetime.now().isoformat(),
            'repository_path': self.repo_path,
            'overall_health': 'unknown',
            'health_score': 0,
            'issues': []
        }
        
        try:
            # Check if it's a git repository
            if not self.git_analyzer.check_is_git_repository():
                health_report['issues'].append({
                    'type': 'not_git_repo',
                    'severity': 'critical',
                    'message': 'Not a git repository'
                })
                health_report['overall_health'] = 'critical'
                return health_report
            
            # Run diagnosis
            diagnosis = self.git_analyzer.diagnose_push_issues()
            health_report['issues'] = diagnosis.get('issues', [])
            
            # Calculate simple health score
            score = 100
            for issue in health_report['issues']:
                severity = issue.get('severity', 'medium')
                if severity == 'critical':
                    score -= 25
                elif severity == 'high':
                    score -= 15
                elif severity == 'medium':
                    score -= 10
                elif severity == 'low':
                    score -= 5
            
            health_report['health_score'] = max(0, score)
            
            # Determine overall health
            if score >= 90:
                health_report['overall_health'] = 'excellent'
            elif score >= 75:
                health_report['overall_health'] = 'good'
            elif score >= 50:
                health_report['overall_health'] = 'fair'
            elif score >= 25:
                health_report['overall_health'] = 'poor'
            else:
                health_report['overall_health'] = 'critical'
            
        except Exception as e:
            self.logger.error(f"Error during health check: {e}")
            health_report['issues'].append({
                'type': 'health_check_error',
                'severity': 'critical',
                'message': f'Health check failed: {e}'
            })
            health_report['overall_health'] = 'critical'
        
        return health_report
    
    def format_health_report(self, health_report):
        """Format health report for console output."""
        lines = []
        
        # Header
        health_icon = {
            'excellent': '🟢',
            'good': '🟡',
            'fair': '🟠',
            'poor': '🔴',
            'critical': '💥'
        }.get(health_report['overall_health'], '❓')
        
        lines.append(f"\n{health_icon} REPOSITORY HEALTH REPORT")
        lines.append("=" * 50)
        lines.append(f"📁 Repository: {os.path.basename(self.repo_path)}")
        lines.append(f"⏰ Timestamp: {health_report['timestamp']}")
        lines.append(f"📊 Health Score: {health_report['health_score']}/100 ({health_report['overall_health'].upper()})")
        lines.append("")
        
        # Issues
        if health_report['issues']:
            lines.append("⚠️  ISSUES FOUND")
            lines.append("-" * 20)
            
            for issue in health_report['issues']:
                severity_icon = {
                    'critical': '🔴',
                    'high': '🟡',
                    'medium': '🔵',
                    'low': '🟢'
                }.get(issue.get('severity'), '❓')
                
                lines.append(f"{severity_icon} {issue.get('message', 'Unknown issue')}")
            
            lines.append("")
        else:
            lines.append("✅ No issues detected!")
        
        return "\n".join(lines)


def main():
    """Simple CLI interface."""
    try:
        monitor = SimpleHealthMonitor()
        health_report = monitor.run_health_check()
        print(monitor.format_health_report(health_report))
        
        # Exit with appropriate code
        if health_report['overall_health'] in ['critical', 'poor']:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()