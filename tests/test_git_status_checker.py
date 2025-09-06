#!/usr/bin/env python3
"""
Unit tests for GitHub Code Status Checker.

This module contains comprehensive tests for all components of the
GitHub status checking functionality.
"""

import os
import sys
import unittest
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path

# Add the project root to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import RepositoryStatus, FileChange, CommitInfo, GitStatusResult
from git_analyzer import GitStatusAnalyzer
from github_client import GitHubClient
from status_reporter import StatusReporter


class TestModels(unittest.TestCase):
    """Test data models and their methods."""
    
    def test_file_change_to_dict(self):
        """Test FileChange to_dict conversion."""
        change = FileChange(
            file_path='test.py',
            change_type='modified',
            lines_added=10,
            lines_removed=5,
            last_modified=datetime(2024, 1, 15, 10, 30, 0)
        )
        
        result = change.to_dict()
        
        self.assertEqual(result['file_path'], 'test.py')
        self.assertEqual(result['change_type'], 'modified')
        self.assertEqual(result['lines_added'], 10)
        self.assertEqual(result['lines_removed'], 5)
        self.assertEqual(result['last_modified'], '2024-01-15T10:30:00')
    
    def test_commit_info_to_dict(self):
        """Test CommitInfo to_dict conversion."""
        commit = CommitInfo(
            sha='abc123',
            message='Test commit',
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
            author='Test Author'
        )
        
        result = commit.to_dict()
        
        self.assertEqual(result['sha'], 'abc123')
        self.assertEqual(result['message'], 'Test commit')
        self.assertEqual(result['author'], 'Test Author')
    
    def test_repository_status_sync_status_text(self):
        """Test sync status text generation."""
        # Test up to date
        repo = RepositoryStatus(
            name='test', remote_url='', current_branch='main',
            local_commit_sha='abc', remote_commit_sha='abc',
            uncommitted_changes=0, ahead_count=0, behind_count=0,
            is_synchronized=True, last_sync_time=None,
            modified_files=[], staged_files=[], untracked_files=[],
            file_changes=[]
        )
        self.assertEqual(repo.sync_status_text, "Up to date")
        
        # Test ahead
        repo.ahead_count = 2
        repo.is_synchronized = False
        self.assertEqual(repo.sync_status_text, "Ahead by 2 commits")
        
        # Test behind
        repo.ahead_count = 0
        repo.behind_count = 3
        self.assertEqual(repo.sync_status_text, "Behind by 3 commits")
        
        # Test diverged
        repo.ahead_count = 2
        repo.behind_count = 1
        self.assertEqual(repo.sync_status_text, "Diverged: 2 ahead, 1 behind")


if __name__ == '__main__':
    unittest.main(verbosity=2)