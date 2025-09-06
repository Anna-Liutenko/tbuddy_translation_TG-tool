#!/usr/bin/env python3
"""
Comprehensive Security and Deployment Validation Script
This script validates the entire deployment system with security compliance checks
"""

import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ComprehensiveValidator:
    """Comprehensive security and deployment validation"""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self.validation_results = {
            'timestamp': datetime.now().isoformat(),
            'repo_path': str(self.repo_path),
            'checks': {},
            'overall_status': 'UNKNOWN',
            'critical_issues': 0,
            'high_issues': 0,
            'medium_issues': 0,
            'warnings': 0
        }
        
    def run_command(self, command: List[str], cwd: str = None) -> Dict:
        """Run a command and return the result"""
        try:
            result = subprocess.run(
                command,
                cwd=cwd or self.repo_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                'success': result.returncode == 0,
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': 'Command timed out'
            }
        except Exception as e:
            return {
                'success': False,
                'returncode': -1,
                'stdout': '',
                'stderr': str(e)
            }
    
    def validate_security(self) -> Dict:
        """Run security validation"""
        logger.info("Running security validation...")
        
        security_script = self.repo_path / "security" / "validate_security.py"
        
        if not security_script.exists():
            return {
                'status': 'FAILED',
                'message': 'Security validation script not found',
                'details': {}
            }
        
        # Run security validation
        result = self.run_command([
            sys.executable, str(security_script),
            '--repo-path', str(self.repo_path),
            '--output', str(self.repo_path / 'security_report.json')
        ])
        
        # Load security report if available
        security_report_path = self.repo_path / 'security_report.json'
        security_details = {}
        
        if security_report_path.exists():
            try:
                with open(security_report_path, 'r') as f:
                    security_details = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load security report: {e}")
        
        return {
            'status': 'PASSED' if result['success'] else 'FAILED',
            'message': 'Security validation completed',
            'command_output': result,
            'details': security_details
        }
    
    def validate_git_hooks(self) -> Dict:
        """Validate Git hooks setup"""
        logger.info("Validating Git hooks...")
        
        git_dir = self.repo_path / '.git'
        hooks_dir = git_dir / 'hooks'
        
        if not git_dir.exists():
            return {
                'status': 'SKIPPED',
                'message': 'Not a Git repository',
                'details': {}
            }
        
        # Check for pre-commit hook
        pre_commit_hook = hooks_dir / 'pre-commit'
        security_hook = self.repo_path / 'security' / 'pre_commit_check.sh'
        
        issues = []
        
        if not security_hook.exists():
            issues.append('Security pre-commit script not found')
        
        if not pre_commit_hook.exists():
            issues.append('Pre-commit hook not installed')
        else:
            # Check if hook references security script
            try:
                with open(pre_commit_hook, 'r') as f:
                    hook_content = f.read()
                    if 'pre_commit_check.sh' not in hook_content and 'validate_security.py' not in hook_content:
                        issues.append('Pre-commit hook does not reference security validation')
            except Exception as e:
                issues.append(f'Could not read pre-commit hook: {e}')
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': 'Git hooks validation completed',
            'details': {
                'issues': issues,
                'security_hook_exists': security_hook.exists(),
                'pre_commit_hook_exists': pre_commit_hook.exists()
            }
        }
    
    def validate_environment_templates(self) -> Dict:
        """Validate environment template synchronization"""
        logger.info("Validating environment templates...")
        
        required_templates = [
            '.env.example',
            '.env.production.example',
            '.env.enhanced.example',
            '.env.testing'
        ]
        
        issues = []
        template_details = {}
        
        for template in required_templates:
            template_path = self.repo_path / template
            
            if not template_path.exists():
                issues.append(f'Template missing: {template}')
                template_details[template] = {'exists': False}
                continue
            
            template_details[template] = {'exists': True}
            
            # Check for placeholder values
            try:
                with open(template_path, 'r') as f:
                    content = f.read()
                    
                # Check for required variables
                required_vars = ['TELEGRAM_API_TOKEN', 'DIRECT_LINE_SECRET']
                missing_vars = []
                
                for var in required_vars:
                    if var not in content:
                        missing_vars.append(var)
                
                if missing_vars:
                    issues.append(f'Template {template} missing variables: {", ".join(missing_vars)}')
                
                # Check for placeholder patterns
                placeholder_patterns = ['YOUR_', 'PLACEHOLDER', 'EXAMPLE', 'CHANGE_ME']
                has_placeholders = any(pattern in content for pattern in placeholder_patterns)
                
                if not has_placeholders:
                    issues.append(f'Template {template} may contain real values instead of placeholders')
                
                template_details[template].update({
                    'has_required_vars': not missing_vars,
                    'has_placeholders': has_placeholders,
                    'missing_vars': missing_vars
                })
                
            except Exception as e:
                issues.append(f'Could not validate template {template}: {e}')
                template_details[template]['error'] = str(e)
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': f'Environment templates validation completed ({len(issues)} issues)',
            'details': {
                'issues': issues,
                'templates': template_details
            }
        }
    
    def validate_deployment_files(self) -> Dict:
        """Validate deployment configuration files"""
        logger.info("Validating deployment files...")
        
        required_files = {
            'deploy/tbuddy.service': 'Systemd service file',
            'deploy/tbuddy.nginx.conf': 'Nginx configuration',
            'deploy/secure_deploy.sh': 'Secure deployment script',
            'scripts/health_check.sh': 'Health check script',
            'scripts/rollback.sh': 'Rollback script',
            'scripts/monitor.sh': 'Monitoring script'
        }
        
        issues = []
        file_details = {}
        
        for file_path, description in required_files.items():
            full_path = self.repo_path / file_path
            
            if not full_path.exists():
                issues.append(f'{description} missing: {file_path}')
                file_details[file_path] = {'exists': False}
                continue
            
            file_details[file_path] = {
                'exists': True,
                'size': full_path.stat().st_size,
                'executable': os.access(full_path, os.X_OK)
            }
            
            # Check if shell scripts are executable
            if file_path.endswith('.sh') and not os.access(full_path, os.X_OK):
                issues.append(f'Script not executable: {file_path}')
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': f'Deployment files validation completed ({len(issues)} issues)',
            'details': {
                'issues': issues,
                'files': file_details
            }
        }
    
    def validate_gitignore(self) -> Dict:
        """Validate .gitignore completeness"""
        logger.info("Validating .gitignore...")
        
        gitignore_path = self.repo_path / '.gitignore'
        
        if not gitignore_path.exists():
            return {
                'status': 'FAILED',
                'message': '.gitignore file not found',
                'details': {}
            }
        
        try:
            with open(gitignore_path, 'r') as f:
                gitignore_content = f.read()
        except Exception as e:
            return {
                'status': 'FAILED',
                'message': f'Could not read .gitignore: {e}',
                'details': {}
            }
        
        # Required patterns for security
        required_patterns = [
            '.env',
            '*.db',
            '*.log',
            '__pycache__',
            '.qoder',
            '*.key',
            '*.pem'
        ]
        
        missing_patterns = []
        for pattern in required_patterns:
            if pattern not in gitignore_content:
                missing_patterns.append(pattern)
        
        # Check for dangerous includes
        dangerous_patterns = ['!.env', '!*.key', '!*.pem']
        dangerous_includes = []
        for pattern in dangerous_patterns:
            if pattern in gitignore_content:
                dangerous_includes.append(pattern)
        
        issues = []
        if missing_patterns:
            issues.append(f'Missing security patterns: {", ".join(missing_patterns)}')
        if dangerous_includes:
            issues.append(f'Dangerous include patterns: {", ".join(dangerous_includes)}')
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': f'.gitignore validation completed ({len(issues)} issues)',
            'details': {
                'issues': issues,
                'missing_patterns': missing_patterns,
                'dangerous_includes': dangerous_includes
            }
        }
    
    def validate_documentation(self) -> Dict:
        """Validate documentation completeness"""
        logger.info("Validating documentation...")
        
        required_docs = {
            'README.md': 'Main documentation',
            'DEPLOY.md': 'Deployment instructions',
            'ARCHITECTURE_COMPLIANCE_REPORT.md': 'Architecture compliance',
            'COMPLIANCE_VALIDATION_GUIDE.md': 'Compliance guide'
        }
        
        issues = []
        doc_details = {}
        
        for doc_file, description in required_docs.items():
            doc_path = self.repo_path / doc_file
            
            if not doc_path.exists():
                issues.append(f'{description} missing: {doc_file}')
                doc_details[doc_file] = {'exists': False}
                continue
            
            try:
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                doc_details[doc_file] = {
                    'exists': True,
                    'size': len(content),
                    'lines': len(content.splitlines()),
                    'has_content': len(content.strip()) > 100  # At least 100 characters
                }
                
                if not doc_details[doc_file]['has_content']:
                    issues.append(f'{description} appears to be empty or minimal: {doc_file}')
                    
            except Exception as e:
                issues.append(f'Could not read {doc_file}: {e}')
                doc_details[doc_file] = {'exists': True, 'error': str(e)}
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': f'Documentation validation completed ({len(issues)} issues)',
            'details': {
                'issues': issues,
                'documents': doc_details
            }
        }
    
    def validate_test_framework(self) -> Dict:
        """Validate testing framework"""
        logger.info("Validating test framework...")
        
        test_files = {
            'scripts/deployment_test.py': 'Deployment testing script',
            'comprehensive_test_runner.py': 'Comprehensive test runner',
            'test_utilities.py': 'Test utilities'
        }
        
        issues = []
        test_details = {}
        
        for test_file, description in test_files.items():
            test_path = self.repo_path / test_file
            
            if not test_path.exists():
                issues.append(f'{description} missing: {test_file}')
                test_details[test_file] = {'exists': False}
                continue
            
            test_details[test_file] = {
                'exists': True,
                'size': test_path.stat().st_size,
                'executable': os.access(test_path, os.X_OK) if test_file.endswith('.py') else True
            }
        
        # Check tests directory
        tests_dir = self.repo_path / 'tests'
        if tests_dir.exists():
            test_count = len(list(tests_dir.glob('*.py')))
            test_details['tests_directory'] = {
                'exists': True,
                'test_count': test_count
            }
            
            if test_count == 0:
                issues.append('Tests directory exists but contains no test files')
        else:
            issues.append('Tests directory not found')
            test_details['tests_directory'] = {'exists': False}
        
        return {
            'status': 'PASSED' if not issues else 'FAILED',
            'message': f'Test framework validation completed ({len(issues)} issues)',
            'details': {
                'issues': issues,
                'test_files': test_details
            }
        }
    
    def run_comprehensive_validation(self) -> Dict:
        """Run all validation checks"""
        logger.info("Starting comprehensive validation...")
        
        validation_checks = [
            ('security_validation', self.validate_security),
            ('git_hooks', self.validate_git_hooks),
            ('environment_templates', self.validate_environment_templates),
            ('deployment_files', self.validate_deployment_files),
            ('gitignore_validation', self.validate_gitignore),
            ('documentation', self.validate_documentation),
            ('test_framework', self.validate_test_framework)
        ]
        
        total_issues = 0
        passed_checks = 0
        
        for check_name, check_function in validation_checks:
            logger.info(f"Running {check_name}...")
            
            try:
                result = check_function()
                self.validation_results['checks'][check_name] = result
                
                if result['status'] == 'PASSED':
                    passed_checks += 1
                elif result['status'] == 'FAILED':
                    issue_count = len(result.get('details', {}).get('issues', []))
                    total_issues += issue_count
                
                logger.info(f"{check_name}: {result['status']} - {result['message']}")
                
            except Exception as e:
                logger.error(f"Error running {check_name}: {e}")
                self.validation_results['checks'][check_name] = {
                    'status': 'ERROR',
                    'message': f'Validation error: {e}',
                    'details': {}
                }
                total_issues += 1
        
        # Calculate overall status
        total_checks = len(validation_checks)
        if passed_checks == total_checks:
            self.validation_results['overall_status'] = 'PASSED'
        elif passed_checks >= total_checks * 0.8:  # 80% pass rate
            self.validation_results['overall_status'] = 'WARNING'
        else:
            self.validation_results['overall_status'] = 'FAILED'
        
        self.validation_results.update({
            'total_checks': total_checks,
            'passed_checks': passed_checks,
            'failed_checks': total_checks - passed_checks,
            'total_issues': total_issues
        })
        
        logger.info(f"Comprehensive validation completed: {self.validation_results['overall_status']}")
        
        return self.validation_results
    
    def generate_report(self, output_file: Optional[str] = None) -> str:
        """Generate validation report"""
        report_data = self.validation_results
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            logger.info(f"Validation report saved to {output_file}")
        
        # Generate summary report
        summary = []
        summary.append("=" * 70)
        summary.append("COMPREHENSIVE DEPLOYMENT VALIDATION SUMMARY")
        summary.append("=" * 70)
        summary.append(f"Overall Status: {report_data['overall_status']}")
        summary.append(f"Timestamp: {report_data['timestamp']}")
        summary.append(f"Repository: {report_data['repo_path']}")
        summary.append("")
        summary.append(f"Total Checks: {report_data.get('total_checks', 0)}")
        summary.append(f"Passed: {report_data.get('passed_checks', 0)}")
        summary.append(f"Failed: {report_data.get('failed_checks', 0)}")
        summary.append(f"Total Issues: {report_data.get('total_issues', 0)}")
        summary.append("")
        
        # Check details
        summary.append("CHECK DETAILS:")
        summary.append("-" * 30)
        
        for check_name, result in report_data['checks'].items():
            status = result['status']
            message = result['message']
            summary.append(f"{check_name:25} [{status:8}] {message}")
            
            # Show issues if any
            issues = result.get('details', {}).get('issues', [])
            for issue in issues:
                summary.append(f"  * {issue}")
        
        summary.append("")
        summary.append("=" * 70)
        
        return "\n".join(summary)

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Comprehensive deployment validation')
    parser.add_argument('--repo-path', default='.', help='Path to repository root')
    parser.add_argument('--output', help='Output file for validation report (JSON)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run validation
    validator = ComprehensiveValidator(args.repo_path)
    results = validator.run_comprehensive_validation()
    
    # Generate and display report
    summary = validator.generate_report(args.output)
    print(summary)
    
    # Exit with appropriate code
    if results['overall_status'] == 'PASSED':
        sys.exit(0)
    elif results['overall_status'] == 'WARNING':
        sys.exit(1)
    else:
        sys.exit(2)

if __name__ == '__main__':
    main()