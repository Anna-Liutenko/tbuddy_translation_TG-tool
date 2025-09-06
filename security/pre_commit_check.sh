#!/bin/bash
# Pre-commit Security Hook for T.Buddy Translation Tool
# Performs automated security validation before Git commits

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SECURITY_SCRIPT="$REPO_ROOT/security/validate_security.py"
TEMP_REPORT="/tmp/tbuddy_security_report_$(date +%s).json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_header() {
    echo
    echo "=================================================================="
    echo "                T.BUDDY PRE-COMMIT SECURITY CHECK"
    echo "=================================================================="
    echo
}

# Check if Python is available
check_python() {
    if ! command -v python3 &> /dev/null; then
        if ! command -v python &> /dev/null; then
            log_error "Python is not available. Please install Python 3.7+"
            exit 1
        else
            PYTHON_CMD="python"
        fi
    else
        PYTHON_CMD="python3"
    fi
    
    log_info "Using Python: $PYTHON_CMD"
}

# Check if we're in a Git repository
check_git_repo() {
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        log_error "Not in a Git repository"
        exit 1
    fi
    
    log_info "Git repository detected"
}

# Check for staged files that might contain secrets
check_staged_files() {
    log_info "Checking staged files for security risks..."
    
    # Get list of staged files
    STAGED_FILES=$(git diff --cached --name-only)
    
    if [ -z "$STAGED_FILES" ]; then
        log_warning "No staged files found"
        return 0
    fi
    
    # Check for forbidden file patterns
    FORBIDDEN_PATTERNS=(".env" "*.key" "*.pem" "*.p12" "*.pfx" "*.db" "*.sqlite" "config.json" "secrets.json")
    
    for file in $STAGED_FILES; do
        # Skip deleted files
        if [ ! -f "$REPO_ROOT/$file" ]; then
            continue
        fi
        
        # Check against forbidden patterns
        for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
            if [[ "$file" == $pattern ]] || [[ "$file" == *"$pattern" ]]; then
                # Allow template files
                if [[ "$file" == *.example ]] || [[ "$file" == ".env.testing" ]]; then
                    continue
                fi
                
                log_error "Forbidden file staged for commit: $file"
                log_error "This file type should not be committed to version control"
                return 1
            fi
        done
        
        # Check file size (warn about large files)
        FILE_SIZE=$(stat -f%z "$REPO_ROOT/$file" 2>/dev/null || stat -c%s "$REPO_ROOT/$file" 2>/dev/null || echo 0)
        if [ "$FILE_SIZE" -gt 1048576 ]; then  # 1MB
            log_warning "Large file staged: $file ($(($FILE_SIZE / 1024))KB)"
        fi
    done
    
    log_success "Staged files check passed"
    return 0
}

# Run the main security validation
run_security_validation() {
    log_info "Running comprehensive security validation..."
    
    if [ ! -f "$SECURITY_SCRIPT" ]; then
        log_error "Security validation script not found: $SECURITY_SCRIPT"
        exit 1
    fi
    
    # Run the security validation with report output
    if $PYTHON_CMD "$SECURITY_SCRIPT" --repo-path "$REPO_ROOT" --output "$TEMP_REPORT" --verbose; then
        log_success "Security validation passed"
        
        # Show summary if report exists
        if [ -f "$TEMP_REPORT" ]; then
            log_info "Security scan summary:"
            if command -v jq &> /dev/null; then
                echo "  Critical Issues: $(jq -r '.critical_issues' "$TEMP_REPORT")"
                echo "  High Issues: $(jq -r '.high_issues' "$TEMP_REPORT")"
                echo "  Medium Issues: $(jq -r '.medium_issues' "$TEMP_REPORT")"
                echo "  Warnings: $(jq -r '.warnings' "$TEMP_REPORT")"
            else
                log_info "Install 'jq' for detailed report summary"
            fi
        fi
        
        return 0
    else
        log_error "Security validation failed"
        
        # Show critical issues if report exists
        if [ -f "$TEMP_REPORT" ] && command -v jq &> /dev/null; then
            log_error "Critical issues found:"
            jq -r '.issues[] | select(.severity == "CRITICAL") | "  - \(.category): \(.description)"' "$TEMP_REPORT"
        fi
        
        return 1
    fi
}

