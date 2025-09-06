"""
Data models for GitHub Code Status Checker feature.

This module defines the core data structures used throughout the
GitHub status checking functionality.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class FileChange:
    """Represents a change to a single file in the repository."""
    
    file_path: str
    change_type: str  # 'modified', 'added', 'deleted', 'renamed'
    lines_added: int
    lines_removed: int
    last_modified: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'file_path': self.file_path,
            'change_type': self.change_type,
            'lines_added': self.lines_added,
            'lines_removed': self.lines_removed,
            'last_modified': self.last_modified.isoformat() if self.last_modified else None
        }


@dataclass
class CommitInfo:
    """Represents information about a git commit."""
    
    sha: str
    message: str
    timestamp: datetime
    author: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'sha': self.sha,
            'message': self.message,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'author': self.author
        }


@dataclass
class BranchStatus:
    """Represents the status of a git branch."""
    
    name: str
    is_current: bool
    ahead_count: int
    behind_count: int
    last_commit: Optional[CommitInfo] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'is_current': self.is_current,
            'ahead_count': self.ahead_count,
            'behind_count': self.behind_count,
            'last_commit': self.last_commit.to_dict() if self.last_commit else None
        }


@dataclass
class RepositoryStatus:
    """Complete repository status information."""
    
    name: str
    remote_url: str
    current_branch: str
    local_commit_sha: str
    remote_commit_sha: str
    uncommitted_changes: int
    ahead_count: int
    behind_count: int
    is_synchronized: bool
    last_sync_time: Optional[datetime]
    modified_files: List[str]
    staged_files: List[str]
    untracked_files: List[str]
    file_changes: List[FileChange]
    last_commit: Optional[CommitInfo] = None
    remote_latest_commit: Optional[CommitInfo] = None
    
    @property
    def sync_status_text(self) -> str:
        """Get human-readable sync status."""
        if self.is_synchronized:
            return "Up to date"
        elif self.ahead_count > 0 and self.behind_count > 0:
            return f"Diverged: {self.ahead_count} ahead, {self.behind_count} behind"
        elif self.ahead_count > 0:
            return f"Ahead by {self.ahead_count} commits"
        elif self.behind_count > 0:
            return f"Behind by {self.behind_count} commits"
        else:
            return "Unknown status"
    
    @property
    def has_local_changes(self) -> bool:
        """Check if there are any uncommitted local changes."""
        return (self.uncommitted_changes > 0 or 
                len(self.staged_files) > 0 or 
                len(self.untracked_files) > 0)
    
    def get_recommendations(self) -> List[str]:
        """Generate actionable recommendations based on current status."""
        recommendations = []
        
        if self.has_local_changes:
            recommendations.append("Commit local changes")
        
        if self.behind_count > 0:
            if self.has_local_changes:
                recommendations.append("Pull latest changes from remote (after committing)")
            else:
                recommendations.append("Pull latest changes from remote")
        
        if self.ahead_count > 0:
            recommendations.append("Push commits to remote repository")
        
        if self.ahead_count > 0 and self.behind_count > 0:
            recommendations.append("Consider rebasing before pushing")
        
        if not recommendations:
            recommendations.append("Repository is up to date")
        
        return recommendations
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'repository': {
                'name': self.name,
                'remote_url': self.remote_url,
                'current_branch': self.current_branch
            },
            'local_status': {
                'uncommitted_changes': self.uncommitted_changes,
                'staged_files': len(self.staged_files),
                'untracked_files': len(self.untracked_files),
                'modified_files': self.modified_files,
                'staged_file_list': self.staged_files,
                'untracked_file_list': self.untracked_files,
                'last_commit': self.last_commit.to_dict() if self.last_commit else None
            },
            'remote_status': {
                'latest_commit': self.remote_latest_commit.to_dict() if self.remote_latest_commit else None,
                'ahead_count': self.ahead_count,
                'behind_count': self.behind_count
            },
            'sync_status': {
                'is_synchronized': self.is_synchronized,
                'needs_pull': self.behind_count > 0,
                'needs_push': self.ahead_count > 0,
                'status_text': self.sync_status_text,
                'has_local_changes': self.has_local_changes,
                'recommendations': self.get_recommendations()
            },
            'file_changes': [change.to_dict() for change in self.file_changes]
        }


@dataclass
class GitStatusResult:
    """Result of a git status analysis operation."""
    
    success: bool
    repository_status: Optional[RepositoryStatus]
    error_message: Optional[str] = None
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            'success': self.success,
            'error_message': self.error_message,
            'warnings': self.warnings
        }
        
        if self.repository_status:
            result.update(self.repository_status.to_dict())
        
        return result