#!/usr/bin/env python3
"""
GitHub Code Status Checker CLI.

Command-line interface for checking GitHub repository status,
comparing local and remote repositories, and generating actionable reports.
"""

import os
import sys
import argparse
import json
import logging
from pathlib import Path
from typing import Optional

from status_reporter import StatusReporter
from models import GitStatusResult


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )


def print_json_output(result: GitStatusResult):
    """Print result in JSON format."""
    print(json.dumps(result.to_dict(), indent=2, default=str))


def print_table_output(reporter: StatusReporter, result: GitStatusResult):
    """Print result in table format."""
    print(reporter.generate_table_format(result))


def print_summary_output(reporter: StatusReporter, result: GitStatusResult):
    """Print result in summary format."""
    print(reporter.format_status_summary(result))


def print_detailed_output(reporter: StatusReporter, result: GitStatusResult):
    """Print result in detailed format."""
    print(reporter.format_detailed_report(result))


def print_actions_output(reporter: StatusReporter, result: GitStatusResult):
    """Print action plan."""
    actions = reporter.get_action_plan(result)
    
    if not actions:
        print("✅ No actions needed - repository is up to date!")
        return
    
    print("📋 Recommended Actions:")
    print("=" * 50)
    
    for i, action in enumerate(actions, 1):
        priority_icon = {
            'high': '🔴',
            'medium': '🟡', 
            'low': '🟢'
        }.get(action.get('priority', 'medium'), '🔵')
        
        print(f"{i}. {priority_icon} {action['description']}")
        print(f"   Command: {action['command']}")
        print()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="GitHub Code Status Checker - Compare local and remote repository status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Basic status check
  %(prog)s --detailed               # Detailed status with file information
  %(prog)s --format json            # JSON output for scripts
  %(prog)s --remote-only            # Check only remote status
  %(prog)s --branch develop         # Check specific branch
  %(prog)s --actions                # Show recommended actions
  %(prog)s --no-github              # Skip GitHub API calls
        """
    )
    
    parser.add_argument(
        '--path', '-p',
        default='.',
        help='Path to git repository (default: current directory)'
    )
    
    parser.add_argument(
        '--format', '-f',
        choices=['summary', 'detailed', 'table', 'json'],
        default='summary',
        help='Output format (default: summary)'
    )
    
    parser.add_argument(
        '--branch', '-b',
        help='Specific branch to check (default: current branch)'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed file-by-file information'
    )
    
    parser.add_argument(
        '--remote-only',
        action='store_true',
        help='Check only remote status without local comparison'
    )
    
    parser.add_argument(
        '--no-github',
        action='store_true',
        help='Skip GitHub API calls (local git only)'
    )
    
    parser.add_argument(
        '--actions',
        action='store_true',
        help='Show recommended actions'
    )
    
    parser.add_argument(
        '--github-token',
        help='GitHub API token (or set GITHUB_TOKEN environment variable)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='GitHub Code Status Checker 1.0.0'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    logger = logging.getLogger(__name__)
    
    try:
        # Validate repository path
        repo_path = Path(args.path).resolve()
        if not repo_path.exists():
            print(f"❌ Error: Path does not exist: {repo_path}", file=sys.stderr)
            sys.exit(1)
        
        if not repo_path.is_dir():
            print(f"❌ Error: Path is not a directory: {repo_path}", file=sys.stderr)
            sys.exit(1)
        
        # Get GitHub token
        github_token = args.github_token or os.getenv('GITHUB_TOKEN')
        if not github_token and not args.no_github:
            logger.warning("No GitHub token provided. Set GITHUB_TOKEN environment variable or use --github-token for authenticated access.")
        
        # Initialize status reporter
        reporter = StatusReporter(str(repo_path), github_token)
        
        # Generate status report
        logger.info(f"Analyzing repository: {repo_path}")
        
        include_github = not args.no_github
        result = reporter.generate_comprehensive_report(include_github=include_github)
        
        if not result.success:
            print(f"❌ Error: {result.error_message}", file=sys.stderr)
            sys.exit(1)
        
        # Handle different output formats
        if args.actions:
            print_actions_output(reporter, result)
        elif args.format == 'json':
            print_json_output(result)
        elif args.format == 'table':
            print_table_output(reporter, result)
        elif args.format == 'detailed' or args.detailed:
            print_detailed_output(reporter, result)
        else:  # summary
            print_summary_output(reporter, result)
        
        # Exit with appropriate code
        if result.repository_status and not result.repository_status.is_synchronized:
            sys.exit(1)  # Non-zero exit for unsynchronized repos
        else:
            sys.exit(0)
    
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user", file=sys.stderr)
        sys.exit(130)
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=args.verbose)
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()