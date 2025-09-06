# Windows Local Testing and Deployment Guide

## Overview

This guide provides comprehensive instructions for testing T.Buddy Translation Tool locally on Windows environments before deploying to Ubuntu servers. It covers local testing execution, git workflow validation, cross-platform compatibility verification, and secure deployment procedures.

## Prerequisites

### Windows Development Environment
- **Windows 10/11** with PowerShell 5.1 or higher
- **Python 3.9+** installed and accessible via command line
- **Git for Windows** with proper configuration
- **Visual Studio Code** or preferred IDE
- **Internet connection** for GitHub integration

### Required Python Packages
```powershell
pip install -r requirements.txt
```

### Environment Setup
1. **Clone the repository**:
   ```powershell
   git clone https://github.com/your-org/tbuddy_translation_TG-tool.git
   cd tbuddy_translation_TG-tool
   ```

2. **Create virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   ```powershell
   # Copy template and edit with your values
   Copy-Item .env.testing.example .env.testing
   notepad .env.testing
   ```

## Local Testing Framework

### 1. Framework Validation

First, validate that the testing framework is properly set up:

```powershell
# Validate testing framework
python validate_testing_framework.py
```

**Expected Output:**
```
TELEGRAM TRANSLATION BOT - TESTING FRAMEWORK VALIDATION
✅ File Structure - PASSED
✅ Module Imports - PASSED
✅ Test Configuration - PASSED
✅ Core Functionality - PASSED
✅ Test Server - PASSED
✅ Quick Test Sample - PASSED
```

### 2. Security Validation

Run security validation to ensure no secrets or sensitive data are exposed:

```powershell
# Run security validation
python security\validate_security.py --verbose
```

**Expected Output:**
```
SECURITY VALIDATION SUMMARY
Critical Issues: 0
High Issues: 0 (or only temporary files)
STATUS: PASSED
```

**If issues are found:**
- Remove any `.db`, `.log`, or `__pycache__` files
- Ensure no real secrets are in template files
- Check that `.gitignore` patterns are comprehensive

### 3. Git Status and Push Resolution

Check repository status and resolve any git push issues:

```powershell
# Check git status with actionable recommendations
python git_status_checker.py --actions --detailed
```

**Common Git Issues and Solutions:**

| Issue | Command | Description |
|-------|---------|-------------|
| **Uncommitted changes** | `git add . && git commit -m "Your message"` | Stage and commit changes |
| **Outdated branch** | `git pull --rebase origin main` | Update local branch |
| **Push conflicts** | `git fetch origin && git merge origin/main` | Resolve conflicts |
| **Authentication** | `git config --global credential.helper manager` | Update Windows credentials |

### 4. Comprehensive Testing

Run the full test suite with cross-platform validation:

```powershell
# Run all tests with verbose output
python comprehensive_test_runner.py --verbose

# Run specific test categories
python comprehensive_test_runner.py --suite comprehensive_unit_tests,integration_tests

# Quick validation (unit tests only)
python comprehensive_test_runner.py --quick
```

**Test Categories:**
- **Unit Tests**: Core functionality validation
- **Integration Tests**: Database and API testing
- **Error Simulation**: Error handling verification
- **Group Chat Tests**: Multi-user functionality
- **Message Simulation**: End-to-end workflows

### 5. Deployment Readiness Validation

Validate that the system is ready for Ubuntu deployment:

```powershell
# Comprehensive deployment validation
python validate_deployment.py --verbose
```

## Cross-Platform Testing Strategy

### Windows-Specific Considerations

| Component | Windows Handling | Ubuntu Target | Validation |
|-----------|------------------|---------------|------------|
| **File Paths** | Backslash separators | Forward slash | `pathlib.Path` usage |
| **Line Endings** | CRLF | LF | Git `autocrlf=true` |
| **Environment Variables** | Case-insensitive | Case-sensitive | Explicit variable names |
| **Database Files** | Windows paths | POSIX paths | Cross-platform testing |
| **Service Management** | Manual/IIS | Systemd | Service simulation |

