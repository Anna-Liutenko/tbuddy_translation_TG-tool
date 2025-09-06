#!/usr/bin/env bash
# Automated Rollback Script for T.Buddy Translation Tool
# Provides safe rollback capabilities with comprehensive backup and recovery

set -euo pipefail

# Configuration
SERVICE_NAME="tbuddy"
APP_DIR="/opt/tbuddy"
CONFIG_DIR="/etc/tbuddy"
BACKUP_DIR="/opt/backups"
LOG_DIR="/var/log/tbuddy"
ROLLBACK_LOG="/var/log/tbuddy/rollback.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$ROLLBACK_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] $1" >> "$ROLLBACK_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$ROLLBACK_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1" >> "$ROLLBACK_LOG"
}

# Initialize rollback log
init_rollback_log() {
    mkdir -p "$(dirname "$ROLLBACK_LOG")"
    touch "$ROLLBACK_LOG"
    chown tbuddy:www-data "$ROLLBACK_LOG" 2>/dev/null || true
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        log_info "Usage: sudo $0 [command]"
        exit 1
    fi
}

# Create backup before any operation
create_backup() {
    local backup_name="tbuddy-$(date +%Y%m%d-%H%M%S)"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    log_info "Creating backup: $backup_name"
    
    mkdir -p "$BACKUP_DIR"
    
    # Create backup directory
    mkdir -p "$backup_path"
    
    # Backup application directory
    if [[ -d "$APP_DIR" ]]; then
        cp -r "$APP_DIR" "$backup_path/app"
        log_info "Application directory backed up"
    fi
    
    # Backup configuration (but not secrets)
    if [[ -d "$CONFIG_DIR" ]]; then
        mkdir -p "$backup_path/config"
        # Only backup non-sensitive config files
        find "$CONFIG_DIR" -name "*.conf" -o -name "*.yaml" -o -name "*.json" | while read -r file; do
            if [[ -f "$file" ]]; then
                cp "$file" "$backup_path/config/"
            fi
        done
        log_info "Configuration backed up (excluding secrets)"
    fi
    
    # Backup systemd service file
    if [[ -f "/etc/systemd/system/$SERVICE_NAME.service" ]]; then
        cp "/etc/systemd/system/$SERVICE_NAME.service" "$backup_path/"
        log_info "Systemd service file backed up"
    fi
    
    # Backup nginx configuration
    if [[ -f "/etc/nginx/sites-available/$SERVICE_NAME" ]]; then
        cp "/etc/nginx/sites-available/$SERVICE_NAME" "$backup_path/"
        log_info "Nginx configuration backed up"
    fi
    
    # Create backup metadata
    cat > "$backup_path/metadata.json" <<EOF
{
    "backup_name": "$backup_name",
    "timestamp": "$(date -Iseconds)",
    "service_status": "$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || echo 'unknown')",
    "git_commit": "$(cd "$APP_DIR" 2>/dev/null && git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "python_version": "$(cd "$APP_DIR" 2>/dev/null && ./venv/bin/python --version 2>/dev/null || echo 'unknown')",
    "backup_size": "$(du -sh "$backup_path" | cut -f1)"
}
EOF
    
    log_success "Backup created: $backup_path"
    echo "$backup_path"
}

# List available backups
list_backups() {
    log_info "Available backups:"
    
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_warning "No backup directory found"
        return 1
    fi
    
    local backups
    backups=$(find "$BACKUP_DIR" -maxdepth 1 -name "tbuddy-*" -type d | sort -r)
    
    if [[ -z "$backups" ]]; then
        log_warning "No backups found"
        return 1
    fi
    
    echo
    printf "%-25s %-20s %-15s %s\n" "BACKUP NAME" "TIMESTAMP" "SIZE" "STATUS"
    echo "------------------------------------------------------------------------"
    
    echo "$backups" | while read -r backup_path; do
        local backup_name
        backup_name=$(basename "$backup_path")
        
        local backup_size
        backup_size=$(du -sh "$backup_path" 2>/dev/null | cut -f1)
        
        local timestamp
        timestamp=$(echo "$backup_name" | cut -d'-' -f2-3 | sed 's/-/ /')
        
        local status="Available"
        if [[ -f "$backup_path/metadata.json" ]]; then
            if command -v jq > /dev/null; then
                status=$(jq -r '.service_status' "$backup_path/metadata.json" 2>/dev/null || echo "Available")
            fi
        fi
        
        printf "%-25s %-20s %-15s %s\n" "$backup_name" "$timestamp" "$backup_size" "$status"
    done
    
    echo
}

