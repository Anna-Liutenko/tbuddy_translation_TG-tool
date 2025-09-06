#!/usr/bin/env python3
"""
Automated Git Push Issue Resolver

This module provides functionality to automatically diagnose and resolve
common git push issues, using the existing repository diagnostic tools.
"""

import os
import sys
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime

from git_analyzer import GitStatusAnalyzer
from status_reporter import StatusReporter


class GitPushResolver:
    """Automated resolver for common git push issues."""
    
    def __init__(self, repo_path: str = ".", github_token: Optional[str] = None):
        """
        Initialize Git Push Issue Resolver.
        
        Args:
            repo_path: Path to the git repository
            github_token: GitHub API token for enhanced diagnostics
        """
        self.repo_path = os.path.abspath(repo_path)
        self.git_analyzer = GitStatusAnalyzer(repo_path)
        self.status_reporter = StatusReporter(repo_path, github_token)
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.auto_fix_enabled = True
        self.backup_enabled = True
        self.max_file_size_mb = 50
        
    def resolve_git_push_issues(self, auto_fix: bool = True, create_backup: bool = True) -> Dict[str, Any]:
        """
        Main resolution workflow for git push issues.
        
        Args:
            auto_fix: Whether to automatically apply fixes
            create_backup: Whether to create backup before fixes
            
        Returns:
            Dictionary with resolution results
        """
        self.auto_fix_enabled = auto_fix
        self.backup_enabled = create_backup
        
        result = {
            'success': False,
            'timestamp': datetime.now().isoformat(),
            'issues_found': [],
            'actions_taken': [],
            'backup_created': False,
            'push_attempted': False,
            'push_successful': False,
            'error_message': None,
            'recommendations': []
        }
        
        try:
            self.logger.info("Starting git push issue resolution...")
            
            # 1. Diagnostic Phase
            diagnosis = self._run_comprehensive_diagnosis()
            result['issues_found'] = diagnosis.get('issues', [])
            
            if not diagnosis.get('issues'):
                self.logger.info("No issues detected, attempting direct push...")
                return self._attempt_push(result)
            
            # 2. Create backup if requested
            if self.backup_enabled:
                backup_path = self._create_backup()
                if backup_path:
                    result['backup_created'] = True
                    result['backup_path'] = backup_path
                    self.logger.info(f"Backup created at: {backup_path}")
            
            # 3. Apply automated fixes
            if self.auto_fix_enabled:
                fix_results = self._apply_automated_fixes(diagnosis)
                result['actions_taken'] = fix_results
            
            # 4. Attempt push
            return self._attempt_push(result)
            
        except Exception as e:
            self.logger.error(f"Error during resolution: {e}")
            result['error_message'] = str(e)
            return result
    
    def _run_comprehensive_diagnosis(self) -> Dict[str, Any]:
        """Run comprehensive diagnosis using existing tools."""
        try:
            # Use enhanced git analyzer for detailed diagnosis
            diagnosis = self.git_analyzer.diagnose_push_issues()
            
            # Enhance with status reporter information
            status_result = self.status_reporter.generate_comprehensive_report()
            if status_result.success:
                diagnosis['status_report'] = status_result.repository_status
                diagnosis['action_plan'] = self.status_reporter.get_action_plan(status_result)
            
            return diagnosis
            
        except Exception as e:
            self.logger.error(f"Error during diagnosis: {e}")
            return {'issues': [{'type': 'diagnosis_failed', 'message': str(e)}]}
    
    def _create_backup(self) -> Optional[str]:
        """Create backup of current repository state."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f".git_backup_{timestamp}"
            backup_path = os.path.join(self.repo_path, backup_dir)
            
            # Create backup directory
            os.makedirs(backup_path, exist_ok=True)
            
            # Backup important files and git state
            files_to_backup = [
                '.git/index',
                '.git/HEAD',
                '.git/refs',
                '.git/logs'
            ]
            
            for file_path in files_to_backup:
                src = os.path.join(self.repo_path, file_path)
                if os.path.exists(src):
                    dst = os.path.join(backup_path, file_path)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dst)
            
            # Save current git status
            status_file = os.path.join(backup_path, "git_status.txt")
            success, output = self.git_analyzer.execute_git_command(['status', '--porcelain'])
            if success:
                with open(status_file, 'w') as f:
                    f.write(f"Git status at {datetime.now()}:\n")
                    f.write(output)
            
            return backup_path
            
        except Exception as e:
            self.logger.error(f"Failed to create backup: {e}")
            return None
    
    def _apply_automated_fixes(self, diagnosis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Apply automated fixes based on diagnosis."""
        actions_taken = []
        
        try:
            issues = diagnosis.get('issues', [])
            
            for issue in issues:
                action = self._fix_issue(issue)
                if action:
                    actions_taken.append(action)
            
            # Apply file-specific fixes
            self._fix_problematic_files(diagnosis, actions_taken)
            self._fix_large_files(diagnosis, actions_taken)
            
        except Exception as e:
            self.logger.error(f"Error applying automated fixes: {e}")
            actions_taken.append({
                'action': 'fix_failed',
                'description': f'Failed to apply fixes: {e}',
                'success': False
            })
        
        return actions_taken
    
    def _fix_issue(self, issue: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """Fix a specific issue type."""
        issue_type = issue.get('type')
        
        try:
            if issue_type == 'behind_remote':
                return self._fix_behind_remote()
            elif issue_type == 'divergent_branches':
                return self._fix_divergent_branches()
            elif issue_type.startswith('problematic_'):
                return None  # Handled separately
            elif issue_type == 'large_files':
                return None  # Handled separately
            else:
                self.logger.warning(f"No automated fix available for issue type: {issue_type}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to fix issue {issue_type}: {e}")
            return {
                'action': f'fix_{issue_type}',
                'description': f'Failed to fix {issue_type}: {e}',
                'success': False
            }
    
    def _fix_behind_remote(self) -> Dict[str, str]:
        """Fix when local branch is behind remote."""
        try:
            # Check if there are uncommitted changes
            _, _, _, total_changes = self.git_analyzer.get_uncommitted_changes()
            
            if total_changes > 0:
                # Stash changes first
                success, output = self.git_analyzer.execute_git_command(['stash', 'save', 'Auto-stash before pull'])
                if not success:
                    return {
                        'action': 'stash_failed',
                        'description': f'Failed to stash changes: {output}',
                        'success': False
                    }
                
                # Pull changes
                success, output = self.git_analyzer.execute_git_command(['pull'])
                if success:
                    # Pop stash
                    self.git_analyzer.execute_git_command(['stash', 'pop'])
                    return {
                        'action': 'pull_with_stash',
                        'description': 'Successfully pulled remote changes and restored local changes',
                        'success': True
                    }
                else:
                    return {
                        'action': 'pull_failed',
                        'description': f'Failed to pull: {output}',
                        'success': False
                    }
            else:
                # Simple pull without stashing
                success, output = self.git_analyzer.execute_git_command(['pull'])
                return {
                    'action': 'pull',
                    'description': 'Successfully pulled remote changes' if success else f'Failed to pull: {output}',
                    'success': success
                }
                
        except Exception as e:
            return {
                'action': 'pull_error',
                'description': f'Error during pull operation: {e}',
                'success': False
            }
    
    def _fix_divergent_branches(self) -> Dict[str, str]:
        """Fix when branches have diverged."""
        try:
            # For safety, we'll recommend manual intervention for divergent branches
            return {
                'action': 'divergent_manual',
                'description': 'Divergent branches detected - manual intervention recommended (rebase or merge)',
                'success': False,
                'manual_action': True
            }
            
        except Exception as e:
            return {
                'action': 'divergent_error',
                'description': f'Error handling divergent branches: {e}',
                'success': False
            }
    
    def _fix_problematic_files(self, diagnosis: Dict[str, Any], actions_taken: List[Dict[str, str]]):
        """Fix problematic files by creating/updating .gitignore."""
        problematic_files = diagnosis.get('problematic_files', {})
        
        if not any(files for files in problematic_files.values()):
            return
        
        try:
            gitignore_path = os.path.join(self.repo_path, '.gitignore')
            
            # Read existing .gitignore
            existing_patterns = set()
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r') as f:
                    existing_patterns = set(line.strip() for line in f.readlines() if line.strip() and not line.startswith('#'))
            
            # Define patterns to add
            patterns_to_add = []
            
            if problematic_files.get('cache_files'):
                cache_patterns = ['__pycache__/', '*.pyc', '*.pyo', '*.pyd', '.cache/', 'node_modules/']
                patterns_to_add.extend([p for p in cache_patterns if p not in existing_patterns])
            
            if problematic_files.get('log_files'):
                log_patterns = ['*.log', 'logs/', 'run.log']
                patterns_to_add.extend([p for p in log_patterns if p not in existing_patterns])
            
            if problematic_files.get('env_files'):
                env_patterns = ['.env', '.env.local', '.env.production', '.env.staging', '.venv/', 'venv/']
                patterns_to_add.extend([p for p in env_patterns if p not in existing_patterns])
            
            if problematic_files.get('db_files'):
                db_patterns = ['*.db', '*.sqlite', '*.sqlite3']
                patterns_to_add.extend([p for p in db_patterns if p not in existing_patterns])
            
            if problematic_files.get('temp_files'):
                temp_patterns = ['*.tmp', '*.temp', '*~', '*.swp', '*.swo']
                patterns_to_add.extend([p for p in temp_patterns if p not in existing_patterns])
            
            if patterns_to_add:
                # Append new patterns to .gitignore
                with open(gitignore_path, 'a') as f:
                    f.write("\n# Auto-generated patterns to prevent problematic files\n")
                    for pattern in patterns_to_add:
                        f.write(f"{pattern}\n")
                
                # Remove problematic files from staging area
                for category, files in problematic_files.items():
                    for file_path in files:
                        self.git_analyzer.execute_git_command(['reset', 'HEAD', file_path])
                
                actions_taken.append({
                    'action': 'update_gitignore',
                    'description': f'Updated .gitignore with {len(patterns_to_add)} new patterns',
                    'success': True,
                    'patterns_added': patterns_to_add
                })
            
        except Exception as e:
            actions_taken.append({
                'action': 'gitignore_update_failed',
                'description': f'Failed to update .gitignore: {e}',
                'success': False
            })
    
    def _fix_large_files(self, diagnosis: Dict[str, Any], actions_taken: List[Dict[str, str]]):
        """Handle large files by suggesting Git LFS or .gitignore."""
        large_files = diagnosis.get('large_files', [])
        
        if not large_files:
            return
        
        try:
            gitignore_path = os.path.join(self.repo_path, '.gitignore')
            
            # Add large files to .gitignore as a safe default
            with open(gitignore_path, 'a') as f:
                f.write("\n# Large files auto-excluded\n")
                for file_path, size_mb in large_files:
                    f.write(f"{file_path}\n")
                    # Remove from staging if present
                    self.git_analyzer.execute_git_command(['reset', 'HEAD', file_path])
            
            actions_taken.append({
                'action': 'exclude_large_files',
                'description': f'Added {len(large_files)} large files to .gitignore',
                'success': True,
                'files_excluded': large_files,
                'recommendation': 'Consider using Git LFS for version control of large files'
            })
            
        except Exception as e:
            actions_taken.append({
                'action': 'large_files_fix_failed',
                'description': f'Failed to handle large files: {e}',
                'success': False
            })
    
    def _attempt_push(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Attempt to push changes to remote repository."""
        try:
            result['push_attempted'] = True
            
            # Get current branch
            current_branch = self.git_analyzer.get_current_branch()
            
            # Attempt push
            success, output = self.git_analyzer.execute_git_command(['push', 'origin', current_branch])
            
            result['push_successful'] = success
            result['success'] = success
            
            if success:
                self.logger.info("Git push successful!")
                result['message'] = "Git push completed successfully"
            else:
                self.logger.error(f"Git push failed: {output}")
                result['error_message'] = output
                result['recommendations'] = self._generate_push_failure_recommendations(output)
            
        except Exception as e:
            self.logger.error(f"Error during push attempt: {e}")
            result['error_message'] = str(e)
            result['push_successful'] = False
            result['success'] = False
        
        return result
    
    def _generate_push_failure_recommendations(self, error_output: str) -> List[str]:
        """Generate recommendations based on push failure output."""
        recommendations = []
        
        if "authentication" in error_output.lower() or "permission denied" in error_output.lower():
            recommendations.extend([
                "Check GitHub authentication (token or SSH key)",
                "Verify repository permissions",
                "Test connection with: ssh -T git@github.com"
            ])
        
        if "non-fast-forward" in error_output.lower():
            recommendations.extend([
                "Remote has newer commits than local",
                "Pull remote changes before pushing",
                "Consider using 'git pull --rebase' to avoid merge commits"
            ])
        
        if "large file" in error_output.lower() or "file size" in error_output.lower():
            recommendations.extend([
                "Repository contains large files",
                "Consider using Git LFS for large files",
                "Add large files to .gitignore if not needed in version control"
            ])
        
        if "hook" in error_output.lower():
            recommendations.extend([
                "Pre-push hook is blocking the push",
                "Check repository hooks and fix any issues",
                "Contact repository administrator if needed"
            ])
        
        if not recommendations:
            recommendations.append("Manual intervention required - check git push output for specific error")
        
        return recommendations


def main():
    """CLI interface for Git Push Issue Resolver."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Automated Git Push Issue Resolver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python git_push_resolver.py                    # Full automated resolution
  python git_push_resolver.py --no-auto-fix     # Diagnosis only
  python git_push_resolver.py --no-backup       # Skip backup creation
  python git_push_resolver.py --verbose         # Detailed logging
        """
    )
    
    parser.add_argument(
        '--path', '-p',
        default='.',
        help='Path to git repository (default: current directory)'
    )
    
    parser.add_argument(
        '--no-auto-fix',
        action='store_true',
        help='Disable automatic fixes (diagnosis only)'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup creation'
    )
    
    parser.add_argument(
        '--github-token',
        help='GitHub API token for enhanced diagnostics'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    try:
        # Initialize resolver
        github_token = args.github_token or os.getenv('GITHUB_TOKEN')
        resolver = GitPushResolver(args.path, github_token)
        
        # Run resolution
        result = resolver.resolve_git_push_issues(
            auto_fix=not args.no_auto_fix,
            create_backup=not args.no_backup
        )
        
        # Print results
        print("\n" + "="*60)
        print("GIT PUSH ISSUE RESOLUTION RESULTS")
        print("="*60)
        
        if result['success']:
            print("✅ Resolution completed successfully!")
            if result['push_successful']:
                print("🚀 Git push was successful!")
        else:
            print("❌ Resolution failed")
        
        if result['issues_found']:
            print(f"\n📋 Issues found: {len(result['issues_found'])}")
            for issue in result['issues_found']:
                print(f"   • {issue.get('message', 'Unknown issue')}")
        
        if result['actions_taken']:
            print(f"\n🔧 Actions taken: {len(result['actions_taken'])}")
            for action in result['actions_taken']:
                status = "✅" if action.get('success') else "❌"
                print(f"   {status} {action.get('description', 'Unknown action')}")
        
        if result.get('backup_created'):
            print(f"\n💾 Backup created at: {result.get('backup_path')}")
        
        if result.get('recommendations'):
            print("\n💡 Recommendations:")
            for rec in result['recommendations']:
                print(f"   • {rec}")
        
        if result.get('error_message'):
            print(f"\n❌ Error: {result['error_message']}")
        
        # Exit with appropriate code
        sys.exit(0 if result['success'] else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()