#!/usr/bin/env python3
"""
Environment Variable Scanner for Translation Service API Keys

This script scans the environment and configuration files for translation service
API keys or credentials that would indicate direct translation service integration,
violating the architecture requirement that all translation must happen in Copilot Studio.

Features:
- Scan current environment variables
- Check .env files and environment templates
- Detect obfuscated or encoded API keys
- Monitor for new environment variables
- Generate security alerts for translation service credentials

Usage:
    python env_scanner.py                           # Basic scan
    python env_scanner.py --scan-files              # Include file scanning
    python env_scanner.py --monitor                 # Continuous monitoring
    python env_scanner.py --output-format json      # JSON output
"""

import os
import sys
import re
import json
import base64
import argparse
import logging
import time
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class EnvScanResult:
    """Result of environment variable scan."""
    timestamp: str
    violations: List[Dict]
    warnings: List[Dict]
    clean_variables: List[str]
    total_variables_scanned: int
    files_scanned: List[str]
    compliance_status: str


class EnvironmentScanner:
    """Scans environment variables for translation service API keys."""
    
    # Known translation service environment variable patterns
    TRANSLATION_ENV_PATTERNS = {
        # Google Translate
        'GOOGLE_TRANSLATE_API_KEY': 'Google Translate API Key',
        'GOOGLE_APPLICATION_CREDENTIALS': 'Google Cloud Service Account (may include Translate)',
        'GOOGLE_API_KEY': 'Google API Key (may include Translate)',
        'GOOGLE_CLOUD_PROJECT': 'Google Cloud Project (may include Translate)',
        'GCLOUD_PROJECT': 'Google Cloud Project (may include Translate)',
        
        # Azure Translator
        'AZURE_TRANSLATOR_KEY': 'Azure Translator Text API Key',
        'AZURE_TRANSLATOR_TEXT_KEY': 'Azure Translator Text API Key',
        'AZURE_COGNITIVE_SERVICES_KEY': 'Azure Cognitive Services Key (may include Translator)',
        'AZURE_TRANSLATOR_ENDPOINT': 'Azure Translator Endpoint',
        'TRANSLATOR_TEXT_SUBSCRIPTION_KEY': 'Azure Translator Subscription Key',
        'TRANSLATOR_TEXT_REGION': 'Azure Translator Region',
        
        # DeepL
        'DEEPL_API_KEY': 'DeepL Translation API Key',
        'DEEPL_AUTH_KEY': 'DeepL Authentication Key',
        'DEEPL_ENDPOINT': 'DeepL API Endpoint',
        
        # Yandex Translate
        'YANDEX_TRANSLATE_API_KEY': 'Yandex Translate API Key',
        'YANDEX_API_KEY': 'Yandex API Key (may include Translate)',
        'YANDEX_TRANSLATE_FOLDER_ID': 'Yandex Translate Folder ID',
        
        # OpenAI (if used for translation)
        'OPENAI_API_KEY': 'OpenAI API Key (may be used for translation)',
        'OPENAI_ORG_ID': 'OpenAI Organization ID',
        'OPENAI_TRANSLATE_MODEL': 'OpenAI Translation Model',
        
        # AWS Translate
        'AWS_ACCESS_KEY_ID': 'AWS Access Key (may include Translate service)',
        'AWS_SECRET_ACCESS_KEY': 'AWS Secret Key (may include Translate service)',
        'AWS_TRANSLATE_REGION': 'AWS Translate Region',
        'AWS_TRANSLATE_ROLE_ARN': 'AWS Translate IAM Role',
        
        # Generic translation service patterns
        'TRANSLATION_API_KEY': 'Generic Translation API Key',
        'TRANSLATE_API_KEY': 'Generic Translate API Key',
        'TRANSLATION_SERVICE_KEY': 'Translation Service Key',
        'TRANSLATION_ENDPOINT': 'Translation Service Endpoint',
    }
    
    # Suspicious patterns that might indicate translation services
    SUSPICIOUS_PATTERNS = [
        r'.*translate.*key.*',
        r'.*translation.*key.*',
        r'.*translate.*api.*',
        r'.*translation.*api.*',
        r'.*translate.*token.*',
        r'.*translation.*token.*',
        r'.*translate.*secret.*',
        r'.*translation.*secret.*',
        r'.*deepl.*',
        r'.*yandex.*translate.*',
        r'.*google.*translate.*',
        r'.*azure.*translate.*',
        r'.*aws.*translate.*',
    ]
    
    # Known safe environment variables for the bot
    SAFE_VARIABLES = {
        'TELEGRAM_API_TOKEN',
        'DIRECT_LINE_SECRET',
        'DATABASE_URL',
        'PORT',
        'LOG_FILE',
        'LOG_LEVEL',
        'DEBUG_LOCAL',
        'DEBUG_VERBOSE',
        'TELEGRAM_LOG_RESPONSES',
        'USE_WAITRESS',
        'GITHUB_TOKEN',
        'PATH',
        'HOME',
        'USER',
        'PWD',
        'TERM',
        'SHELL',
        'LANG',
        'LC_ALL',
        'TZ',
        'PYTHONPATH',
        'VIRTUAL_ENV',
        'CONDA_DEFAULT_ENV',
    }
    
    def __init__(self, project_root: str = '.'):
        self.project_root = Path(project_root).resolve()
        
    def scan_environment(self, include_files: bool = True) -> EnvScanResult:
        """Perform complete environment scan."""
        start_time = datetime.now(timezone.utc)
        logger.info("Starting environment variable scan for translation service compliance")
        
        violations = []
        warnings = []
        clean_variables = []
        files_scanned = []
        
        # Scan current environment variables
        env_violations, env_warnings, env_clean = self._scan_current_environment()
        violations.extend(env_violations)
        warnings.extend(env_warnings)
        clean_variables.extend(env_clean)
        
        # Scan environment files if requested
        if include_files:
            file_violations, file_warnings, scanned_files = self._scan_environment_files()
            violations.extend(file_violations)
            warnings.extend(file_warnings)
            files_scanned.extend(scanned_files)
        
        # Determine compliance status
        if violations:
            status = "VIOLATION"
        elif warnings:
            status = "WARNING"
        else:
            status = "COMPLIANT"
        
        return EnvScanResult(
            timestamp=start_time.isoformat(),
            violations=violations,
            warnings=warnings,
            clean_variables=clean_variables,
            total_variables_scanned=len(os.environ),
            files_scanned=files_scanned,
            compliance_status=status
        )
    
    def _scan_current_environment(self) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Scan current environment variables."""
        violations = []
        warnings = []
        clean_variables = []
        
        logger.info(f"Scanning {len(os.environ)} environment variables")
        
        for var_name, var_value in os.environ.items():
            # Check for exact matches
            if var_name.upper() in self.TRANSLATION_ENV_PATTERNS:
                severity = 'HIGH' if 'translate' in var_name.lower() else 'MEDIUM'
                violations.append({
                    'type': 'TRANSLATION_ENV_VAR',
                    'variable': var_name,
                    'severity': severity,
                    'description': self.TRANSLATION_ENV_PATTERNS[var_name.upper()],
                    'value_length': len(var_value),
                    'source': 'environment'
                })
                continue
            
            # Check for pattern matches
            var_name_lower = var_name.lower()
            pattern_match = False
            
            for pattern in self.SUSPICIOUS_PATTERNS:
                if re.match(pattern, var_name_lower):
                    pattern_match = True
                    warnings.append({
                        'type': 'SUSPICIOUS_ENV_VAR_PATTERN',
                        'variable': var_name,
                        'pattern': pattern,
                        'severity': 'MEDIUM',
                        'description': f"Environment variable matches suspicious pattern: {pattern}",
                        'value_length': len(var_value),
                        'source': 'environment'
                    })
                    break
            
            if not pattern_match:
                # Check if it's a known safe variable
                if var_name.upper() in self.SAFE_VARIABLES:
                    clean_variables.append(var_name)
                else:
                    # Check for encoded API keys
                    if self._is_suspicious_value(var_value):
                        warnings.append({
                            'type': 'SUSPICIOUS_ENV_VAR_VALUE',
                            'variable': var_name,
                            'severity': 'LOW',
                            'description': f"Environment variable has suspicious value pattern",
                            'value_length': len(var_value),
                            'source': 'environment'
                        })
                    else:
                        clean_variables.append(var_name)
        
        return violations, warnings, clean_variables
    
    def _scan_environment_files(self) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Scan environment files for translation service variables."""
        violations = []
        warnings = []
        files_scanned = []
        
        # Common environment file patterns
        env_file_patterns = [
            '.env',
            '.env.local',
            '.env.development', 
            '.env.production',
            '.env.test',
            '.env.example',
            '.env.template',
            '.env.dist',
            'environment.yml',
            'environment.yaml',
            '.environment'
        ]
        
        for pattern in env_file_patterns:
            for env_file in self.project_root.rglob(pattern):
                try:
                    files_scanned.append(str(env_file))
                    file_violations, file_warnings = self._scan_env_file(env_file)
                    violations.extend(file_violations)
                    warnings.extend(file_warnings)
                except Exception as e:
                    warnings.append({
                        'type': 'FILE_SCAN_ERROR',
                        'file': str(env_file),
                        'description': f"Error scanning environment file: {e}",
                        'severity': 'LOW',
                        'source': 'file'
                    })
        
        return violations, warnings, files_scanned
    
    def _scan_env_file(self, file_path: Path) -> Tuple[List[Dict], List[Dict]]:
        """Scan a single environment file."""
        violations = []
        warnings = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                
                # Parse variable assignment
                if '=' in line:
                    var_name, var_value = line.split('=', 1)
                    var_name = var_name.strip()
                    var_value = var_value.strip().strip('"\'')
                    
                    # Check for translation service variables
                    if var_name.upper() in self.TRANSLATION_ENV_PATTERNS:
                        severity = 'HIGH' if 'translate' in var_name.lower() else 'MEDIUM'
                        violations.append({
                            'type': 'TRANSLATION_ENV_VAR_IN_FILE',
                            'file': str(file_path),
                            'line': line_num,
                            'variable': var_name,
                            'severity': severity,
                            'description': self.TRANSLATION_ENV_PATTERNS[var_name.upper()],
                            'value_length': len(var_value),
                            'source': 'file'
                        })
                        continue
                    
                    # Check for suspicious patterns
                    var_name_lower = var_name.lower()
                    for pattern in self.SUSPICIOUS_PATTERNS:
                        if re.match(pattern, var_name_lower):
                            warnings.append({
                                'type': 'SUSPICIOUS_ENV_VAR_PATTERN_IN_FILE',
                                'file': str(file_path),
                                'line': line_num,
                                'variable': var_name,
                                'pattern': pattern,
                                'severity': 'MEDIUM',
                                'description': f"Variable matches suspicious pattern: {pattern}",
                                'value_length': len(var_value),
                                'source': 'file'
                            })
                            break
                    
                    # Check for suspicious values
                    if var_value and self._is_suspicious_value(var_value):
                        warnings.append({
                            'type': 'SUSPICIOUS_ENV_VAR_VALUE_IN_FILE',
                            'file': str(file_path),
                            'line': line_num,
                            'variable': var_name,
                            'severity': 'LOW',
                            'description': f"Variable has suspicious value pattern",
                            'value_length': len(var_value),
                            'source': 'file'
                        })
        
        except Exception as e:
            raise Exception(f"Failed to read file {file_path}: {e}")
        
        return violations, warnings
    
    def _is_suspicious_value(self, value: str) -> bool:
        """Check if a value looks like an API key or secret."""
        if not value or len(value) < 10:
            return False
        
        # Common API key patterns
        suspicious_patterns = [
            r'^[A-Za-z0-9]{32,}$',  # Long alphanumeric strings
            r'^[A-Za-z0-9+/]+=*$',  # Base64-like
            r'^sk-[A-Za-z0-9]+$',   # OpenAI style
            r'^AIza[A-Za-z0-9_-]+$', # Google API key style
            r'^[a-f0-9]{40,}$',     # Hex keys
            r'.*secret.*',          # Contains 'secret'
            r'.*token.*',           # Contains 'token'
            r'.*key.*',             # Contains 'key'
        ]
        
        value_lower = value.lower()
        for pattern in suspicious_patterns:
            if re.match(pattern, value_lower):
                return True
        
        return False
    
    def monitor_environment(self, interval_seconds: int = 60):
        """Monitor environment variables for changes."""
        logger.info(f"Starting environment monitoring (interval: {interval_seconds}s)")
        
        last_env_vars = set(os.environ.keys())
        
        try:
            while True:
                current_env_vars = set(os.environ.keys())
                
                # Check for new variables
                new_vars = current_env_vars - last_env_vars
                if new_vars:
                    logger.info(f"New environment variables detected: {list(new_vars)}")
                    
                    # Quick scan of new variables
                    for var_name in new_vars:
                        if var_name.upper() in self.TRANSLATION_ENV_PATTERNS:
                            logger.error(f"🚨 VIOLATION: Translation service variable added: {var_name}")
                        else:
                            var_name_lower = var_name.lower()
                            for pattern in self.SUSPICIOUS_PATTERNS:
                                if re.match(pattern, var_name_lower):
                                    logger.warning(f"⚠️  WARNING: Suspicious variable added: {var_name}")
                                    break
                
                # Check for removed variables
                removed_vars = last_env_vars - current_env_vars
                if removed_vars:
                    logger.info(f"Environment variables removed: {list(removed_vars)}")
                
                last_env_vars = current_env_vars
                time.sleep(interval_seconds)
        
        except KeyboardInterrupt:
            logger.info("Environment monitoring stopped by user")
        except Exception as e:
            logger.error(f"Monitoring error: {e}")
    
    def generate_report(self, result: EnvScanResult, format_type: str = 'text') -> str:
        """Generate environment scan report."""
        if format_type == 'json':
            return json.dumps(asdict(result), indent=2)
        
        # Text format
        report = []
        report.append("=" * 80)
        report.append("ENVIRONMENT VARIABLE SCAN REPORT")
        report.append("=" * 80)
        report.append(f"Timestamp: {result.timestamp}")
        report.append(f"Compliance Status: {result.compliance_status}")
        report.append(f"Total Variables Scanned: {result.total_variables_scanned}")
        report.append(f"Files Scanned: {len(result.files_scanned)}")
        report.append("")
        
        # Architecture reminder
        report.append("ARCHITECTURE REQUIREMENT:")
        report.append("• NO translation service API keys should exist")
        report.append("• ALL translation logic must be in Copilot Studio agent")
        report.append("• Bot should only have Telegram and Direct Line credentials")
        report.append("")
        
        # Violations
        if result.violations:
            report.append("🚨 VIOLATIONS FOUND:")
            report.append("-" * 40)
            for violation in result.violations:
                report.append(f"• {violation['type']} [{violation['severity']}]")
                report.append(f"  Variable: {violation['variable']}")
                report.append(f"  Description: {violation['description']}")
                if 'file' in violation:
                    report.append(f"  File: {violation['file']} (line {violation.get('line', 'N/A')})")
                report.append(f"  Value Length: {violation['value_length']} characters")
                report.append("")
        else:
            report.append("✅ NO VIOLATIONS FOUND")
            report.append("")
        
        # Warnings
        if result.warnings:
            report.append("⚠️  WARNINGS:")
            report.append("-" * 40)
            for warning in result.warnings:
                report.append(f"• {warning['type']} [{warning['severity']}]")
                report.append(f"  Variable: {warning['variable']}")
                report.append(f"  Description: {warning['description']}")
                if 'file' in warning:
                    report.append(f"  File: {warning['file']} (line {warning.get('line', 'N/A')})")
                if 'value_length' in warning:
                    report.append(f"  Value Length: {warning['value_length']} characters")
                report.append("")
        
        # Clean variables summary
        if result.clean_variables:
            report.append(f"✅ CLEAN VARIABLES ({len(result.clean_variables)}):")
            report.append("-" * 40)
            for var in sorted(result.clean_variables):
                report.append(f"  • {var}")
            report.append("")
        
        # Files scanned
        if result.files_scanned:
            report.append(f"📁 FILES SCANNED ({len(result.files_scanned)}):")
            report.append("-" * 40)
            for file_path in result.files_scanned:
                report.append(f"  • {file_path}")
            report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS:")
        report.append("-" * 40)
        if result.compliance_status == "COMPLIANT":
            report.append("• Environment is compliant with translation service architecture")
            report.append("• Continue monitoring for new environment variables")
            report.append("• Review .env files before committing to version control")
        else:
            report.append("• URGENT: Remove all translation service API keys")
            report.append("• Verify no direct translation service integrations exist")
            report.append("• Ensure all translation logic is in Copilot Studio")
            report.append("• Review and clean environment files")
        
        return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Environment Variable Scanner for Translation Service Compliance')
    parser.add_argument('--project-root', default='.', help='Project root directory')
    parser.add_argument('--scan-files', action='store_true', help='Include environment files in scan')
    parser.add_argument('--monitor', action='store_true', help='Continuous monitoring mode')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds')
    parser.add_argument('--output-format', choices=['text', 'json'], default='text')
    parser.add_argument('--output-file', help='Save report to file')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scanner = EnvironmentScanner(args.project_root)
    
    if args.monitor:
        scanner.monitor_environment(args.interval)
    else:
        result = scanner.scan_environment(args.scan_files)
        report = scanner.generate_report(result, args.output_format)
        
        if args.output_file:
            with open(args.output_file, 'w') as f:
                f.write(report)
            logger.info(f"Report saved to {args.output_file}")
        else:
            print(report)
        
        # Exit with appropriate code
        sys.exit(0 if result.compliance_status == "COMPLIANT" else 1)


if __name__ == '__main__':
    main()