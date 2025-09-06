#!/usr/bin/env python3
"""
Translation Service Compliance Testing Script

This script verifies that the Telegram bot contains NO direct translation service calls
and maintains compliance with the architecture requirement that all translation logic
must be executed within the Copilot Studio agent.

Usage:
    python compliance_test.py
    python compliance_test.py --verbose
    python compliance_test.py --output-format json
"""

import os
import sys
import ast
import json
import argparse
import logging
from pathlib import Path
from typing import List, Dict, Set, Tuple
import importlib.util

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

class TranslationServiceDetector:
    """Detects direct translation service usage in Python code."""
    
    TRANSLATION_SERVICES = {
        'google.cloud.translate',
        'google.cloud.translation',
        'googletrans',
        'azure.ai.translation',
        'azure.cognitiveservices.language.translatortext',
        'deepl',
        'yandextranslate',
        'openai',
        'boto3',  # AWS Translate via boto3
        'awstranslate',
        'translate',
        'mtranslate',
        'translators'
    }
    
    TRANSLATION_KEYWORDS = {
        'translate_text', 'translate_client', 'translator_client',
        'translation_service', 'google_translate', 'azure_translate',
        'deepl_translate', 'yandex_translate', 'aws_translate',
        'openai_translate', 'translation_api', 'translate_api'
    }
    
    TRANSLATION_ENV_VARS = {
        'GOOGLE_TRANSLATE_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS',
        'AZURE_TRANSLATOR_KEY', 'AZURE_TRANSLATOR_ENDPOINT',
        'DEEPL_API_KEY', 'DEEPL_AUTH_KEY',
        'YANDEX_TRANSLATE_API_KEY', 'YANDEX_API_KEY',
        'OPENAI_API_KEY', 'OPENAI_TRANSLATE_KEY',
        'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY',
        'TRANSLATOR_TEXT_SUBSCRIPTION_KEY'
    }

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.violations = []
        self.warnings = []
        
    def scan_project(self) -> Dict[str, List]:
        """Scan entire project for translation service violations."""
        logger.info(f"Scanning project at: {self.project_root}")
        
        # Scan Python files
        self._scan_python_files()
        
        # Scan requirements files
        self._scan_requirements()
        
        # Scan environment variables
        self._scan_environment_variables()
        
        # Scan configuration files
        self._scan_config_files()
        
        return {
            'violations': self.violations,
            'warnings': self.warnings,
            'compliant': len(self.violations) == 0
        }
    
    def _scan_python_files(self):
        """Scan all Python files for translation service imports and usage."""
        python_files = list(self.project_root.rglob("*.py"))
        logger.info(f"Scanning {len(python_files)} Python files")
        
        for py_file in python_files:
            try:
                self._analyze_python_file(py_file)
            except Exception as e:
                self.warnings.append(f"Failed to analyze {py_file}: {e}")
    
    def _analyze_python_file(self, file_path: Path):
        """Analyze a single Python file for translation service usage."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse AST
            tree = ast.parse(content, filename=str(file_path))
            
            # Check imports
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    self._check_import_node(node, file_path)
                elif isinstance(node, ast.FunctionDef):
                    self._check_function_node(node, file_path)
                elif isinstance(node, ast.Assign):
                    self._check_assignment_node(node, file_path)
                elif isinstance(node, ast.Call):
                    self._check_function_call(node, file_path)
            
            # Check string literals for API endpoints
            self._check_string_literals(content, file_path)
            
        except SyntaxError as e:
            self.warnings.append(f"Syntax error in {file_path}: {e}")
        except Exception as e:
            self.warnings.append(f"Error analyzing {file_path}: {e}")
    
    def _check_import_node(self, node: ast.AST, file_path: Path):
        """Check import statements for translation services."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_name = alias.name
                if any(service in module_name for service in self.TRANSLATION_SERVICES):
                    self.violations.append({
                        'type': 'FORBIDDEN_IMPORT',
                        'file': str(file_path),
                        'line': node.lineno,
                        'module': module_name,
                        'description': f"Direct import of translation service: {module_name}"
                    })
        
        elif isinstance(node, ast.ImportFrom):
            module_name = node.module or ''
            if any(service in module_name for service in self.TRANSLATION_SERVICES):
                imported_names = [alias.name for alias in node.names]
                self.violations.append({
                    'type': 'FORBIDDEN_FROM_IMPORT',
                    'file': str(file_path),
                    'line': node.lineno,
                    'module': module_name,
                    'imports': imported_names,
                    'description': f"Direct import from translation service: {module_name}"
                })
    
    def _check_function_node(self, node: ast.FunctionDef, file_path: Path):
        """Check function definitions for translation-related names."""
        # Skip validation/testing scripts
        validation_files = {
            'compliance_test.py', 'dependency_auditor.py', 'env_scanner.py',
            'test_compliance.py', 'validate_compliance.py'
        }
        
        if file_path.name in validation_files:
            return  # Skip validation scripts
            
        func_name = node.name.lower()
        if any(keyword in func_name for keyword in self.TRANSLATION_KEYWORDS):
            self.warnings.append({
                'type': 'SUSPICIOUS_FUNCTION_NAME',
                'file': str(file_path),
                'line': node.lineno,
                'function': node.name,
                'description': f"Function name suggests translation logic: {node.name}"
            })
    
    def _check_assignment_node(self, node: ast.Assign, file_path: Path):
        """Check variable assignments for translation service clients."""
        # Skip validation/testing scripts
        validation_files = {
            'compliance_test.py', 'dependency_auditor.py', 'env_scanner.py',
            'test_compliance.py', 'validate_compliance.py'
        }
        
        if file_path.name in validation_files:
            return  # Skip validation scripts
            
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_name = target.id.lower()
                if any(keyword in var_name for keyword in self.TRANSLATION_KEYWORDS):
                    self.warnings.append({
                        'type': 'SUSPICIOUS_VARIABLE_NAME',
                        'file': str(file_path),
                        'line': node.lineno,
                        'variable': target.id,
                        'description': f"Variable name suggests translation service: {target.id}"
                    })
    
    def _check_function_call(self, node: ast.Call, file_path: Path):
        """Check function calls for translation service API calls."""
        # Skip validation/testing scripts
        validation_files = {
            'compliance_test.py', 'dependency_auditor.py', 'env_scanner.py',
            'test_compliance.py', 'validate_compliance.py'
        }
        
        if file_path.name in validation_files:
            return  # Skip validation scripts
            
        if isinstance(node.func, ast.Attribute):
            method_name = node.func.attr.lower()
            if any(keyword in method_name for keyword in self.TRANSLATION_KEYWORDS):
                self.warnings.append({
                    'type': 'SUSPICIOUS_METHOD_CALL',
                    'file': str(file_path),
                    'line': node.lineno,
                    'method': node.func.attr,
                    'description': f"Method call suggests translation logic: {node.func.attr}"
                })
    
    def _check_string_literals(self, content: str, file_path: Path):
        """Check string literals for translation service API endpoints."""
        # Skip validation/testing scripts that contain reference endpoints
        validation_files = {
            'compliance_test.py', 'dependency_auditor.py', 'env_scanner.py',
            'test_compliance.py', 'validate_compliance.py'
        }
        
        if file_path.name in validation_files:
            return  # Skip validation scripts that contain reference patterns
            
        translation_endpoints = [
            'translate.googleapis.com',
            'api.cognitive.microsofttranslator.com',
            'api-free.deepl.com',
            'api.deepl.com',
            'translate.yandex.net',
            'api.openai.com/v1/chat/completions',  # If used for translation
            'comprehend.amazonaws.com'
        ]
        
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            line_lower = line.lower()
            for endpoint in translation_endpoints:
                if endpoint in line_lower and 'example' not in line_lower:
                    self.violations.append({
                        'type': 'TRANSLATION_API_ENDPOINT',
                        'file': str(file_path),
                        'line': line_num,
                        'endpoint': endpoint,
                        'description': f"Translation service API endpoint found: {endpoint}"
                    })
    
    def _scan_requirements(self):
        """Scan requirements files for translation service dependencies."""
        req_files = [
            'requirements.txt', 'requirements-dev.txt', 'requirements-prod.txt',
            'Pipfile', 'pyproject.toml', 'setup.py'
        ]
        
        for req_file in req_files:
            file_path = self.project_root / req_file
            if file_path.exists():
                self._check_requirements_file(file_path)
    
    def _check_requirements_file(self, file_path: Path):
        """Check a requirements file for translation service dependencies."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                line_clean = line.strip().lower()
                if line_clean and not line_clean.startswith('#'):
                    package_name = line_clean.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0]
                    
                    if any(service in package_name for service in self.TRANSLATION_SERVICES):
                        self.violations.append({
                            'type': 'FORBIDDEN_DEPENDENCY',
                            'file': str(file_path),
                            'line': line_num,
                            'package': package_name,
                            'description': f"Translation service dependency found: {package_name}"
                        })
        except Exception as e:
            self.warnings.append(f"Error checking requirements file {file_path}: {e}")
    
    def _scan_environment_variables(self):
        """Check environment variables for translation service API keys."""
        # Check current environment
        for var_name in os.environ:
            if var_name.upper() in self.TRANSLATION_ENV_VARS:
                self.violations.append({
                    'type': 'TRANSLATION_ENV_VAR',
                    'variable': var_name,
                    'description': f"Translation service environment variable found: {var_name}"
                })
        
        # Check .env files
        env_files = ['.env', '.env.local', '.env.production', '.env.development']
        for env_file in env_files:
            file_path = self.project_root / env_file
            if file_path.exists():
                self._check_env_file(file_path)
    
    def _check_env_file(self, file_path: Path):
        """Check an environment file for translation service variables."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                line_clean = line.strip()
                if line_clean and not line_clean.startswith('#') and '=' in line_clean:
                    var_name = line_clean.split('=')[0].strip()
                    if var_name.upper() in self.TRANSLATION_ENV_VARS:
                        self.violations.append({
                            'type': 'TRANSLATION_ENV_VAR_FILE',
                            'file': str(file_path),
                            'line': line_num,
                            'variable': var_name,
                            'description': f"Translation service environment variable in file: {var_name}"
                        })
        except Exception as e:
            self.warnings.append(f"Error checking env file {file_path}: {e}")
    
    def _scan_config_files(self):
        """Scan configuration files for translation service references."""
        config_files = list(self.project_root.rglob("*.yaml")) + \
                     list(self.project_root.rglob("*.yml")) + \
                     list(self.project_root.rglob("*.json")) + \
                     list(self.project_root.rglob("*.toml"))
        
        for config_file in config_files:
            if config_file.name.startswith('.git'):
                continue
            self._check_config_file(config_file)
    
    def _check_config_file(self, file_path: Path):
        """Check a configuration file for translation service references."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().lower()
            
            for service in self.TRANSLATION_SERVICES:
                if service in content:
                    self.warnings.append({
                        'type': 'TRANSLATION_REFERENCE_IN_CONFIG',
                        'file': str(file_path),
                        'service': service,
                        'description': f"Translation service reference in config: {service}"
                    })
        except Exception as e:
            # Skip binary files or files with encoding issues
            pass


def generate_compliance_report(results: Dict, format_type: str = 'text') -> str:
    """Generate a compliance report in the specified format."""
    
    violations = results['violations']
    warnings = results['warnings']
    is_compliant = results['compliant']
    
    if format_type == 'json':
        return json.dumps(results, indent=2)
    
    # Text format
    report = []
    report.append("=" * 80)
    report.append("TRANSLATION SERVICE COMPLIANCE REPORT")
    report.append("=" * 80)
    report.append("")
    
    # Summary
    status = "✅ COMPLIANT" if is_compliant else "❌ NON-COMPLIANT"
    report.append(f"Status: {status}")
    report.append(f"Violations Found: {len(violations)}")
    report.append(f"Warnings: {len(warnings)}")
    report.append("")
    
    # Architecture compliance note
    report.append("Architecture Requirement:")
    report.append("• NO direct translation service calls should exist in bot code")
    report.append("• ALL translation logic must be executed within Copilot Studio agent")
    report.append("• Bot should act as pure message relay between Telegram and Copilot Studio")
    report.append("")
    
    # Violations
    if violations:
        report.append("VIOLATIONS FOUND:")
        report.append("-" * 40)
        for i, violation in enumerate(violations, 1):
            report.append(f"{i}. {violation['type']}")
            if 'file' in violation:
                report.append(f"   File: {violation['file']}")
            if 'line' in violation:
                report.append(f"   Line: {violation['line']}")
            report.append(f"   Description: {violation['description']}")
            report.append("")
    else:
        report.append("✅ NO VIOLATIONS FOUND")
        report.append("The bot correctly implements a pure relay architecture.")
        report.append("")
    
    # Warnings
    if warnings:
        report.append("WARNINGS:")
        report.append("-" * 40)
        for i, warning in enumerate(warnings, 1):
            if isinstance(warning, dict):
                report.append(f"{i}. {warning['type']}")
                if 'file' in warning:
                    report.append(f"   File: {warning['file']}")
                if 'line' in warning:
                    report.append(f"   Line: {warning['line']}")
                report.append(f"   Description: {warning['description']}")
            else:
                report.append(f"{i}. {warning}")
            report.append("")
    
    # Recommendations
    report.append("COMPLIANCE RECOMMENDATIONS:")
    report.append("-" * 40)
    if is_compliant:
        report.append("• Continue regular compliance monitoring")
        report.append("• Review dependencies before adding new packages")
        report.append("• Monitor environment variables for translation API keys")
        report.append("• Enforce code review guidelines against direct translation APIs")
    else:
        report.append("• URGENT: Remove all direct translation service integrations")
        report.append("• Move translation logic to Copilot Studio agent")
        report.append("• Update code to use pure message relay pattern")
        report.append("• Remove translation service dependencies from requirements")
    
    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(description='Translation Service Compliance Testing')
    parser.add_argument('--project-root', default='.', help='Path to project root directory')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('--output-format', choices=['text', 'json'], default='text', 
                       help='Output format for the report')
    parser.add_argument('--output-file', help='Save report to file instead of stdout')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Run compliance scan
    detector = TranslationServiceDetector(args.project_root)
    results = detector.scan_project()
    
    # Generate report
    report = generate_compliance_report(results, args.output_format)
    
    # Output report
    if args.output_file:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        logger.info(f"Report saved to {args.output_file}")
    else:
        print(report)
    
    # Exit with error code if violations found
    sys.exit(0 if results['compliant'] else 1)


if __name__ == '__main__':
    main()