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
    
    def check_large_files(self, size_limit_mb: int = 50) -> List[Tuple[str, int]]:
        """
        Check for large files that might cause push issues.
        
        Args:
            size_limit_mb: Size limit in megabytes
            
        Returns:
            List of (file_path, size_in_mb) tuples for files exceeding limit
        """
        large_files = []
        size_limit_bytes = size_limit_mb * 1024 * 1024
        
        try:
            for root, dirs, files in os.walk(self.repo_path):
                # Skip .git directory
                if '.git' in dirs:
                    dirs.remove('.git')
                
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        if os.path.getsize(file_path) > size_limit_bytes:
                            relative_path = os.path.relpath(file_path, self.repo_path)
                            size_mb = os.path.getsize(file_path) / (1024 * 1024)
                            large_files.append((relative_path, round(size_mb, 2)))
                    except OSError:
                        continue
        except Exception as e:
            self.logger.error(f"Error checking large files: {e}")
        
        return large_files
    
    def check_problematic_files(self) -> Dict[str, List[str]]:
        """
        Check for files that shouldn't be committed.
        
        Returns:
            Dictionary with categories of problematic files
        """
        problematic = {
            'cache_files': [],
            'log_files': [],
            'env_files': [],
            'db_files': [],
            'temp_files': []
        }
        
        # Patterns for problematic files
        patterns = {
            'cache_files': ['__pycache__', '.pyc', '.pyo', '.pyd', 'node_modules', '.cache'],
            'log_files': ['.log', 'logs/', 'run.log'],
            'env_files': ['.env', '.env.local', '.env.production', '.env.staging'],
            'db_files': ['.db', '.sqlite', '.sqlite3'],
            'temp_files': ['.tmp', '.temp', '~', '.swp', '.swo']
        }
        
        try:
            # Check staged and untracked files
            all_files = []
            modified_files, staged_files, untracked_files, _ = self.get_uncommitted_changes()
            all_files.extend(staged_files)
            all_files.extend(untracked_files)
            
            for file_path in all_files:
                for category, file_patterns in patterns.items():
                    for pattern in file_patterns:
                        if pattern in file_path:
                            problematic[category].append(file_path)
                            break
        except Exception as e:
            self.logger.error(f"Error checking problematic files: {e}")
        
        return problematic
    
    def diagnose_push_issues(self) -> Dict[str, Any]:
        """
        Comprehensive diagnosis of potential git push issues.
        
        Returns:
            Dictionary containing all diagnostic information
        """
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'repository_path': self.repo_path,
            'issues': [],
            'recommendations': [],
            'large_files': [],
            'problematic_files': {},
            'remote_status': 'unknown',
            'branch_status': {}
        }
        
        try:
            # Check if it's a git repository
            if not self.check_is_git_repository():
                diagnosis['issues'].append({
                    'type': 'not_git_repo',
                    'severity': 'critical',
                    'message': 'Not a git repository',
                    'solution': 'Initialize git repository with "git init"'
                })
                return diagnosis
            
            # Check remote connection
            has_remote = self.check_remote_connection()
            diagnosis['remote_status'] = 'connected' if has_remote else 'disconnected'
            
            if not has_remote:
                diagnosis['issues'].append({
                    'type': 'no_remote',
                    'severity': 'high',
                    'message': 'No remote repository connection',
                    'solution': 'Add remote repository or check network connection'
                })
            
            # Check for large files
            large_files = self.check_large_files()
            diagnosis['large_files'] = large_files
            
            if large_files:
                diagnosis['issues'].append({
                    'type': 'large_files',
                    'severity': 'medium',
                    'message': f'Found {len(large_files)} files larger than 50MB',
                    'solution': 'Use Git LFS for large files or add to .gitignore',
                    'files': large_files
                })
            
            # Check for problematic files
            problematic_files = self.check_problematic_files()
            diagnosis['problematic_files'] = problematic_files
            
            for category, files in problematic_files.items():
                if files:
                    diagnosis['issues'].append({
                        'type': f'problematic_{category}',
                        'severity': 'medium',
                        'message': f'Found {len(files)} {category.replace("_", " ")} that should not be committed',
                        'solution': f'Add {category.replace("_", " ")} to .gitignore',
                        'files': files
                    })
            
            # Check branch status
            branch_comparison = self.get_branch_comparison()
            diagnosis['branch_status'] = branch_comparison
            
            if branch_comparison['behind'] > 0:
                diagnosis['issues'].append({
                    'type': 'behind_remote',
                    'severity': 'high',
                    'message': f'Local branch is {branch_comparison["behind"]} commits behind remote',
                    'solution': 'Pull remote changes before pushing'
                })
            
            if branch_comparison['ahead'] > 0 and branch_comparison['behind'] > 0:
                diagnosis['issues'].append({
                    'type': 'divergent_branches',
                    'severity': 'high',
                    'message': 'Local and remote branches have diverged',
                    'solution': 'Rebase or merge remote changes before pushing'
                })
            
            # Generate recommendations
            diagnosis['recommendations'] = self._generate_recommendations(diagnosis)
            
        except Exception as e:
            self.logger.error(f"Error during push issue diagnosis: {e}")
            diagnosis['issues'].append({
                'type': 'diagnosis_error',
                'severity': 'critical',
                'message': f'Error during diagnosis: {e}',
                'solution': 'Check repository state manually'
            })
        
        return diagnosis
    
    def _generate_recommendations(self, diagnosis: Dict[str, Any]) -> List[str]:
        """
        Generate actionable recommendations based on diagnosis.
        
        Args:
            diagnosis: Diagnosis results
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        # Sort issues by severity
        issues = diagnosis.get('issues', [])
        critical_issues = [i for i in issues if i['severity'] == 'critical']
        high_issues = [i for i in issues if i['severity'] == 'high']
        
        if critical_issues:
            recommendations.append("🔴 CRITICAL: Address critical issues first before attempting push")
            for issue in critical_issues:
                recommendations.append(f"   • {issue['solution']}")
        
        if high_issues:
            recommendations.append("🟡 HIGH PRIORITY: Resolve these issues before pushing")
            for issue in high_issues:
                recommendations.append(f"   • {issue['solution']}")
        
        # Add specific file handling recommendations
        if diagnosis.get('large_files'):
            recommendations.append("📁 Large files detected - consider Git LFS or .gitignore")
        
        problematic = diagnosis.get('problematic_files', {})
        if any(files for files in problematic.values()):
            recommendations.append("🚫 Problematic files detected - create/update .gitignore")
        
        if not recommendations:
            recommendations.append("✅ No major issues detected - repository appears ready for push")
        
        return recommendations
    
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