#!/usr/bin/env python3
"""
Dependency Auditing Script for Translation Service Compliance

This script continuously monitors the project for any new dependencies or code changes
that might introduce direct translation service calls, violating the architecture
requirement that all translation logic must be in Copilot Studio.

Features:
- Monitor requirements.txt changes
- Track new Python file additions
- Scan commits for translation service introductions
- Generate alerts and compliance reports
- Integration with CI/CD pipelines

Usage:
    python dependency_auditor.py --mode monitor        # Continuous monitoring
    python dependency_auditor.py --mode check          # One-time check
    python dependency_auditor.py --mode git-hook       # Git hook integration
    python dependency_auditor.py --mode ci             # CI/CD integration
"""

import os
import sys
import time
import json
import hashlib
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, asdict
import importlib.util

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class AuditResult:
    """Results of a dependency audit scan."""
    timestamp: str
    project_path: str
    compliance_status: str  # COMPLIANT, WARNING, VIOLATION
    violations: List[Dict]
    warnings: List[Dict]
    dependencies_hash: str
    files_hash: str
    scan_duration_ms: int


class DependencyAuditor:
    """Monitors project dependencies for translation service compliance."""
    
    FORBIDDEN_PACKAGES = {
        'googletrans', 'google-cloud-translate', 'google-cloud-translation',
        'azure-cognitiveservices-language-translatortext', 'azure-ai-translation',
        'deepl', 'yandex-translate', 'yandextranslate',
        'openai', 'boto3',  # Can be used for AWS Translate
        'mtranslate', 'translators', 'translate',
        'polyglot', 'textblob', 'langdetect'  # Often used with translation
    }
    
    SUSPICIOUS_PACKAGES = {
        'requests',  # Could be used to call translation APIs directly
        'urllib3', 'httpx', 'aiohttp'  # HTTP clients
    }
    
    ALLOWED_PACKAGES = {
        'flask', 'python-dotenv', 'waitress', 'gunicorn', 
        'pygithub', 'gitpython', 'pytest', 'requests'  # Core dependencies
    }
    
    def __init__(self, project_root: str, state_file: str = '.audit_state.json'):
        self.project_root = Path(project_root).resolve()
        self.state_file = self.project_root / state_file
        self.current_state = self._load_state()
        
    def _load_state(self) -> Dict:
        """Load previous audit state from disk."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load audit state: {e}")
        return {
            'last_scan': None,
            'dependencies_hash': None,
            'files_hash': None,
            'violation_count': 0,
            'scan_history': []
        }
    
    def _save_state(self, result: AuditResult):
        """Save audit state to disk."""
        self.current_state.update({
            'last_scan': result.timestamp,
            'dependencies_hash': result.dependencies_hash,
            'files_hash': result.files_hash,
            'violation_count': len(result.violations),
            'scan_history': (self.current_state.get('scan_history', []) + [asdict(result)])[-10:]  # Keep last 10
        })
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(self.current_state, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save audit state: {e}")
    
    def run_audit(self) -> AuditResult:
        """Run complete dependency audit."""
        start_time = datetime.now(timezone.utc)
        logger.info(f"Starting dependency audit for {self.project_root}")
        
        violations = []
        warnings = []
        
        # Check dependencies
        dep_violations, dep_warnings = self._audit_dependencies()
        violations.extend(dep_violations)
        warnings.extend(dep_warnings)
        
        # Check new files
        file_violations, file_warnings = self._audit_new_files()
        violations.extend(file_violations)
        warnings.extend(file_warnings)
        
        # Check git history if available
        git_violations, git_warnings = self._audit_git_changes()
        violations.extend(git_violations)
        warnings.extend(git_warnings)
        
        # Calculate hashes
        deps_hash = self._calculate_dependencies_hash()
        files_hash = self._calculate_files_hash()
        
        # Determine compliance status
        if violations:
            status = "VIOLATION"
        elif warnings:
            status = "WARNING"
        else:
            status = "COMPLIANT"
        
        # Create result
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        result = AuditResult(
            timestamp=start_time.isoformat(),
            project_path=str(self.project_root),
            compliance_status=status,
            violations=violations,
            warnings=warnings,
            dependencies_hash=deps_hash,
            files_hash=files_hash,
            scan_duration_ms=duration
        )
        
        # Save state
        self._save_state(result)
        
        logger.info(f"Audit completed: {status} ({len(violations)} violations, {len(warnings)} warnings)")
        return result
    
    def _audit_dependencies(self) -> Tuple[List[Dict], List[Dict]]:
        """Audit project dependencies for forbidden packages."""
        violations = []
        warnings = []
        
        # Check requirements.txt
        req_file = self.project_root / 'requirements.txt'
        if req_file.exists():
            deps_violations, deps_warnings = self._check_requirements_file(req_file)
            violations.extend(deps_violations)
            warnings.extend(deps_warnings)
        
        # Check other dependency files
        for dep_file in ['Pipfile', 'pyproject.toml', 'setup.py']:
            file_path = self.project_root / dep_file
            if file_path.exists():
                file_violations, file_warnings = self._check_dependency_file(file_path)
                violations.extend(file_violations)
                warnings.extend(file_warnings)
        
        return violations, warnings
    
    def _check_requirements_file(self, file_path: Path) -> Tuple[List[Dict], List[Dict]]:
        """Check requirements.txt for forbidden dependencies."""
        violations = []
        warnings = []
        
        try:
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip().lower()
                if not line or line.startswith('#'):
                    continue
                
                # Extract package name (before ==, >=, etc.)
                package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()
                
                if package_name in self.FORBIDDEN_PACKAGES:
                    violations.append({
                        'type': 'FORBIDDEN_DEPENDENCY',
                        'file': str(file_path),
                        'line': line_num,
                        'package': package_name,
                        'severity': 'HIGH',
                        'description': f"Forbidden translation service dependency: {package_name}"
                    })
                elif package_name in self.SUSPICIOUS_PACKAGES and package_name not in self.ALLOWED_PACKAGES:
                    warnings.append({
                        'type': 'SUSPICIOUS_DEPENDENCY',
                        'file': str(file_path),
                        'line': line_num,
                        'package': package_name,
                        'severity': 'MEDIUM',
                        'description': f"Suspicious dependency that could be used for direct API calls: {package_name}"
                    })
        
        except Exception as e:
            warnings.append({
                'type': 'AUDIT_ERROR',
                'file': str(file_path),
                'description': f"Error reading requirements file: {e}"
            })
        
        return violations, warnings
    
    def _check_dependency_file(self, file_path: Path) -> Tuple[List[Dict], List[Dict]]:
        """Check other dependency files for forbidden packages."""
        violations = []
        warnings = []
        
        try:
            with open(file_path, 'r') as f:
                content = f.read().lower()
            
            for package in self.FORBIDDEN_PACKAGES:
                if package in content:
                    violations.append({
                        'type': 'FORBIDDEN_DEPENDENCY_IN_CONFIG',
                        'file': str(file_path),
                        'package': package,
                        'severity': 'HIGH',
                        'description': f"Forbidden dependency found in {file_path.name}: {package}"
                    })
        
        except Exception as e:
            warnings.append({
                'type': 'AUDIT_ERROR',
                'file': str(file_path),
                'description': f"Error reading dependency file: {e}"
            })
        
        return violations, warnings
    
    def _audit_new_files(self) -> Tuple[List[Dict], List[Dict]]:
        """Check for new Python files that might contain translation services."""
        violations = []
        warnings = []
        
        # Get current file hash
        current_files_hash = self._calculate_files_hash()
        previous_files_hash = self.current_state.get('files_hash')
        
        if previous_files_hash and current_files_hash != previous_files_hash:
            logger.info("Detected changes in Python files, scanning for new violations")
            
            # Run quick compliance check on all Python files
            python_files = list(self.project_root.rglob("*.py"))
            for py_file in python_files:
                file_violations, file_warnings = self._quick_scan_python_file(py_file)
                violations.extend(file_violations)
                warnings.extend(file_warnings)
        
        return violations, warnings
    
    def _quick_scan_python_file(self, file_path: Path) -> Tuple[List[Dict], List[Dict]]:
        """Quick scan of a Python file for translation service usage."""
        violations = []
        warnings = []
        
        # Skip validation/testing scripts
        validation_files = {
            'compliance_test.py', 'dependency_auditor.py', 'env_scanner.py',
            'test_compliance.py', 'validate_compliance.py'
        }
        
        if file_path.name in validation_files:
            return violations, warnings  # Skip validation scripts
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            
            # Check for import statements
            for line_num, line in enumerate(lines, 1):
                line_lower = line.strip().lower()
                
                # Check imports
                if line_lower.startswith(('import ', 'from ')):
                    for package in self.FORBIDDEN_PACKAGES:
                        if package in line_lower:
                            violations.append({
                                'type': 'FORBIDDEN_IMPORT_DETECTED',
                                'file': str(file_path),
                                'line': line_num,
                                'content': line.strip(),
                                'severity': 'HIGH',
                                'description': f"Forbidden import detected: {package}"
                            })
                
                # Check for API endpoints
                api_endpoints = [
                    'translate.googleapis.com',
                    'api.cognitive.microsofttranslator.com',
                    'api.deepl.com',
                    'translate.yandex.net'
                ]
                
                for endpoint in api_endpoints:
                    if endpoint in line_lower:
                        violations.append({
                            'type': 'TRANSLATION_API_ENDPOINT_DETECTED',
                            'file': str(file_path),
                            'line': line_num,
                            'endpoint': endpoint,
                            'severity': 'HIGH',
                            'description': f"Translation API endpoint detected: {endpoint}"
                        })
        
        except Exception as e:
            warnings.append({
                'type': 'FILE_SCAN_ERROR',
                'file': str(file_path),
                'description': f"Error scanning file: {e}"
            })
        
        return violations, warnings
    
    def _audit_git_changes(self) -> Tuple[List[Dict], List[Dict]]:
        """Audit recent git changes for translation service additions."""
        violations = []
        warnings = []
        
        try:
            # Check if we're in a git repository
            result = subprocess.run(['git', 'rev-parse', '--git-dir'], 
                                  cwd=self.project_root, 
                                  capture_output=True, 
                                  text=True)
            
            if result.returncode != 0:
                return violations, warnings
            
            # Get recent commits (last 10)
            result = subprocess.run(['git', 'log', '--oneline', '-10'], 
                                  cwd=self.project_root, 
                                  capture_output=True, 
                                  text=True)
            
            if result.returncode == 0:
                commits = result.stdout.strip().split('\n')
                for commit in commits:
                    if any(keyword in commit.lower() for keyword in 
                          ['translate', 'translation', 'google', 'azure', 'deepl']):
                        warnings.append({
                            'type': 'SUSPICIOUS_COMMIT_MESSAGE',
                            'commit': commit,
                            'severity': 'MEDIUM',
                            'description': f"Suspicious commit message: {commit}"
                        })
        
        except Exception as e:
            logger.debug(f"Git audit failed: {e}")
        
        return violations, warnings
    
    def _calculate_dependencies_hash(self) -> str:
        """Calculate hash of all dependency files."""
        hash_input = ""
        
        for dep_file in ['requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py']:
            file_path = self.project_root / dep_file
            if file_path.exists():
                try:
                    with open(file_path, 'r') as f:
                        hash_input += f.read()
                except Exception:
                    pass
        
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def _calculate_files_hash(self) -> str:
        """Calculate hash of all Python files."""
        python_files = sorted(self.project_root.rglob("*.py"))
        hash_input = ""
        
        for py_file in python_files:
            try:
                hash_input += str(py_file.stat().st_mtime)
                hash_input += str(py_file.stat().st_size)
            except Exception:
                pass
        
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def monitor_continuously(self, interval_seconds: int = 300):
        """Run continuous monitoring with specified interval."""
        logger.info(f"Starting continuous monitoring (interval: {interval_seconds}s)")
        
        try:
            while True:
                result = self.run_audit()
                
                if result.compliance_status != "COMPLIANT":
                    self._send_alert(result)
                
                time.sleep(interval_seconds)
        
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    def _send_alert(self, result: AuditResult):
        """Send alert for compliance violations."""
        if result.compliance_status == "VIOLATION":
            logger.error(f"🚨 COMPLIANCE VIOLATION DETECTED!")
            for violation in result.violations:
                logger.error(f"  - {violation['type']}: {violation['description']}")
        elif result.compliance_status == "WARNING":
            logger.warning(f"⚠️  COMPLIANCE WARNING!")
            for warning in result.warnings:
                logger.warning(f"  - {warning['type']}: {warning['description']}")
    
    def generate_report(self, result: AuditResult, format_type: str = 'text') -> str:
        """Generate audit report in specified format."""
        if format_type == 'json':
            return json.dumps(asdict(result), indent=2)
        
        # Text format
        report = []
        report.append("=" * 80)
        report.append("DEPENDENCY AUDIT REPORT")
        report.append("=" * 80)
        report.append(f"Timestamp: {result.timestamp}")
        report.append(f"Project: {result.project_path}")
        report.append(f"Status: {result.compliance_status}")
        report.append(f"Scan Duration: {result.scan_duration_ms}ms")
        report.append("")
        
        if result.violations:
            report.append("VIOLATIONS:")
            report.append("-" * 40)
            for violation in result.violations:
                report.append(f"• {violation['type']}")
                report.append(f"  Description: {violation['description']}")
                if 'file' in violation:
                    report.append(f"  File: {violation['file']}")
                if 'line' in violation:
                    report.append(f"  Line: {violation['line']}")
                report.append("")
        
        if result.warnings:
            report.append("WARNINGS:")
            report.append("-" * 40)
            for warning in result.warnings:
                report.append(f"• {warning['type']}")
                report.append(f"  Description: {warning['description']}")
                if 'file' in warning:
                    report.append(f"  File: {warning['file']}")
                report.append("")
        
        if not result.violations and not result.warnings:
            report.append("✅ NO ISSUES FOUND")
            report.append("Project maintains translation service compliance.")
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Dependency Auditing for Translation Service Compliance')
    parser.add_argument('--mode', choices=['check', 'monitor', 'git-hook', 'ci'], 
                       default='check', help='Audit mode')
    parser.add_argument('--project-root', default='.', help='Project root directory')
    parser.add_argument('--interval', type=int, default=300, help='Monitoring interval in seconds')
    parser.add_argument('--output-format', choices=['text', 'json'], default='text')
    parser.add_argument('--output-file', help='Save report to file')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    auditor = DependencyAuditor(args.project_root)
    
    if args.mode == 'monitor':
        auditor.monitor_continuously(args.interval)
    elif args.mode == 'check':
        result = auditor.run_audit()
        report = auditor.generate_report(result, args.output_format)
        
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {args.output_file}")
        else:
            print(report)
        
        # Exit with appropriate code
        sys.exit(0 if result.compliance_status == "COMPLIANT" else 1)
    elif args.mode == 'git-hook':
        # Quick check for git pre-commit hook
        result = auditor.run_audit()
        if result.compliance_status == "VIOLATION":
            print("❌ COMMIT REJECTED: Translation service violations detected!")
            print(auditor.generate_report(result))
            sys.exit(1)
        else:
            print("✅ Dependency audit passed")
    elif args.mode == 'ci':
        # CI/CD integration mode
        result = auditor.run_audit()
        print(auditor.generate_report(result, 'json'))
        sys.exit(0 if result.compliance_status == "COMPLIANT" else 1)


if __name__ == '__main__':
    main()