"""
GitHub API Client for GitHub Code Status Checker.

This module provides functionality to interact with the GitHub API
to retrieve remote repository information and compare with local state.
"""

import os
import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple, Any
from urllib.parse import urlparse
from github import Github, GithubException
from github.Repository import Repository
from github.Commit import Commit
from models import CommitInfo, GitStatusResult


class GitHubClient:
    """Client for interacting with GitHub API."""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub API token. If None, will try to get from environment.
        """
        self.token = token or os.getenv('GITHUB_TOKEN')
        self.logger = logging.getLogger(__name__)
        self._github = None
        
    @property
    def github(self) -> Github:
        """Get GitHub API instance, creating if needed."""
        if self._github is None:
            if self.token:
                self._github = Github(self.token)
            else:
                # Use unauthenticated access (rate limited)
                self._github = Github()
                self.logger.warning("Using unauthenticated GitHub API access (rate limited)")
        return self._github
    
    def parse_github_url(self, remote_url: str) -> Optional[Tuple[str, str]]:
        """
        Parse GitHub repository URL to extract owner and repo name.
        
        Args:
            remote_url: Git remote URL (HTTPS or SSH)
            
        Returns:
            Tuple of (owner, repo) or None if not a GitHub URL
        """
        if not remote_url:
            return None
        
        # Handle different URL formats
        patterns = [
            r'github\.com[:/]([^/]+)/([^/\.]+)(?:\.git)?',  # HTTPS or SSH
            r'github\.com/([^/]+)/([^/\.]+)',  # HTTPS without .git
        ]
        
        for pattern in patterns:
            match = re.search(pattern, remote_url)
            if match:
                owner, repo = match.groups()
                return owner, repo
        
        return None
    
    def get_repository(self, remote_url: str) -> Optional[Repository]:
        """
        Get GitHub repository object from remote URL.
        
        Args:
            remote_url: Git remote URL
            
        Returns:
            GitHub Repository object or None if not found
        """
        try:
            parsed = self.parse_github_url(remote_url)
            if not parsed:
                self.logger.warning(f"Could not parse GitHub URL: {remote_url}")
                return None
            
            owner, repo_name = parsed
            return self.github.get_repo(f"{owner}/{repo_name}")
            
        except GithubException as e:
            self.logger.error(f"GitHub API error getting repository: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting repository: {e}")
            return None
    
    def get_latest_commit(self, repo: Repository, branch: str = "main") -> Optional[CommitInfo]:
        """
        Get latest commit information from a branch.
        
        Args:
            repo: GitHub Repository object
            branch: Branch name to check
            
        Returns:
            CommitInfo object or None if not found
        """
        try:
            # Try the specified branch first
            try:
                commits = repo.get_commits(sha=branch)
                latest_commit = commits[0]
            except GithubException:
                # If branch doesn't exist, try default branch
                try:
                    commits = repo.get_commits()
                    latest_commit = commits[0]
                except GithubException as e:
                    self.logger.error(f"Could not get commits: {e}")
                    return None
            
            return CommitInfo(
                sha=latest_commit.sha[:8],
                message=latest_commit.commit.message.strip(),
                timestamp=latest_commit.commit.author.date,
                author=latest_commit.commit.author.name
            )
            
        except Exception as e:
            self.logger.error(f"Error getting latest commit: {e}")
            return None
    
    def get_branch_comparison(self, repo: Repository, base_branch: str, head_branch: str) -> Dict[str, int]:
        """
        Compare two branches to get ahead/behind counts.
        
        Args:
            repo: GitHub Repository object
            base_branch: Base branch name (usually remote)
            head_branch: Head branch name (usually local)
            
        Returns:
            Dict with 'ahead' and 'behind' counts
        """
        try:
            comparison = repo.compare(base_branch, head_branch)
            return {
                'ahead': comparison.ahead_by,
                'behind': comparison.behind_by
            }
            
        except GithubException as e:
            self.logger.error(f"Error comparing branches: {e}")
            return {'ahead': 0, 'behind': 0}
        except Exception as e:
            self.logger.error(f"Error in branch comparison: {e}")
            return {'ahead': 0, 'behind': 0}
    
    def get_commit_history(self, repo: Repository, branch: str = None, limit: int = 10) -> List[CommitInfo]:
        """
        Get recent commit history.
        
        Args:
            repo: GitHub Repository object
            branch: Branch name (None for default)
            limit: Maximum number of commits to retrieve
            
        Returns:
            List of CommitInfo objects
        """
        commits = []
        try:
            if branch:
                github_commits = repo.get_commits(sha=branch)
            else:
                github_commits = repo.get_commits()
            
            for i, commit in enumerate(github_commits):
                if i >= limit:
                    break
                
                commits.append(CommitInfo(
                    sha=commit.sha[:8],
                    message=commit.commit.message.strip(),
                    timestamp=commit.commit.author.date,
                    author=commit.commit.author.name
                ))
                
        except Exception as e:
            self.logger.error(f"Error getting commit history: {e}")
        
        return commits
    
    def get_repository_info(self, remote_url: str, current_branch: str = "main") -> Dict[str, Any]:
        """
        Get comprehensive repository information from GitHub.
        
        Args:
            remote_url: Git remote URL
            current_branch: Current local branch name
            
        Returns:
            Dictionary with repository information
        """
        result = {
            'success': False,
            'repository': None,
            'latest_commit': None,
            'commit_history': [],
            'branch_exists': False,
            'error_message': None
        }
        
        try:
            repo = self.get_repository(remote_url)
            if not repo:
                result['error_message'] = "Repository not found or not accessible"
                return result
            
            result['repository'] = {
                'name': repo.name,
                'full_name': repo.full_name,
                'description': repo.description,
                'default_branch': repo.default_branch,
                'url': repo.html_url,
                'private': repo.private,
                'fork': repo.fork
            }
            
            # Check if the current branch exists on remote
            try:
                repo.get_branch(current_branch)
                result['branch_exists'] = True
                branch_to_check = current_branch
            except GithubException:
                result['branch_exists'] = False
                branch_to_check = repo.default_branch
                self.logger.warning(f"Branch '{current_branch}' not found on remote, using default: {branch_to_check}")
            
            # Get latest commit
            latest_commit = self.get_latest_commit(repo, branch_to_check)
            if latest_commit:
                result['latest_commit'] = latest_commit.to_dict()
            
            # Get commit history
            commit_history = self.get_commit_history(repo, branch_to_check, limit=5)
            result['commit_history'] = [commit.to_dict() for commit in commit_history]
            
            result['success'] = True
            
        except Exception as e:
            result['error_message'] = str(e)
            self.logger.error(f"Error getting repository info: {e}")
        
        return result
    
    def check_rate_limit(self) -> Dict[str, Any]:
        """
        Check GitHub API rate limit status.
        
        Returns:
            Dictionary with rate limit information
        """
        try:
            rate_limit = self.github.get_rate_limit()
            return {
                'core': {
                    'limit': rate_limit.core.limit,
                    'remaining': rate_limit.core.remaining,
                    'reset': rate_limit.core.reset,
                    'used': rate_limit.core.used
                },
                'search': {
                    'limit': rate_limit.search.limit,
                    'remaining': rate_limit.search.remaining,
                    'reset': rate_limit.search.reset,
                    'used': rate_limit.search.used
                }
            }
        except Exception as e:
            self.logger.error(f"Error checking rate limit: {e}")
            return {}
    
    def test_connection(self) -> bool:
        """
        Test GitHub API connection.
        
        Returns:
            True if connection is successful, False otherwise
        """
        try:
            # Try to get authenticated user info or rate limit
            if self.token:
                user = self.github.get_user()
                self.logger.info(f"Connected to GitHub as: {user.login}")
            else:
                rate_limit = self.github.get_rate_limit()
                self.logger.info(f"Connected to GitHub (unauthenticated), rate limit: {rate_limit.core.remaining}")
            return True
            
        except Exception as e:
            self.logger.error(f"GitHub connection test failed: {e}")
            return False
    
    def get_file_content(self, repo: Repository, file_path: str, branch: str = None) -> Optional[str]:
        """
        Get content of a specific file from the repository.
        
        Args:
            repo: GitHub Repository object
            file_path: Path to the file in the repository
            branch: Branch name (None for default)
            
        Returns:
            File content as string or None if not found
        """
        try:
            if branch:
                content = repo.get_contents(file_path, ref=branch)
            else:
                content = repo.get_contents(file_path)
            
            if content.type == 'file':
                return content.decoded_content.decode('utf-8')
            else:
                self.logger.warning(f"Path {file_path} is not a file")
                return None
                
        except GithubException as e:
            if e.status == 404:
                self.logger.info(f"File {file_path} not found in repository")
            else:
                self.logger.error(f"Error getting file content: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Error getting file content: {e}")
            return None