# Validate backup before restore
validate_backup() {
    local backup_path="$1"
    
    log_info "Validating backup: $(basename "$backup_path")"
    
    # Check if backup directory exists
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup directory not found: $backup_path"
        return 1
    fi
    
    # Check if backup contains application files
    if [[ ! -d "$backup_path/app" ]]; then
        log_error "Backup does not contain application directory"
        return 1
    fi
    
    # Check for essential files
    local essential_files=("app/app.py" "app/requirements.txt")
    for file in "${essential_files[@]}"; do
        if [[ ! -f "$backup_path/$file" ]]; then
            log_error "Essential file missing from backup: $file"
            return 1
        fi
    done
    
    # Check backup metadata
    if [[ -f "$backup_path/metadata.json" ]]; then
        if command -v jq > /dev/null; then
            if ! jq . "$backup_path/metadata.json" > /dev/null 2>&1; then
                log_warning "Backup metadata is corrupted"
            else
                log_info "Backup metadata is valid"
            fi
        fi
    else
        log_warning "Backup metadata not found"
    fi
    
    log_success "Backup validation passed"
    return 0
}

# Stop service safely
stop_service() {
    log_info "Stopping service: $SERVICE_NAME"
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        systemctl stop "$SERVICE_NAME"
        
        # Wait for service to stop
        local timeout=30
        local count=0
        while systemctl is-active --quiet "$SERVICE_NAME" && [[ $count -lt $timeout ]]; do
            sleep 1
            ((count++))
        done
        
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            log_error "Service did not stop within $timeout seconds"
            return 1
        else
            log_success "Service stopped successfully"
        fi
    else
        log_info "Service is already stopped"
    fi
    
    return 0
}

# Start service
start_service() {
    log_info "Starting service: $SERVICE_NAME"
    
    systemctl start "$SERVICE_NAME"
    
    # Wait for service to start
    local timeout=30
    local count=0
    while ! systemctl is-active --quiet "$SERVICE_NAME" && [[ $count -lt $timeout ]]; do
        sleep 1
        ((count++))
    done
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service started successfully"
        return 0
    else
        log_error "Service failed to start within $timeout seconds"
        systemctl status "$SERVICE_NAME" --no-pager
        return 1
    fi
}

