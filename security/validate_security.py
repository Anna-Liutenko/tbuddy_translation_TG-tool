#!/usr/bin/env python3
"""
Security Validation Script for T.Buddy Translation Tool
Comprehensive pre-deployment security scanning and validation
"""

import os
import re
import json
import sys
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SecurityValidator:
    """Comprehensive security validation for deployment"""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self.issues = []
        self.warnings = []
        
        # Patterns for detecting secrets and sensitive data
        self.secret_patterns = {
            'api_key': re.compile(r'(?i)(api_key|apikey|api-key)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})["\']?'),
            'secret_key': re.compile(r'(?i)(secret_key|secretkey|secret-key)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{16,})["\']?'),
            'telegram_token': re.compile(r'(?i)(telegram.*token|bot.*token)\s*[:=]\s*["\']?(\d+:[a-zA-Z0-9_\-]{35})["\']?'),
            'direct_line_secret': re.compile(r'(?i)(direct.?line.?secret|directlinesecret)\s*[:=]\s*["\']?([a-zA-Z0-9_\-]{20,})["\']?'),
            'github_token': re.compile(r'(?i)(github.*token|gh.*token)\s*[:=]\s*["\']?(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})["\']?'),
            'password': re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]{8,})["\']?'),
            'database_url': re.compile(r'(?i)(database_url|db_url)\s*[:=]\s*["\']?(sqlite://|mysql://|postgresql://|redis://)[^"\'\s]+["\']?'),
            'webhook_url': re.compile(r'(?i)(webhook_url|webhook.?endpoint)\s*[:=]\s*["\']?(https?://[^"\'\s]+)["\']?'),
        }
        
        # Files that should never be committed
        self.forbidden_files = {
            '.env', '.env.local', '.env.production', '.env.development',
            'config.json', 'secrets.json', 'credentials.json',
            '*.key', '*.pem', '*.p12', '*.pfx',
            '*.db', '*.sqlite', '*.sqlite3',
            '*.log', 'run.log', 'debug.log',
            '__pycache__', '*.pyc', '*.pyo',
            '.DS_Store', 'Thumbs.db',
            'node_modules', '*.tmp', '*.temp'
        }
        
        # Required template files
        self.required_templates = {
            '.env.example': 'Development environment template',
            '.env.production.example': 'Production environment template',
            '.env.enhanced.example': 'Enhanced features template',
            '.env.testing': 'Testing environment template'
        }

    def add_issue(self, severity: str, category: str, description: str, file_path: str = None, line_number: int = None):
        """Add a security issue"""
        issue = {
            'severity': severity,
            'category': category,
            'description': description,
            'file_path': str(file_path) if file_path else None,
            'line_number': line_number
        }
        if severity == 'WARNING':
            self.warnings.append(issue)
        else:
            self.issues.append(issue)

    def scan_file_for_secrets(self, file_path: Path) -> List[Dict]:
        """Scan a single file for potential secrets"""
        secrets_found = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            for line_num, line in enumerate(lines, 1):
                for pattern_name, pattern in self.secret_patterns.items():
                    matches = pattern.finditer(line)
                    for match in matches:
                        # Skip template placeholders
                        matched_value = match.group(2)
                        if any(placeholder in matched_value.upper() for placeholder in 
                               ['YOUR_', 'PLACEHOLDER', 'EXAMPLE', 'CHANGE_ME', 'REPLACE_', 'XXX', 'TOKEN_HERE', '_HERE']):
                            continue
                        
                        # Skip URLs with placeholder domains
                        if pattern_name in ['database_url', 'webhook_url'] and any(placeholder in matched_value.upper() for placeholder in 
                               ['DOMAIN_HERE', 'PATH_HERE', 'localhost', '127.0.0.1', 'example.com']):
                            continue
                            
                        secrets_found.append({
                            'type': pattern_name,
                            'file': str(file_path),
                            'line': line_num,
                            'content': line.strip(),
                            'matched_value': match.group(2)[:10] + '...' if len(match.group(2)) > 10 else match.group(2)
                        })
                        
        except Exception as e:
            logger.warning(f"Could not scan file {file_path}: {e}")
            
        return secrets_found

    def validate_gitignore(self) -> bool:
        """Validate .gitignore file for security"""
        gitignore_path = self.repo_path / '.gitignore'
        
        if not gitignore_path.exists():
            self.add_issue('CRITICAL', 'GITIGNORE', 'No .gitignore file found')
            return False
            
        try:
            with open(gitignore_path, 'r', encoding='utf-8') as f:
                gitignore_content = f.read()
                
            # Check for required patterns
            required_patterns = [
                '.env',
                '*.env',
                '.env.*',
                '*.log',
                '*.db',
                '*.sqlite*',
                '__pycache__',
                '*.pyc',
                '.qoder'
            ]
            
            missing_patterns = []
            for pattern in required_patterns:
                if pattern not in gitignore_content:
                    missing_patterns.append(pattern)
                    
            if missing_patterns:
                self.add_issue('HIGH', 'GITIGNORE', f'Missing security patterns in .gitignore: {", ".join(missing_patterns)}')
                return False
                
        except Exception as e:
            self.add_issue('CRITICAL', 'GITIGNORE', f'Could not read .gitignore: {e}')
            return False
            
        return True

    def validate_environment_templates(self) -> bool:
        """Validate environment template files"""
        all_valid = True
        
        for template_name, description in self.required_templates.items():
            template_path = self.repo_path / template_name
            
            if not template_path.exists():
                self.add_issue('HIGH', 'ENV_TEMPLATE', f'Missing required template: {template_name} ({description})')
                all_valid = False
                continue
                
            # For template files, only check for obviously real secrets (not placeholder URLs)
            try:
                with open(template_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # Check for obviously real secrets (not placeholder patterns)
                real_secret_patterns = {
                    'telegram_token': re.compile(r'(?i)(telegram.*token|bot.*token)\s*[:=]\s*["\']?(\d+:[a-zA-Z0-9_\-]{35})["\']?'),
                    'github_token': re.compile(r'(?i)(github.*token|gh.*token)\s*[:=]\s*["\']?(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})["\']?'),
                }
                
                lines = content.splitlines()
                for line_num, line in enumerate(lines, 1):
                    for pattern_name, pattern in real_secret_patterns.items():
                        matches = pattern.finditer(line)
                        for match in matches:
                            # Only flag if it doesn't look like a placeholder
                            matched_value = match.group(2)
                            if not any(placeholder in matched_value.upper() for placeholder in 
                                     ['YOUR_', 'PLACEHOLDER', 'EXAMPLE', 'CHANGE_ME', 'REPLACE_', 'XXX', 'TOKEN_HERE', '_HERE']):
                                self.add_issue('CRITICAL', 'ENV_TEMPLATE', 
                                             f'Template {template_name} contains real secret: {pattern_name} at line {line_num}')
                                all_valid = False
                    
                # Check for required placeholders
                required_vars = ['TELEGRAM_API_TOKEN', 'DIRECT_LINE_SECRET']
                missing_vars = []
                
                for var in required_vars:
                    if var not in content:
                        missing_vars.append(var)
                        
                if missing_vars:
                    self.add_issue('MEDIUM', 'ENV_TEMPLATE', 
                                 f'Template {template_name} missing required variables: {", ".join(missing_vars)}')
                    
            except Exception as e:
                self.add_issue('HIGH', 'ENV_TEMPLATE', f'Could not validate template {template_name}: {e}')
                all_valid = False
                
        return all_valid

    def scan_repository_for_secrets(self) -> List[Dict]:
        """Scan entire repository for secrets"""
        all_secrets = []
        
        # Define file patterns to scan
        scan_patterns = ['*.py', '*.js', '*.json', '*.yaml', '*.yml', '*.sh', '*.conf', '*.cfg', '*.ini']
        
        for pattern in scan_patterns:
            for file_path in self.repo_path.rglob(pattern):
                # Skip certain directories
                if any(part in file_path.parts for part in ['.git', '__pycache__', 'node_modules', '.qoder']):
                    continue
                    
                # Skip template files (they should only have placeholders)
                if file_path.name.endswith('.example') or file_path.name == '.env.testing':
                    continue
                    
                secrets = self.scan_file_for_secrets(file_path)
                all_secrets.extend(secrets)
                
        return all_secrets

    def validate_file_permissions(self) -> bool:
        """Validate file permissions for security"""
        issues_found = False
        
        # Check for files that should not be world-readable
        sensitive_files = ['.env', 'config.json', 'secrets.json']
        
        for file_name in sensitive_files:
            file_path = self.repo_path / file_name
            if file_path.exists():
                # On Windows, this is less critical, but still check
                try:
                    stat_info = file_path.stat()
                    # This is a simplified check - on Unix systems we'd check octal permissions
                    self.add_issue('WARNING', 'PERMISSIONS', 
                                 f'Sensitive file {file_name} exists in repository')
                    issues_found = True
                except Exception as e:
                    logger.warning(f"Could not check permissions for {file_path}: {e}")
                    
        return not issues_found

    def check_forbidden_files(self) -> bool:
        """Check for files that should never be committed"""
        issues_found = False
        
        for forbidden_pattern in self.forbidden_files:
            if '*' in forbidden_pattern:
                # Handle glob patterns
                pattern = forbidden_pattern.replace('*', '')
                for file_path in self.repo_path.rglob('*'):
                    if pattern in file_path.name and not file_path.is_dir():
                        # Skip template files
                        if not file_path.name.endswith('.example') and file_path.name != '.env.testing':
                            self.add_issue('HIGH', 'FORBIDDEN_FILE', 
                                         f'Forbidden file found: {file_path.relative_to(self.repo_path)}')
                            issues_found = True
            else:
                file_path = self.repo_path / forbidden_pattern
                if file_path.exists() and not file_path.name.endswith('.example'):
                    self.add_issue('HIGH', 'FORBIDDEN_FILE', 
                                 f'Forbidden file found: {forbidden_pattern}')
                    issues_found = True
                    
        return not issues_found

    def validate_deployment_scripts(self) -> bool:
        """Validate deployment scripts for security"""
        issues_found = False
        deploy_dir = self.repo_path / 'deploy'
        
        if not deploy_dir.exists():
            self.add_issue('WARNING', 'DEPLOYMENT', 'No deploy directory found')
            return True
            
        # Check deployment scripts
        for script_file in deploy_dir.glob('*.sh'):
            secrets = self.scan_file_for_secrets(script_file)
            if secrets:
                for secret in secrets:
                    self.add_issue('CRITICAL', 'DEPLOYMENT', 
                                 f'Deployment script {script_file.name} contains secret: {secret["type"]} at line {secret["line"]}')
                    issues_found = True
                    
        return not issues_found

    def generate_security_report(self) -> Dict:
        """Generate comprehensive security report"""
        return {
            'timestamp': os.environ.get('BUILD_TIMESTAMP', 'unknown'),
            'repository_path': str(self.repo_path),
            'critical_issues': len([i for i in self.issues if i['severity'] == 'CRITICAL']),
            'high_issues': len([i for i in self.issues if i['severity'] == 'HIGH']),
            'medium_issues': len([i for i in self.issues if i['severity'] == 'MEDIUM']),
            'warnings': len(self.warnings),
            'total_issues': len(self.issues),
            'issues': self.issues,
            'warnings': self.warnings,
            'scan_summary': {
                'gitignore_valid': self.validate_gitignore(),
                'templates_valid': self.validate_environment_templates(),
                'no_secrets_found': len(self.scan_repository_for_secrets()) == 0,
                'permissions_secure': self.validate_file_permissions(),
                'no_forbidden_files': self.check_forbidden_files(),
                'deployment_secure': self.validate_deployment_scripts()
            }
        }

    def run_full_validation(self) -> bool:
        """Run complete security validation"""
        logger.info("Starting comprehensive security validation...")
        
        # 1. Validate .gitignore
        logger.info("Validating .gitignore...")
        self.validate_gitignore()
        
        # 2. Validate environment templates
        logger.info("Validating environment templates...")
        self.validate_environment_templates()
        
        # 3. Scan for secrets
        logger.info("Scanning repository for secrets...")
        secrets = self.scan_repository_for_secrets()
        for secret in secrets:
            self.add_issue('CRITICAL', 'SECRET_EXPOSURE', 
                         f'Secret found in {secret["file"]} at line {secret["line"]}: {secret["type"]}')
        
        # 4. Check file permissions
        logger.info("Validating file permissions...")
        self.validate_file_permissions()
        
        # 5. Check for forbidden files
        logger.info("Checking for forbidden files...")
        self.check_forbidden_files()
        
        # 6. Validate deployment scripts
        logger.info("Validating deployment scripts...")
        self.validate_deployment_scripts()
        
        # Generate report
        report = self.generate_security_report()
        
        # Critical issues block deployment
        critical_issues = [i for i in self.issues if i['severity'] == 'CRITICAL']
        if critical_issues:
            logger.error(f"SECURITY VALIDATION FAILED: {len(critical_issues)} critical issues found")
            for issue in critical_issues:
                logger.error(f"CRITICAL: {issue['category']} - {issue['description']}")
            return False
            
        # High severity issues are warnings but don't block
        high_issues = [i for i in self.issues if i['severity'] == 'HIGH']
        if high_issues:
            logger.warning(f"Security concerns found: {len(high_issues)} high severity issues")
            for issue in high_issues:
                logger.warning(f"HIGH: {issue['category']} - {issue['description']}")
        
        logger.info("Security validation completed successfully")
        return True

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Security validation for T.Buddy deployment')
    parser.add_argument('--repo-path', default='.', help='Path to repository root')
    parser.add_argument('--output', help='Output file for security report (JSON)')
    parser.add_argument('--strict', action='store_true', help='Treat warnings as errors')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run validation
    validator = SecurityValidator(args.repo_path)
    validation_passed = validator.run_full_validation()
    
    # Generate report
    report = validator.generate_security_report()
    
    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Security report saved to {args.output}")
    
    # Print summary
    print("\n" + "="*60)
    print("SECURITY VALIDATION SUMMARY")
    print("="*60)
    print(f"Critical Issues: {report['critical_issues']}")
    print(f"High Issues: {report['high_issues']}")
    print(f"Medium Issues: {report['medium_issues']}")
    print(f"Warnings: {report['warnings']}")
    print(f"Total Issues: {report['total_issues']}")
    
    if validation_passed:
        if args.strict and report['warnings'] > 0:
            print("\nSTATUS: FAILED (strict mode - warnings treated as errors)")
            sys.exit(1)
        else:
            print("\nSTATUS: PASSED")
            sys.exit(0)
    else:
        print("\nSTATUS: FAILED")
        sys.exit(1)

if __name__ == '__main__':
    main()