# Check environment template synchronization
check_template_sync() {
    log_info "Checking environment template synchronization..."
    
    TEMPLATES=(".env.example" ".env.production.example" ".env.enhanced.example" ".env.testing")
    MISSING_TEMPLATES=()
    
    for template in "${TEMPLATES[@]}"; do
        if [ ! -f "$REPO_ROOT/$template" ]; then
            MISSING_TEMPLATES+=("$template")
        fi
    done
    
    if [ ${#MISSING_TEMPLATES[@]} -gt 0 ]; then
        log_error "Missing environment templates:"
        for template in "${MISSING_TEMPLATES[@]}"; do
            log_error "  - $template"
        done
        return 1
    fi
    
    # Check if any template is staged and others need updates
    STAGED_TEMPLATES=()
    for template in "${TEMPLATES[@]}"; do
        if git diff --cached --name-only | grep -q "^$template$"; then
            STAGED_TEMPLATES+=("$template")
        fi
    done
    
    if [ ${#STAGED_TEMPLATES[@]} -gt 0 ]; then
        log_info "Environment templates staged for commit:"
        for template in "${STAGED_TEMPLATES[@]}"; do
            log_info "  - $template"
        done
        
        # Recommend updating other templates if not all are staged
        if [ ${#STAGED_TEMPLATES[@]} -lt ${#TEMPLATES[@]} ]; then
            log_warning "Consider updating all environment templates when modifying any template"
        fi
    fi
    
    log_success "Template synchronization check passed"
    return 0
}

# Check Git configuration
check_git_config() {
    log_info "Checking Git configuration..."
    
    # Check if .gitignore exists and is staged
    if [ ! -f "$REPO_ROOT/.gitignore" ]; then
        log_error ".gitignore file is missing"
        return 1
    fi
    
    # Check for common .gitignore patterns
    REQUIRED_PATTERNS=(".env" "*.log" "*.db" "__pycache__" ".qoder")
    MISSING_PATTERNS=()
    
    for pattern in "${REQUIRED_PATTERNS[@]}"; do
        if ! grep -q "$pattern" "$REPO_ROOT/.gitignore"; then
            MISSING_PATTERNS+=("$pattern")
        fi
    done
    
    if [ ${#MISSING_PATTERNS[@]} -gt 0 ]; then
        log_warning "Missing .gitignore patterns:"
        for pattern in "${MISSING_PATTERNS[@]}"; do
            log_warning "  - $pattern"
        done
    fi
    
    log_success "Git configuration check passed"
    return 0
}

# Main execution
main() {
    print_header
    
    # Pre-flight checks
    check_python
    check_git_repo
    
    # Security checks
    log_info "Starting pre-commit security validation..."
    
    # 1. Check staged files
    if ! check_staged_files; then
        log_error "Staged files check failed"
        exit 1
    fi
    
    # 2. Check template synchronization
    if ! check_template_sync; then
        log_error "Template synchronization check failed"
        exit 1
    fi
    
    # 3. Check Git configuration
    if ! check_git_config; then
        log_error "Git configuration check failed"
        exit 1
    fi
    
    # 4. Run comprehensive security validation
    if ! run_security_validation; then
        log_error "Security validation failed - commit blocked"
        exit 1
    fi
    
    # Cleanup
    if [ -f "$TEMP_REPORT" ]; then
        rm -f "$TEMP_REPORT"
    fi
    
    echo
    log_success "All security checks passed - commit approved"
    echo "=================================================================="
    echo
    
    exit 0
}

# Handle script interruption
cleanup() {
    if [ -f "$TEMP_REPORT" ]; then
        rm -f "$TEMP_REPORT"
    fi
    echo
    log_warning "Pre-commit check interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function
main "$@"