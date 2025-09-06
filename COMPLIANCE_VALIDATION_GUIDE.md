# Translation Service Compliance Validation Guide

## Overview

This guide explains how to use the automated validation tools to ensure the Telegram bot maintains compliance with the architectural requirement that **NO direct translation service calls should exist in the bot code**.

## Validation Tools

### 1. Compliance Test Script (`compliance_test.py`)

**Purpose:** Comprehensive static analysis of the codebase to detect translation service integrations.

**Usage:**
```bash
# Basic compliance check
python compliance_test.py

# JSON output for CI/CD integration
python compliance_test.py --output-format json

# Save report to file
python compliance_test.py --output-file compliance_report.txt

# Verbose mode for debugging
python compliance_test.py --verbose
```

**What it checks:**
- Python import statements for translation services
- Function and variable names suggesting translation logic
- String literals containing translation API endpoints
- Dependencies in requirements.txt and other dependency files
- Configuration files for translation service references

### 2. Dependency Auditor (`dependency_auditor.py`)

**Purpose:** Continuous monitoring of dependencies and code changes for translation service violations.

**Usage:**
```bash
# One-time dependency check
python dependency_auditor.py --mode check

# Continuous monitoring (checks every 5 minutes)
python dependency_auditor.py --mode monitor --interval 300

# Git pre-commit hook integration
python dependency_auditor.py --mode git-hook

# CI/CD pipeline integration
python dependency_auditor.py --mode ci --output-format json
```

**What it monitors:**
- New package dependencies in requirements files
- Python file changes that might introduce violations
- Git commit messages for suspicious patterns
- File modification timestamps for change detection

### 3. Environment Variable Scanner (`env_scanner.py`)

**Purpose:** Scan environment variables and configuration files for translation service API keys.

**Usage:**
```bash
# Basic environment scan
python env_scanner.py

# Include .env files in scan
python env_scanner.py --scan-files

# Continuous monitoring of environment changes
python env_scanner.py --monitor --interval 60

# JSON output
python env_scanner.py --output-format json
```

**What it detects:**
- Translation service API keys in environment variables
- Suspicious environment variable patterns
- API keys in .env files and configuration files
- Encoded or obfuscated credentials

## Integration with Development Workflow

### Pre-Commit Hook Setup

Add this to your `.git/hooks/pre-commit` file:

```bash
#!/bin/bash
echo "Running translation service compliance check..."
python dependency_auditor.py --mode git-hook
if [ $? -ne 0 ]; then
    echo "❌ COMMIT REJECTED: Translation service violations detected!"
    exit 1
fi
echo "✅ Compliance check passed"
```

### CI/CD Pipeline Integration

**GitHub Actions Example (`.github/workflows/compliance.yml`):**

```yaml
name: Translation Service Compliance Check

on: [push, pull_request]

jobs:
  compliance:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    
    - name: Install dependencies
      run: pip install -r requirements.txt
    
    - name: Run compliance tests
      run: |
        python compliance_test.py --output-format json
        python dependency_auditor.py --mode ci
        python env_scanner.py --output-format json
```

### Local Development Integration

**Add to your development setup script:**

```bash
# Run all compliance checks
echo "🔍 Running translation service compliance validation..."

echo "1. Code compliance check..."
python compliance_test.py
if [ $? -ne 0 ]; then
    echo "❌ Code compliance failed!"
    exit 1
fi

echo "2. Dependency audit..."
python dependency_auditor.py --mode check
if [ $? -ne 0 ]; then
    echo "❌ Dependency audit failed!"
    exit 1
fi

echo "3. Environment variable scan..."
python env_scanner.py --scan-files
if [ $? -ne 0 ]; then
    echo "❌ Environment scan failed!"
    exit 1
fi

echo "✅ All compliance checks passed!"
```

## Expected Results

### ✅ Compliant Project

When the project is compliant, you should see:

```
Status: ✅ COMPLIANT
Violations Found: 0
Warnings: 0

✅ NO VIOLATIONS FOUND
The bot correctly implements a pure relay architecture.
```

### ❌ Non-Compliant Project

If violations are detected:

```
Status: ❌ NON-COMPLIANT
Violations Found: X
Warnings: Y

VIOLATIONS FOUND:
1. FORBIDDEN_IMPORT
   File: example.py
   Line: 10
   Description: Direct import of translation service: googletrans
```

## Understanding Warning Types

### Violations (Must Fix)
- `FORBIDDEN_IMPORT`: Direct import of translation service
- `FORBIDDEN_FROM_IMPORT`: Import from translation service module
- `FORBIDDEN_DEPENDENCY`: Translation service in requirements.txt
- `TRANSLATION_API_ENDPOINT`: Translation service URL detected
- `TRANSLATION_ENV_VAR`: Translation API key in environment

### Warnings (Should Review)
- `SUSPICIOUS_FUNCTION_NAME`: Function name suggests translation logic
- `SUSPICIOUS_VARIABLE_NAME`: Variable name suggests translation service
- `SUSPICIOUS_METHOD_CALL`: Method call might be translation-related
- `SUSPICIOUS_ENV_VAR_PATTERN`: Environment variable matches suspicious pattern

## Quick Reference Commands

```bash
# Daily development check
python compliance_test.py

# Before committing changes
python dependency_auditor.py --mode check

# After environment changes
python env_scanner.py --scan-files

# Full comprehensive check
python compliance_test.py && \
python dependency_auditor.py --mode check && \
python env_scanner.py --scan-files

# JSON output for automation
python compliance_test.py --output-format json > compliance.json
python dependency_auditor.py --mode ci --output-format json > audit.json
python env_scanner.py --output-format json > env_scan.json
```

## Troubleshooting

### False Positives

If the tools flag legitimate code:

1. **Validation Scripts:** The tools automatically exclude themselves (compliance_test.py, dependency_auditor.py, env_scanner.py)
2. **Test Files:** Add test files to the exclusion list in the validation scripts
3. **Comments:** The tools ignore comments and example code

### Script Failures

1. **Python Version:** Ensure Python 3.7+ is installed
2. **Permissions:** Check file read permissions
3. **Dependencies:** No additional dependencies required beyond standard library

### Monitoring Issues

1. **Background Monitoring:** Use `--interval` to adjust monitoring frequency
2. **System Resources:** Monitor CPU usage with continuous scanning
3. **Log Files:** Check application logs for detailed error information

## Architecture Compliance Summary

The validation tools verify compliance with the core architectural requirement:

> **All translation logic must be executed within the Copilot Studio agent. The bot should act as a pure message relay between Telegram and Copilot Studio.**

By using these tools regularly, you ensure the project maintains its clean architecture and prevents accidental introduction of direct translation service integrations.