"""
Status Reporter for GitHub Code Status Checker.

This module provides functionality to compile comprehensive status reports,
format comparison results, and generate actionable recommendations.
"""

import os
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from git_analyzer import GitStatusAnalyzer
from github_client import GitHubClient
from models import GitStatusResult, RepositoryStatus


class StatusReporter:
    """Compiles comprehensive status reports and generates recommendations."""
    
    def __init__(self, repo_path: str = ".", github_token: Optional[str] = None):
        """
        Initialize status reporter.
        
        Args:
            repo_path: Path to the git repository
            github_token: GitHub API token
        """
        self.repo_path = repo_path
        self.git_analyzer = GitStatusAnalyzer(repo_path)
        self.github_client = GitHubClient(github_token)
        self.logger = logging.getLogger(__name__)
    
    def generate_comprehensive_report(self, include_github: bool = True) -> GitStatusResult:
        """
        Generate a comprehensive status report combining local and remote information.
        
        Args:
            include_github: Whether to include GitHub API information
            
        Returns:
            GitStatusResult with complete status information
        """
        try:
            # Get local status first
            local_result = self.git_analyzer.get_local_status()
            
            if not local_result.success:
                return local_result
            
            repo_status = local_result.repository_status
            if not repo_status:
                return local_result
            
            # Enhance with GitHub information if requested and available
            if include_github and repo_status.remote_url:
                github_info = self._get_github_enhancement(repo_status)
                if github_info:
                    repo_status = self._merge_github_info(repo_status, github_info)
            
            return GitStatusResult(
                success=True,
                repository_status=repo_status,
                warnings=local_result.warnings
            )
            
        except Exception as e:
            self.logger.error(f"Error generating comprehensive report: {e}")
            return GitStatusResult(
                success=False,
                repository_status=None,
                error_message=str(e)
            )
    
    def _get_github_enhancement(self, repo_status: RepositoryStatus) -> Optional[Dict[str, Any]]:
        """Get additional information from GitHub API."""
        try:
            if not self.github_client.test_connection():
                self.logger.warning("GitHub API connection failed")
                return None
            
            github_info = self.github_client.get_repository_info(
                repo_status.remote_url,
                repo_status.current_branch
            )
            
            if github_info['success']:
                return github_info
            else:
                self.logger.warning(f"GitHub API error: {github_info.get('error_message')}")
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting GitHub enhancement: {e}")
            return None
    
    def _merge_github_info(self, repo_status: RepositoryStatus, github_info: Dict[str, Any]) -> RepositoryStatus:
        """Merge GitHub API information with local repository status."""
        try:
            # Update remote commit information if available
            if github_info.get('latest_commit'):
                from models import CommitInfo
                commit_data = github_info['latest_commit']
                repo_status.remote_latest_commit = CommitInfo(
                    sha=commit_data['sha'],
                    message=commit_data['message'],
                    timestamp=datetime.fromisoformat(commit_data['timestamp'].replace('Z', '+00:00')),
                    author=commit_data['author']
                )
                repo_status.remote_commit_sha = commit_data['sha']
            
            # Update synchronization status based on remote info
            if repo_status.remote_latest_commit and repo_status.last_commit:
                repo_status.is_synchronized = (
                    repo_status.local_commit_sha == repo_status.remote_commit_sha and
                    repo_status.uncommitted_changes == 0
                )
            
            return repo_status
            
        except Exception as e:
            self.logger.error(f"Error merging GitHub info: {e}")
            return repo_status
    
    def format_status_summary(self, result: GitStatusResult) -> str:
        """
        Format a human-readable status summary.
        
        Args:
            result: GitStatusResult to format
            
        Returns:
            Formatted status summary string
        """
        if not result.success:
            return f"❌ Error: {result.error_message}"
        
        repo = result.repository_status
        if not repo:
            return "❌ No repository status available"
        
        lines = []
        
        # Repository header
        lines.append(f"📁 Repository: {repo.name}")
        lines.append(f"🌿 Branch: {repo.current_branch}")
        
        # Sync status
        if repo.is_synchronized:
            lines.append("✅ Status: Up to date")
        else:
            lines.append(f"⚠️  Status: {repo.sync_status_text}")
        
        # Local changes
        if repo.has_local_changes:
            lines.append(f"📝 Local changes: {repo.uncommitted_changes} files")
            if repo.staged_files:
                lines.append(f"   • {len(repo.staged_files)} staged")
            if repo.modified_files:
                lines.append(f"   • {len(repo.modified_files)} modified")
            if repo.untracked_files:
                lines.append(f"   • {len(repo.untracked_files)} untracked")
        
        # Remote comparison
        if repo.ahead_count > 0 or repo.behind_count > 0:
            lines.append("🔄 Remote comparison:")
            if repo.ahead_count > 0:
                lines.append(f"   • {repo.ahead_count} commits ahead")
            if repo.behind_count > 0:
                lines.append(f"   • {repo.behind_count} commits behind")
        
        # Last commits
        if repo.last_commit:
            lines.append(f"💾 Last local commit: {repo.last_commit.sha} - {repo.last_commit.message[:50]}")
        
        if repo.remote_latest_commit:
            lines.append(f"🌐 Last remote commit: {repo.remote_latest_commit.sha} - {repo.remote_latest_commit.message[:50]}")
        
        # Recommendations
        recommendations = repo.get_recommendations()
        if recommendations and recommendations[0] != "Repository is up to date":
            lines.append("\n💡 Recommended actions:")
            for rec in recommendations:
                lines.append(f"   • {rec}")
        
        # Warnings
        if result.warnings:
            lines.append("\n⚠️  Warnings:")
            for warning in result.warnings:
                lines.append(f"   • {warning}")
        
        return "\n".join(lines)
    
    def format_detailed_report(self, result: GitStatusResult) -> str:
        """
        Format a detailed status report with file-level information.
        
        Args:
            result: GitStatusResult to format
            
        Returns:
            Detailed formatted report string
        """
        summary = self.format_status_summary(result)
        
        if not result.success or not result.repository_status:
            return summary
        
        repo = result.repository_status
        lines = [summary, "\n" + "="*60 + "\n"]
        
        # File changes detail
        if repo.file_changes:
            lines.append("📄 File Changes Details:")
            for change in repo.file_changes:
                change_icon = {
                    'modified': '📝',
                    'added': '➕',
                    'deleted': '❌',
                    'renamed': '🔄'
                }.get(change.change_type, '📄')
                
                lines.append(f"   {change_icon} {change.file_path} ({change.change_type})")
                if change.lines_added > 0 or change.lines_removed > 0:
                    lines.append(f"      +{change.lines_added} -{change.lines_removed} lines")
            lines.append("")
        
        # Repository info
        lines.append("ℹ️  Repository Information:")
        lines.append(f"   • Remote URL: {repo.remote_url}")
        lines.append(f"   • Current branch: {repo.current_branch}")
        if repo.last_sync_time:
            lines.append(f"   • Last sync: {repo.last_sync_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)
    
    def generate_table_format(self, result: GitStatusResult) -> str:
        """
        Generate a table-formatted status report.
        
        Args:
            result: GitStatusResult to format
            
        Returns:
            Table-formatted status string
        """
        if not result.success or not result.repository_status:
            return f"Error: {result.error_message or 'No status available'}"
        
        repo = result.repository_status
        
        # Create table data
        rows = [
            ["Repository", repo.name],
            ["Branch", repo.current_branch],
            ["Status", repo.sync_status_text],
            ["Local Changes", f"{repo.uncommitted_changes} files"],
            ["Staged Files", str(len(repo.staged_files))],
            ["Modified Files", str(len(repo.modified_files))],
            ["Untracked Files", str(len(repo.untracked_files))],
            ["Ahead by", f"{repo.ahead_count} commits"],
            ["Behind by", f"{repo.behind_count} commits"],
            ["Synchronized", "✅" if repo.is_synchronized else "❌"],
        ]
        
        if repo.last_commit:
            rows.append(["Last Local Commit", f"{repo.last_commit.sha} - {repo.last_commit.message[:30]}"])
        
        if repo.remote_latest_commit:
            rows.append(["Last Remote Commit", f"{repo.remote_latest_commit.sha} - {repo.remote_latest_commit.message[:30]}"])
        
        # Calculate column widths
        max_key_width = max(len(row[0]) for row in rows)
        max_value_width = max(len(str(row[1])) for row in rows)
        
        # Format table
        lines = []
        lines.append("+" + "-" * (max_key_width + 2) + "+" + "-" * (max_value_width + 2) + "+")
        
        for key, value in rows:
            lines.append(f"| {key:<{max_key_width}} | {str(value):<{max_value_width}} |")
        
        lines.append("+" + "-" * (max_key_width + 2) + "+" + "-" * (max_value_width + 2) + "+")
        
        return "\n".join(lines)
    
    def get_action_plan(self, result: GitStatusResult) -> List[Dict[str, str]]:
        """
        Generate a structured action plan based on repository status.
        
        Args:
            result: GitStatusResult to analyze
            
        Returns:
            List of action items with commands and descriptions
        """
        if not result.success or not result.repository_status:
            return []
        
        repo = result.repository_status
        actions = []
        
        # Handle uncommitted changes
        if repo.has_local_changes:
            if repo.modified_files or repo.staged_files:
                actions.append({
                    "action": "commit_changes",
                    "description": "Commit local changes",
                    "command": "git add . && git commit -m \"Your commit message\"",
                    "priority": "high"
                })
            
            if repo.untracked_files:
                actions.append({
                    "action": "review_untracked",
                    "description": "Review untracked files",
                    "command": "git status",
                    "priority": "medium"
                })
        
        # Handle remote synchronization
        if repo.behind_count > 0:
            if repo.has_local_changes:
                actions.append({
                    "action": "pull_after_commit",
                    "description": "Pull remote changes after committing",
                    "command": f"git pull origin {repo.current_branch}",
                    "priority": "high"
                })
            else:
                actions.append({
                    "action": "pull_changes",
                    "description": "Pull remote changes",
                    "command": f"git pull origin {repo.current_branch}",
                    "priority": "high"
                })
        
        if repo.ahead_count > 0:
            actions.append({
                "action": "push_changes",
                "description": "Push local commits to remote",
                "command": f"git push origin {repo.current_branch}",
                "priority": "medium"
            })
        
        # Handle diverged branches
        if repo.ahead_count > 0 and repo.behind_count > 0:
            actions.append({
                "action": "rebase_option",
                "description": "Consider rebasing before pushing",
                "command": f"git rebase origin/{repo.current_branch}",
                "priority": "low"
            })
        
        return actions