### Environment Detection

The framework automatically detects the platform:

```python
import platform
if platform.system() == 'Windows':
    # Windows-specific configuration
elif platform.system() == 'Linux':
    # Ubuntu-specific configuration
```

### Path Handling

All file operations use `pathlib.Path` for cross-platform compatibility:

```python
from pathlib import Path

# Automatically handles Windows vs. Linux paths
config_path = Path(__file__).parent / 'config' / 'settings.json'
```

## Local Testing Commands

### Daily Development Workflow

```powershell
# 1. Start development session
.\venv\Scripts\Activate.ps1
python validate_testing_framework.py

# 2. Run tests during development
python comprehensive_test_runner.py --quick

# 3. Before committing changes
python security\validate_security.py
python git_status_checker.py --actions

# 4. Full validation before deployment
python comprehensive_test_runner.py --verbose
python validate_deployment.py
```

### Test Server Operations

```powershell
# Start local test server for webhook testing
python test_server.py
# Server runs on http://localhost:5000

# Test webhook endpoints
Invoke-RestMethod -Uri "http://localhost:5000/health" -Method GET
Invoke-RestMethod -Uri "http://localhost:5000/webhook" -Method POST -Body $testPayload -ContentType "application/json"
```

### Database Testing

```powershell
# Database connectivity and operations
python tests\smoke_db.py

# Database migration testing
python db.py --test

# Database cleanup (removes test databases)
Remove-Item test_chat_settings_*.db -ErrorAction SilentlyContinue
```

## Performance Monitoring

### Test Performance Metrics

The comprehensive test runner provides performance monitoring:

```json
{
  "performance_metrics": {
    "comprehensive_unit_tests": {"avg": 0.5, "min": 0.2, "max": 1.0},
    "integration_tests": {"avg": 2.1, "min": 1.5, "max": 3.2},
    "database_operations": {"avg": 0.05, "min": 0.01, "max": 0.1}
  }
}
```

### Performance Thresholds

| Operation | Windows Target | Ubuntu Target | Alert Threshold |
|-----------|----------------|---------------|-----------------|
| **Language Parsing** | < 1.0s | < 0.8s | > 2.0s |
| **Database Operations** | < 0.1s | < 0.05s | > 0.5s |
| **API Calls** | < 2.0s | < 1.5s | > 5.0s |
| **Test Suite** | < 5 min | < 3 min | > 10 min |

## Report Generation

### Test Reports

All test executions generate comprehensive reports:

```powershell
# Reports are saved to test_reports/ directory
ls test_reports\

# View HTML report
start test_reports\comprehensive_test_report_*.html

# JSON report for automation
Get-Content test_reports\comprehensive_test_report_*.json | ConvertFrom-Json
```

### Report Types

| Report | Format | Purpose |
|--------|--------|---------|
| **HTML Report** | Visual dashboard | Human-readable test results |
| **JSON Report** | Structured data | Automation and CI/CD integration |
| **Performance Report** | Metrics summary | Performance analysis |
| **Security Report** | Vulnerability scan | Security compliance |

## Troubleshooting

### Common Windows Issues

#### Unicode Logging Errors
```
UnicodeEncodeError: 'charmap' codec can't encode character
```

**Solution:**
```powershell
# Set console to UTF-8 encoding
chcp 65001
$env:PYTHONIOENCODING="utf-8"
```

#### PowerShell Execution Policy
```
cannot be loaded because running scripts is disabled
```

**Solution:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Git Line Ending Issues
```
warning: LF will be replaced by CRLF
```

**Solution:**
```powershell
git config --global core.autocrlf true
git config --global core.safecrlf false
```

#### Python Path Issues
```
'python' is not recognized as an internal or external command
```

**Solution:**
```powershell
# Add Python to PATH or use full path
$env:PATH += ";C:\Python311;C:\Python311\Scripts"
```

### Database Connectivity Issues