# Restore application from backup
restore_application() {
    local backup_path="$1"
    
    log_info "Restoring application from backup: $(basename "$backup_path")"
    
    # Remove current application (but preserve environment config)
    if [[ -d "$APP_DIR" ]]; then
        # Preserve virtual environment if it exists
        if [[ -d "$APP_DIR/venv" ]]; then
            log_info "Preserving virtual environment"
            mv "$APP_DIR/venv" "/tmp/tbuddy_venv_backup"
        fi
        
        rm -rf "$APP_DIR"/*
    fi
    
    # Restore application files
    cp -r "$backup_path/app"/* "$APP_DIR/"
    
    # Restore virtual environment if it was preserved
    if [[ -d "/tmp/tbuddy_venv_backup" ]]; then
        mv "/tmp/tbuddy_venv_backup" "$APP_DIR/venv"
        log_info "Virtual environment restored"
    fi
    
    # Set proper ownership
    chown -R tbuddy:www-data "$APP_DIR"
    
    # Restore systemd service if backup contains it
    if [[ -f "$backup_path/$SERVICE_NAME.service" ]]; then
        cp "$backup_path/$SERVICE_NAME.service" "/etc/systemd/system/"
        systemctl daemon-reload
        log_info "Systemd service configuration restored"
    fi
    
    # Restore nginx configuration if backup contains it
    if [[ -f "$backup_path/$SERVICE_NAME" ]]; then
        cp "$backup_path/$SERVICE_NAME" "/etc/nginx/sites-available/"
        nginx -t
        log_info "Nginx configuration restored"
    fi
    
    log_success "Application restored successfully"
}

# Perform health check after rollback
post_rollback_health_check() {
    log_info "Performing post-rollback health check..."
    
    # Wait a moment for service to fully initialize
    sleep 5
    
    local health_issues=0
    
    # Check service status
    if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        log_error "Service is not running after rollback"
        ((health_issues++))
    fi
    
    # Check if port is listening
    if ! netstat -tuln 2>/dev/null | grep -q ":8080" && ! ss -tuln 2>/dev/null | grep -q ":8080"; then
        log_error "Application is not listening on port 8080"
        ((health_issues++))
    fi
    
    # Check health endpoint if available
    if command -v curl > /dev/null; then
        if ! curl -s --max-time 10 http://localhost:8080/health > /dev/null; then
            log_warning "Health endpoint is not responding"
        else
            log_success "Health endpoint is responding"
        fi
    fi
    
    if [[ $health_issues -eq 0 ]]; then
        log_success "Post-rollback health check passed"
        return 0
    else
        log_error "Post-rollback health check failed ($health_issues issues)"
        return 1
    fi
}

# Interactive rollback selection
interactive_rollback() {
    log_info "Starting interactive rollback process..."
    
    # List available backups
    list_backups
    
    echo
    read -p "Enter backup name to restore (or 'cancel' to abort): " backup_name
    
    if [[ "$backup_name" == "cancel" ]]; then
        log_info "Rollback cancelled by user"
        return 0
    fi
    
    local backup_path="$BACKUP_DIR/$backup_name"
    
    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup not found: $backup_name"
        return 1
    fi
    
    # Show backup details
    if [[ -f "$backup_path/metadata.json" ]] && command -v jq > /dev/null; then
        echo
        log_info "Backup details:"
        jq . "$backup_path/metadata.json"
        echo
    fi
    
    read -p "Are you sure you want to rollback to this backup? (yes/no): " confirm
    
    if [[ "$confirm" != "yes" ]]; then
        log_info "Rollback cancelled by user"
        return 0
    fi
    
    # Perform rollback
    rollback_to_backup "$backup_path"
}

# Rollback to specific backup
rollback_to_backup() {
    local backup_path="$1"
    
    log_info "Starting rollback to: $(basename "$backup_path")"
    
    # Validate backup
    if ! validate_backup "$backup_path"; then
        log_error "Backup validation failed"
        return 1
    fi
    
    # Create a backup of current state before rollback
    local pre_rollback_backup
    pre_rollback_backup=$(create_backup)
    log_info "Pre-rollback backup created: $(basename "$pre_rollback_backup")"
    
    # Stop service
    if ! stop_service; then
        log_error "Failed to stop service"
        return 1
    fi
    
    # Restore application
    if ! restore_application "$backup_path"; then
        log_error "Failed to restore application"
        
        # Attempt to restore from pre-rollback backup
        log_info "Attempting to restore from pre-rollback backup..."
        restore_application "$pre_rollback_backup"
        start_service
        return 1
    fi
    
    # Start service
    if ! start_service; then
        log_error "Failed to start service after rollback"
        
        # Attempt to restore from pre-rollback backup
        log_info "Attempting to restore from pre-rollback backup..."
        restore_application "$pre_rollback_backup"
        start_service
        return 1
    fi
    
    # Perform health check
    if post_rollback_health_check; then
        log_success "Rollback completed successfully!"
        
        # Update webhook if nginx is configured
        if systemctl is-active --quiet nginx; then
            systemctl reload nginx
        fi
        
        return 0
    else
        log_error "Rollback completed but health check failed"
        return 1
    fi
}

# Auto rollback (rollback to most recent backup)
auto_rollback() {
    log_info "Starting automatic rollback to most recent backup..."
    
    local latest_backup
    latest_backup=$(find "$BACKUP_DIR" -maxdepth 1 -name "tbuddy-*" -type d | sort -r | head -1)
    
    if [[ -z "$latest_backup" ]]; then
        log_error "No backups found for automatic rollback"
        return 1
    fi
    
    log_info "Rolling back to: $(basename "$latest_backup")"
    rollback_to_backup "$latest_backup"
}

# Clean old backups
clean_old_backups() {
    local keep_count="${1:-10}"
    
    log_info "Cleaning old backups (keeping $keep_count most recent)..."
    
    local backups
    backups=$(find "$BACKUP_DIR" -maxdepth 1 -name "tbuddy-*" -type d | sort -r)
    
    local backup_count
    backup_count=$(echo "$backups" | wc -l)
    
    if [[ $backup_count -le $keep_count ]]; then
        log_info "No old backups to clean ($backup_count <= $keep_count)"
        return 0
    fi
    
    local to_remove
    to_remove=$(echo "$backups" | tail -n +$((keep_count + 1)))
    
    echo "$to_remove" | while read -r backup_path; do
        log_info "Removing old backup: $(basename "$backup_path")"
        rm -rf "$backup_path"
    done
    
    log_success "Old backups cleaned"
}

# Show usage
show_usage() {
    echo "Usage: $0 [command] [options]"
    echo
    echo "Commands:"
    echo "  backup                     Create backup of current state"
    echo "  list                       List available backups"
    echo "  rollback [backup_name]     Rollback to specific backup (interactive if no name)"
    echo "  auto                       Rollback to most recent backup"
    echo "  clean [keep_count]         Clean old backups (default: keep 10)"
    echo "  validate <backup_name>     Validate specific backup"
    echo
    echo "Examples:"
    echo "  $0 backup                  # Create backup"
    echo "  $0 list                    # List backups"
    echo "  $0 rollback                # Interactive rollback"
    echo "  $0 rollback tbuddy-20231206-143022  # Rollback to specific backup"
    echo "  $0 auto                    # Auto rollback to latest"
    echo "  $0 clean 5                 # Keep only 5 most recent backups"
    echo
}

# Main script logic
main() {
    # Initialize logging
    init_rollback_log
    
    case "${1:-help}" in
        "backup")
            check_root
            create_backup
            ;;
        "list")
            list_backups
            ;;
        "rollback")
            check_root
            if [[ -n "${2:-}" ]]; then
                rollback_to_backup "$BACKUP_DIR/$2"
            else
                interactive_rollback
            fi
            ;;
        "auto")
            check_root
            auto_rollback
            ;;
        "clean")
            check_root
            clean_old_backups "${2:-10}"
            ;;
        "validate")
            if [[ -z "${2:-}" ]]; then
                log_error "Backup name required for validation"
                show_usage
                exit 1
            fi
            validate_backup "$BACKUP_DIR/$2"
            ;;
        "help"|"-h"|"--help")
            show_usage
            ;;
        *)
            log_error "Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Handle script interruption
cleanup() {
    echo
    log_warning "Rollback script interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function
main "$@"