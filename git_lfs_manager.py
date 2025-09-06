#!/usr/bin/env python3
"""
Git LFS Setup and Large File Management Utility

This module provides functionality to detect large files, set up Git LFS,
and manage large file handling in git repositories.
"""

import os
import sys
import subprocess
import logging
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime


class GitLFSManager:
    """Manages Git LFS setup and large file handling."""
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize Git LFS Manager.
        
        Args:
            repo_path: Path to the git repository
        """
        self.repo_path = os.path.abspath(repo_path)
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.default_size_limit_mb = 50
        self.lfs_extensions = {
            'images': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'svg'],
            'videos': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv'],
            'audio': ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma'],
            'archives': ['zip', 'rar', '7z', 'tar', 'gz', 'bz2'],
            'documents': ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'],
            'databases': ['db', 'sqlite', 'sqlite3', 'mdb'],
            'models': ['pkl', 'h5', 'model', 'weights'],
            'data': ['csv', 'json', 'xml', 'parquet']
        }
    
    def check_git_lfs_available(self) -> bool:
        """Check if Git LFS is installed and available."""
        try:
            result = subprocess.run(['git', 'lfs', 'version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False
    
    def install_git_lfs(self) -> Tuple[bool, str]:
        """
        Install Git LFS in the repository.
        
        Returns:
            Tuple of (success, message)
        """
        try:
            if not self.check_git_lfs_available():
                return False, "Git LFS is not installed on this system. Please install Git LFS first."
            
            # Initialize Git LFS in repository
            result = subprocess.run(['git', 'lfs', 'install'], 
                                  cwd=self.repo_path, capture_output=True, text=True)
            
            if result.returncode == 0:
                return True, "Git LFS initialized successfully"
            else:
                return False, f"Failed to initialize Git LFS: {result.stderr}"
                
        except Exception as e:
            return False, f"Error installing Git LFS: {e}"
    
    def find_large_files(self, size_limit_mb: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Find large files in the repository.
        
        Args:
            size_limit_mb: Size limit in megabytes (default: 50MB)
            
        Returns:
            List of dictionaries containing file information
        """
        if size_limit_mb is None:
            size_limit_mb = self.default_size_limit_mb
        
        size_limit_bytes = size_limit_mb * 1024 * 1024
        large_files = []
        
        try:
            for root, dirs, files in os.walk(self.repo_path):
                # Skip .git directory
                if '.git' in dirs:
                    dirs.remove('.git')
                
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        file_size = os.path.getsize(file_path)
                        if file_size > size_limit_bytes:
                            relative_path = os.path.relpath(file_path, self.repo_path)
                            file_ext = Path(file_path).suffix.lower().lstrip('.')
                            
                            # Categorize file type
                            file_category = self._categorize_file(file_ext)
                            
                            large_files.append({
                                'path': relative_path,
                                'size_mb': round(file_size / (1024 * 1024), 2),
                                'size_bytes': file_size,
                                'extension': file_ext,
                                'category': file_category,
                                'lfs_recommended': self._is_lfs_recommended(file_ext, file_category),
                                'gitignore_recommended': self._is_gitignore_recommended(file_ext, file_category)
                            })
                    except OSError:
                        continue
        except Exception as e:
            self.logger.error(f"Error finding large files: {e}")
        
        # Sort by size (largest first)
        large_files.sort(key=lambda x: x['size_bytes'], reverse=True)
        return large_files
    
    def _categorize_file(self, extension: str) -> str:
        """Categorize file by extension."""
        for category, extensions in self.lfs_extensions.items():
            if extension in extensions:
                return category
        return 'other'
    
    def _is_lfs_recommended(self, extension: str, category: str) -> bool:
        """Determine if Git LFS is recommended for this file type."""
        # LFS is recommended for binary files and large data files
        lfs_categories = ['images', 'videos', 'audio', 'archives', 'models', 'databases']
        return category in lfs_categories
    
    def _is_gitignore_recommended(self, extension: str, category: str) -> bool:
        """Determine if .gitignore is recommended for this file type."""
        # Gitignore is recommended for temporary files, logs, and generated content
        gitignore_extensions = ['log', 'tmp', 'temp', 'cache', 'pyc', 'pyo']
        gitignore_categories = ['databases']  # SQLite files often shouldn't be versioned
        
        return extension in gitignore_extensions or category in gitignore_categories
    
    def setup_git_lfs_tracking(self, file_patterns: List[str]) -> Tuple[bool, str]:
        """
        Set up Git LFS tracking for specified file patterns.
        
        Args:
            file_patterns: List of file patterns to track with LFS
            
        Returns:
            Tuple of (success, message)
        """
        try:
            if not self.check_git_lfs_available():
                return False, "Git LFS is not available"
            
            # Initialize LFS if not already done
            install_success, install_message = self.install_git_lfs()
            if not install_success:
                return False, install_message
            
            # Track each pattern
            tracked_patterns = []
            for pattern in file_patterns:
                result = subprocess.run(['git', 'lfs', 'track', pattern], 
                                      cwd=self.repo_path, capture_output=True, text=True)
                if result.returncode == 0:
                    tracked_patterns.append(pattern)
                else:
                    self.logger.warning(f"Failed to track pattern {pattern}: {result.stderr}")
            
            if tracked_patterns:
                # Add .gitattributes to git
                gitattributes_path = os.path.join(self.repo_path, '.gitattributes')
                if os.path.exists(gitattributes_path):
                    result = subprocess.run(['git', 'add', '.gitattributes'], 
                                          cwd=self.repo_path, capture_output=True, text=True)
                    if result.returncode != 0:
                        self.logger.warning(f"Failed to add .gitattributes: {result.stderr}")
                
                return True, f"Successfully tracking {len(tracked_patterns)} patterns with Git LFS"
            else:
                return False, "No patterns were successfully tracked"
                
        except Exception as e:
            return False, f"Error setting up Git LFS tracking: {e}"
    
    def generate_lfs_recommendations(self, large_files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate recommendations for handling large files.
        
        Args:
            large_files: List of large file information
            
        Returns:
            Dictionary with recommendations
        """
        recommendations = {
            'timestamp': datetime.now().isoformat(),
            'total_files': len(large_files),
            'total_size_mb': sum(f['size_mb'] for f in large_files),
            'lfs_recommended': [],
            'gitignore_recommended': [],
            'manual_review': [],
            'patterns_for_lfs': [],
            'patterns_for_gitignore': []
        }
        
        # Categorize files
        for file_info in large_files:
            if file_info['lfs_recommended']:
                recommendations['lfs_recommended'].append(file_info)
            elif file_info['gitignore_recommended']:
                recommendations['gitignore_recommended'].append(file_info)
            else:
                recommendations['manual_review'].append(file_info)
        
        # Generate patterns for LFS
        lfs_extensions = set()
        for file_info in recommendations['lfs_recommended']:
            ext = file_info['extension']
            if ext:
                lfs_extensions.add(f"*.{ext}")
        recommendations['patterns_for_lfs'] = sorted(lfs_extensions)
        
        # Generate patterns for gitignore
        gitignore_extensions = set()
        for file_info in recommendations['gitignore_recommended']:
            ext = file_info['extension']
            if ext:
                gitignore_extensions.add(f"*.{ext}")
            # Also add specific file paths for databases
            if file_info['category'] == 'databases':
                gitignore_extensions.add(file_info['path'])
        recommendations['patterns_for_gitignore'] = sorted(gitignore_extensions)
        
        return recommendations
    
    def apply_lfs_setup(self, recommendations: Dict[str, Any], auto_apply: bool = False) -> Dict[str, Any]:
        """
        Apply LFS setup based on recommendations.
        
        Args:
            recommendations: Recommendations from generate_lfs_recommendations
            auto_apply: Whether to automatically apply without prompts
            
        Returns:
            Dictionary with application results
        """
        results = {
            'success': False,
            'lfs_setup': False,
            'patterns_tracked': [],
            'gitignore_updated': False,
            'patterns_ignored': [],
            'errors': []
        }
        
        try:
            # Set up LFS tracking
            lfs_patterns = recommendations.get('patterns_for_lfs', [])
            if lfs_patterns:
                if auto_apply or self._confirm_action(f"Set up Git LFS tracking for {len(lfs_patterns)} patterns?"):
                    lfs_success, lfs_message = self.setup_git_lfs_tracking(lfs_patterns)
                    if lfs_success:
                        results['lfs_setup'] = True
                        results['patterns_tracked'] = lfs_patterns
                        self.logger.info(lfs_message)
                    else:
                        results['errors'].append(f"LFS setup failed: {lfs_message}")
            
            # Update .gitignore
            gitignore_patterns = recommendations.get('patterns_for_gitignore', [])
            if gitignore_patterns:
                if auto_apply or self._confirm_action(f"Add {len(gitignore_patterns)} patterns to .gitignore?"):
                    gitignore_success = self._update_gitignore(gitignore_patterns)
                    if gitignore_success:
                        results['gitignore_updated'] = True
                        results['patterns_ignored'] = gitignore_patterns
                    else:
                        results['errors'].append("Failed to update .gitignore")
            
            results['success'] = (results['lfs_setup'] or results['gitignore_updated']) and not results['errors']
            
        except Exception as e:
            results['errors'].append(f"Error applying LFS setup: {e}")
        
        return results
    
    def _confirm_action(self, message: str) -> bool:
        """Prompt user for confirmation."""
        response = input(f"{message} (y/N): ").strip().lower()
        return response in ['y', 'yes']
    
    def _update_gitignore(self, patterns: List[str]) -> bool:
        """Update .gitignore with new patterns."""
        try:
            gitignore_path = os.path.join(self.repo_path, '.gitignore')
            
            # Read existing patterns
            existing_patterns = set()
            if os.path.exists(gitignore_path):
                with open(gitignore_path, 'r') as f:
                    existing_patterns = set(line.strip() for line in f.readlines() 
                                          if line.strip() and not line.startswith('#'))
            
            # Filter out existing patterns
            new_patterns = [p for p in patterns if p not in existing_patterns]
            
            if new_patterns:
                with open(gitignore_path, 'a') as f:
                    f.write("\n# Large files auto-excluded\n")
                    for pattern in new_patterns:
                        f.write(f"{pattern}\n")
                
                self.logger.info(f"Added {len(new_patterns)} patterns to .gitignore")
                return True
            else:
                self.logger.info("All patterns already exist in .gitignore")
                return True
                
        except Exception as e:
            self.logger.error(f"Error updating .gitignore: {e}")
            return False
    
    def get_lfs_status(self) -> Dict[str, Any]:
        """Get current Git LFS status."""
        status = {
            'lfs_available': False,
            'lfs_initialized': False,
            'tracked_patterns': [],
            'tracked_files': []
        }
        
        try:
            # Check if LFS is available
            status['lfs_available'] = self.check_git_lfs_available()
            
            if status['lfs_available']:
                # Check if LFS is initialized
                result = subprocess.run(['git', 'lfs', 'track'], 
                                      cwd=self.repo_path, capture_output=True, text=True)
                if result.returncode == 0:
                    status['lfs_initialized'] = True
                    # Parse tracked patterns
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            status['tracked_patterns'].append(line.strip())
                
                # Get tracked files
                result = subprocess.run(['git', 'lfs', 'ls-files'], 
                                      cwd=self.repo_path, capture_output=True, text=True)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            # Parse LFS ls-files output (format: "hash * filename")
                            parts = line.split(' * ')
                            if len(parts) >= 2:
                                status['tracked_files'].append(parts[1])
        
        except Exception as e:
            self.logger.error(f"Error getting LFS status: {e}")
        
        return status


def main():
    """CLI interface for Git LFS Manager."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Git LFS Setup and Large File Management Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python git_lfs_manager.py scan                    # Scan for large files
  python git_lfs_manager.py setup --auto           # Auto-setup LFS
  python git_lfs_manager.py status                 # Show LFS status
  python git_lfs_manager.py track "*.pdf"          # Track PDF files with LFS
        """
    )
    
    parser.add_argument(
        'action',
        choices=['scan', 'setup', 'status', 'track'],
        help='Action to perform'
    )
    
    parser.add_argument(
        '--path', '-p',
        default='.',
        help='Path to git repository (default: current directory)'
    )
    
    parser.add_argument(
        '--size-limit',
        type=int,
        default=50,
        help='Size limit in MB for large file detection (default: 50)'
    )
    
    parser.add_argument(
        '--auto',
        action='store_true',
        help='Automatically apply recommendations without prompts'
    )
    
    parser.add_argument(
        '--pattern',
        action='append',
        help='File pattern to track with LFS (can be used multiple times)'
    )
    
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
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
        # Initialize LFS manager
        lfs_manager = GitLFSManager(args.path)
        
        if args.action == 'scan':
            # Scan for large files
            large_files = lfs_manager.find_large_files(args.size_limit)
            
            if args.format == 'json':
                print(json.dumps(large_files, indent=2))
            else:
                if large_files:
                    print(f"\n📁 Found {len(large_files)} large files (>{args.size_limit}MB):")
                    print("="*80)
                    
                    total_size = sum(f['size_mb'] for f in large_files)
                    print(f"Total size: {total_size:.2f} MB\n")
                    
                    for file_info in large_files:
                        lfs_icon = "🔄" if file_info['lfs_recommended'] else ""
                        ignore_icon = "🚫" if file_info['gitignore_recommended'] else ""
                        
                        print(f"{lfs_icon}{ignore_icon} {file_info['path']}")
                        print(f"   Size: {file_info['size_mb']:.2f} MB | Category: {file_info['category']}")
                        
                        if file_info['lfs_recommended']:
                            print("   ✅ Recommended for Git LFS")
                        elif file_info['gitignore_recommended']:
                            print("   ✅ Recommended for .gitignore")
                        else:
                            print("   ⚠️  Manual review recommended")
                        print()
                else:
                    print(f"✅ No large files found (>{args.size_limit}MB)")
        
        elif args.action == 'setup':
            # Set up LFS based on recommendations
            large_files = lfs_manager.find_large_files(args.size_limit)
            recommendations = lfs_manager.generate_lfs_recommendations(large_files)
            
            if args.format == 'json':
                print(json.dumps(recommendations, indent=2))
            else:
                print("\n🔧 LFS Setup Recommendations:")
                print("="*50)
                
                if recommendations['lfs_recommended']:
                    print(f"\n📦 {len(recommendations['lfs_recommended'])} files recommended for Git LFS:")
                    for file_info in recommendations['lfs_recommended'][:5]:  # Show first 5
                        print(f"   • {file_info['path']} ({file_info['size_mb']:.2f} MB)")
                    if len(recommendations['lfs_recommended']) > 5:
                        print(f"   ... and {len(recommendations['lfs_recommended']) - 5} more")
                
                if recommendations['gitignore_recommended']:
                    print(f"\n🚫 {len(recommendations['gitignore_recommended'])} files recommended for .gitignore:")
                    for file_info in recommendations['gitignore_recommended'][:5]:
                        print(f"   • {file_info['path']} ({file_info['size_mb']:.2f} MB)")
                    if len(recommendations['gitignore_recommended']) > 5:
                        print(f"   ... and {len(recommendations['gitignore_recommended']) - 5} more")
            
            # Apply setup
            if recommendations['patterns_for_lfs'] or recommendations['patterns_for_gitignore']:
                results = lfs_manager.apply_lfs_setup(recommendations, args.auto)
                
                if args.format == 'json':
                    print(json.dumps(results, indent=2))
                else:
                    if results['success']:
                        print("\n✅ LFS setup completed successfully!")
                        if results['lfs_setup']:
                            print(f"   🔄 Git LFS tracking enabled for {len(results['patterns_tracked'])} patterns")
                        if results['gitignore_updated']:
                            print(f"   🚫 .gitignore updated with {len(results['patterns_ignored'])} patterns")
                    else:
                        print("\n❌ LFS setup failed:")
                        for error in results['errors']:
                            print(f"   • {error}")
        
        elif args.action == 'status':
            # Show LFS status
            status = lfs_manager.get_lfs_status()
            
            if args.format == 'json':
                print(json.dumps(status, indent=2))
            else:
                print("\n📊 Git LFS Status:")
                print("="*30)
                
                print(f"LFS Available: {'✅' if status['lfs_available'] else '❌'}")
                print(f"LFS Initialized: {'✅' if status['lfs_initialized'] else '❌'}")
                
                if status['tracked_patterns']:
                    print(f"\n🔄 Tracked Patterns ({len(status['tracked_patterns'])}):")
                    for pattern in status['tracked_patterns']:
                        print(f"   • {pattern}")
                
                if status['tracked_files']:
                    print(f"\n📁 Tracked Files ({len(status['tracked_files'])}):")
                    for file_path in status['tracked_files'][:10]:  # Show first 10
                        print(f"   • {file_path}")
                    if len(status['tracked_files']) > 10:
                        print(f"   ... and {len(status['tracked_files']) - 10} more")
        
        elif args.action == 'track':
            # Track specific patterns
            if not args.pattern:
                print("❌ Error: --pattern is required for track action")
                sys.exit(1)
            
            success, message = lfs_manager.setup_git_lfs_tracking(args.pattern)
            
            if success:
                print(f"✅ {message}")
                print(f"📁 Tracking patterns: {', '.join(args.pattern)}")
            else:
                print(f"❌ Failed to set up tracking: {message}")
                sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()