```powershell
# Test database operations
python -c "import db; print('Database connection: OK')"

# Reset test database
Remove-Item test_chat_settings_*.db -Force
python tests\smoke_db.py
```

### Network/API Issues

```powershell
# Test internet connectivity
Test-NetConnection -ComputerName github.com -Port 443

# Test Direct Line API (if configured)
python tools\test_directline.py

# Verify webhook connectivity
Invoke-RestMethod -Uri "https://httpbin.org/post" -Method POST -Body '{"test": "data"}' -ContentType "application/json"
```

## Security Best Practices

### Local Development Security

1. **Never commit secrets:**
   ```powershell
   # Check for accidental secrets
   python security\validate_security.py --strict
   ```

2. **Use template files:**
   - Edit `.env.testing` for local development
   - Keep templates (`.env.example`) with placeholders only

3. **Clean up regularly:**
   ```powershell
   # Remove temporary files
   Remove-Item __pycache__ -Recurse -Force -ErrorAction SilentlyContinue
   Remove-Item *.db -ErrorAction SilentlyContinue
   Remove-Item *.log -ErrorAction SilentlyContinue
   ```

### Pre-Deployment Checklist

- [ ] All tests pass with >95% success rate
- [ ] Security validation shows 0 critical issues
- [ ] Git repository is clean and synchronized
- [ ] Environment templates contain only placeholders
- [ ] No sensitive files in repository
- [ ] Cross-platform compatibility verified
- [ ] Performance meets thresholds
- [ ] Documentation is up to date

## Deployment to Ubuntu

### Pre-Deployment Validation

```powershell
# Final validation before deployment
python comprehensive_test_runner.py --verbose
python validate_deployment.py --verbose
python security\validate_security.py --strict

# Ensure git is clean
git status
git push origin main
```

### Deployment Command

```powershell
# Deploy to Ubuntu server (requires SSH access)
# Note: This runs the secure deployment script on the Ubuntu server
ssh user@your-ubuntu-server "cd /opt/tbuddy && sudo ./deploy/secure_deploy.sh"
```

### Post-Deployment Verification

```powershell
# Test deployed service
Invoke-RestMethod -Uri "https://your-domain.com/health" -Method GET

# Check service status
ssh user@your-ubuntu-server "sudo systemctl status tbuddy"
```

## Automation and CI/CD

### GitHub Actions Integration

The repository includes GitHub Actions workflows that automatically run:

1. **On Pull Request:**
   - Security validation
   - Comprehensive testing
   - Cross-platform compatibility checks

2. **On Merge to Main:**
   - Full test suite
   - Deployment readiness validation
   - Automatic deployment (if configured)

### Local CI Simulation

```powershell
# Simulate CI pipeline locally
.\scripts\ci_simulation.ps1
```

## Support and Resources

### Documentation
- [README.md](README.md) - Project overview
- [DEPLOY.md](DEPLOY.md) - Deployment procedures
- [ARCHITECTURE_COMPLIANCE_REPORT.md](ARCHITECTURE_COMPLIANCE_REPORT.md) - System architecture

### Logs and Debugging
```powershell
# View test execution logs
Get-Content test_reports\test_run_*.log | Select-Object -Last 50

# Debug specific components
$env:LOG_LEVEL="DEBUG"
python app.py --debug
```

### Performance Analysis
```powershell
# Analyze test performance
Get-Content test_reports\performance_report_*.json | ConvertFrom-Json | Select-Object performance_metrics
```

## Conclusion

This guide provides a comprehensive approach to local testing on Windows before deploying to Ubuntu servers. By following these procedures, you ensure:

- **Reliability**: Comprehensive testing reduces deployment failures
- **Security**: Validation prevents secrets exposure
- **Compatibility**: Cross-platform testing ensures Ubuntu deployment success
- **Performance**: Monitoring ensures optimal application performance
- **Maintainability**: Automated testing supports continuous development

For additional support, refer to the project documentation or contact the development team.