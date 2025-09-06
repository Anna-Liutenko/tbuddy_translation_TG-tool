"""
Git Status Analyzer for GitHub Code Status Checker.

This module provides functionality to analyze local git repository status,
including uncommitted changes, branch comparisons, and repository state.
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Any
from git import Repo, InvalidGitRepositoryError
from git.exc import GitCommandError
from models import (
    RepositoryStatus, FileChange, CommitInfo, BranchStatus, GitStatusResult
)


class GitStatusAnalyzer:
    """Analyzes local git repository status and compares with remote."""
    
    def __init__(self, repo_path: str = "."):
        """Initialize analyzer with repository path."""
        self.repo_path = os.path.abspath(repo_path)
        self.logger = logging.getLogger(__name__)
        self._repo = None
        
    @property
    def repo(self) -> Repo:
        """Get git repository instance, creating if needed."""
        if self._repo is None:
            try:
                self._repo = Repo(self.repo_path)
            except InvalidGitRepositoryError:
                raise InvalidGitRepositoryError(f"Not a git repository: {self.repo_path}")
        return self._repo
    
    def check_is_git_repository(self) -> bool:
        """Check if the current directory is a git repository."""
        try:
            self.repo
            return True
        except InvalidGitRepositoryError:
            return False
    
    def get_repository_name(self) -> str:
        """Extract repository name from remote URL or directory name."""
        try:
            # Try to get from remote URL first
            remotes = list(self.repo.remotes)
            if remotes:
                remote_url = remotes[0].url
                # Extract name from URL like git@github.com:user/repo.git
                if '/' in remote_url:
                    name = remote_url.split('/')[-1]
                    if name.endswith('.git'):
                        name = name[:-4]
                    return name
        except Exception:
            pass
        
        # Fallback to directory name
        return os.path.basename(self.repo_path)
    
    def get_remote_url(self) -> str:
        """Get the remote repository URL."""
        try:
            remotes = list(self.repo.remotes)
            if remotes:
                return remotes[0].url
        except Exception:
            pass
        return ""
    
    def get_current_branch(self) -> str:
        """Get the current branch name."""
        try:
            return self.repo.active_branch.name
        except Exception:
            return "HEAD"
    
    def get_last_commit_info(self, branch_name: Optional[str] = None) -> Optional[CommitInfo]:
        """Get information about the last commit."""
        try:
            if branch_name:
                commit = self.repo.commit(branch_name)
            else:
                commit = self.repo.head.commit
            
            return CommitInfo(
                sha=commit.hexsha[:8],
                message=commit.message.strip(),
                timestamp=datetime.fromtimestamp(commit.committed_date),
                author=commit.author.name
            )
        except Exception as e:
            self.logger.error(f"Error getting last commit info: {e}")
            return None
    
    def get_uncommitted_changes(self) -> Tuple[List[str], List[str], List[str], int]:
        """
        Get uncommitted changes in the repository.
        
        Returns:
            Tuple of (modified_files, staged_files, untracked_files, total_changes)
        """
        try:
            # Get modified files (both staged and unstaged)
            modified_files = [item.a_path for item in self.repo.index.diff(None)]
            staged_files = [item.a_path for item in self.repo.index.diff("HEAD")]
            untracked_files = self.repo.untracked_files
            
            total_changes = len(modified_files) + len(staged_files) + len(untracked_files)
            
            return modified_files, staged_files, untracked_files, total_changes
            
        except Exception as e:
            self.logger.error(f"Error getting uncommitted changes: {e}")
            return [], [], [], 0
    
    def get_file_changes(self) -> List[FileChange]:
        """Get detailed information about file changes."""
        file_changes = []
        
        try:
            # Get diffs for modified files
            for item in self.repo.index.diff(None):
                try:
                    file_path = item.a_path
                    change_type = 'modified'
                    
                    # Try to get line counts from diff
                    lines_added = 0
                    lines_removed = 0
                    
                    if item.diff:
                        diff_text = item.diff.decode('utf-8', errors='ignore')
                        for line in diff_text.split('\n'):
                            if line.startswith('+') and not line.startswith('+++'):
                                lines_added += 1
                            elif line.startswith('-') and not line.startswith('---'):
                                lines_removed += 1
                    
                    # Get file modification time
                    full_path = os.path.join(self.repo_path, file_path)
                    last_modified = datetime.now()
                    if os.path.exists(full_path):
                        last_modified = datetime.fromtimestamp(os.path.getmtime(full_path))
                    
                    file_changes.append(FileChange(
                        file_path=file_path,
                        change_type=change_type,
                        lines_added=lines_added,
                        lines_removed=lines_removed,
                        last_modified=last_modified
                    ))
                    
                except Exception as e:
                    self.logger.warning(f"Error processing file change for {item.a_path}: {e}")
                    continue
            
            # Add untracked files
            for file_path in self.repo.untracked_files:
                try:
                    full_path = os.path.join(self.repo_path, file_path)
                    last_modified = datetime.now()
                    if os.path.exists(full_path):
                        last_modified = datetime.fromtimestamp(os.path.getmtime(full_path))
                    
                    file_changes.append(FileChange(
                        file_path=file_path,
                        change_type='added',
                        lines_added=0,  # Could count lines in new files
                        lines_removed=0,
                        last_modified=last_modified
                    ))
                except Exception as e:
                    self.logger.warning(f"Error processing untracked file {file_path}: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error getting file changes: {e}")
        
        return file_changes
    
    def check_remote_connection(self) -> bool:
        """Check if remote repository is accessible."""
        try:
            remotes = list(self.repo.remotes)
            if not remotes:
                return False
            
            # Try to fetch remote info without actually downloading
            remote = remotes[0]
            remote.fetch(dry_run=True)
            return True
            
        except Exception as e:
            self.logger.warning(f"Remote connection check failed: {e}")
            return False
    
    def get_branch_comparison(self, remote_name: str = "origin") -> Dict[str, int]:
        """
        Compare current branch with remote branch.
        
        Returns:
            Dict with 'ahead' and 'behind' counts
        """
        try:
            current_branch = self.get_current_branch()
            remote_branch = f"{remote_name}/{current_branch}"
            
            # Check if remote branch exists
            try:
                self.repo.commit(remote_branch)
            except Exception:
                self.logger.warning(f"Remote branch {remote_branch} not found")
                return {'ahead': 0, 'behind': 0}
            
            # Count commits ahead and behind
            ahead_commits = list(self.repo.iter_commits(f"{remote_branch}..HEAD"))
            behind_commits = list(self.repo.iter_commits(f"HEAD..{remote_branch}"))
            
            return {
                'ahead': len(ahead_commits),
                'behind': len(behind_commits)
            }
            
        except Exception as e:
            self.logger.error(f"Error comparing branches: {e}")
            return {'ahead': 0, 'behind': 0}
    
    def fetch_remote_updates(self, remote_name: str = "origin") -> bool:
        """Fetch updates from remote repository without merging."""
        try:
            remotes = [r for r in self.repo.remotes if r.name == remote_name]
            if not remotes:
                self.logger.warning(f"Remote '{remote_name}' not found")
                return False
            
            remote = remotes[0]
            remote.fetch()
            self.logger.info(f"Successfully fetched updates from {remote_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error fetching remote updates: {e}")
            return False
    
    def get_local_status(self) -> GitStatusResult:
        """
        Get comprehensive local repository status.
        
        Returns:
            GitStatusResult with complete repository information
        """
        try:
            if not self.check_is_git_repository():
                return GitStatusResult(
                    success=False,
                    repository_status=None,
                    error_message="Not a git repository"
                )
            
            # Gather all repository information
            repo_name = self.get_repository_name()
            remote_url = self.get_remote_url()
            current_branch = self.get_current_branch()
            last_commit = self.get_last_commit_info()
            
            modified_files, staged_files, untracked_files, total_changes = self.get_uncommitted_changes()
            file_changes = self.get_file_changes()
            
            # Try to get remote comparison
            branch_comparison = {'ahead': 0, 'behind': 0}
            remote_commit = None
            warnings = []
            
            if self.check_remote_connection():
                # Fetch latest remote info
                if self.fetch_remote_updates():
                    branch_comparison = self.get_branch_comparison()
                    try:
                        remote_commit = self.get_last_commit_info(f"origin/{current_branch}")
                    except Exception:
                        warnings.append("Could not get remote commit information")
                else:
                    warnings.append("Failed to fetch remote updates")
            else:
                warnings.append("No remote connection available")
            
            # Determine if synchronized
            is_synchronized = (
                total_changes == 0 and 
                branch_comparison['ahead'] == 0 and 
                branch_comparison['behind'] == 0
            )
            
            # Create repository status
            repository_status = RepositoryStatus(
                name=repo_name,
                remote_url=remote_url,
                current_branch=current_branch,
                local_commit_sha=last_commit.sha if last_commit else "",
                remote_commit_sha=remote_commit.sha if remote_commit else "",
                uncommitted_changes=total_changes,
                ahead_count=branch_comparison['ahead'],
                behind_count=branch_comparison['behind'],
                is_synchronized=is_synchronized,
                last_sync_time=datetime.now() if is_synchronized else None,
                modified_files=modified_files,
                staged_files=staged_files,
                untracked_files=untracked_files,
                file_changes=file_changes,
                last_commit=last_commit,
                remote_latest_commit=remote_commit
            )
            
            return GitStatusResult(
                success=True,
                repository_status=repository_status,
                warnings=warnings
            )
            
        except Exception as e:
            self.logger.error(f"Error getting local status: {e}")
            return GitStatusResult(
                success=False,
                repository_status=None,
                error_message=str(e)
            )
    
    def execute_git_command(self, command: List[str]) -> Tuple[bool, str]:
        """
        Execute a git command and return result.
        
        Args:
            command: List of command parts (e.g., ['status', '--porcelain'])
            
        Returns:
            Tuple of (success, output)
        """
        try:
            full_command = ['git'] + command
            result = subprocess.run(
                full_command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return result.returncode == 0, result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)