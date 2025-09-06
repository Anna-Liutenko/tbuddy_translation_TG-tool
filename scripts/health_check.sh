#!/usr/bin/env bash
# Health Check and Monitoring Script for T.Buddy Translation Tool
# Comprehensive health validation and monitoring utilities

set -euo pipefail

# Configuration
SERVICE_NAME="tbuddy"
APP_DIR="/opt/tbuddy"
CONFIG_DIR="/etc/tbuddy"
LOG_DIR="/var/log/tbuddy"
HEALTH_LOG="/var/log/tbuddy/health.log"
WEBHOOK_TIMEOUT=10
MAX_RETRIES=3

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$HEALTH_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] $1" >> "$HEALTH_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$HEALTH_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1" >> "$HEALTH_LOG"
}

# Initialize health log
init_health_log() {
    mkdir -p "$(dirname "$HEALTH_LOG")"
    touch "$HEALTH_LOG"
    chown tbuddy:www-data "$HEALTH_LOG" 2>/dev/null || true
}

# Check systemd service status
check_service_status() {
    log_info "Checking systemd service status..."
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service is active and running"
        return 0
    else
        log_error "Service is not active"
        systemctl status "$SERVICE_NAME" --no-pager
        return 1
    fi
}

# Check if application is listening on expected port
check_port_listening() {
    log_info "Checking if application is listening on port 8080..."
    
    if netstat -tuln 2>/dev/null | grep -q ":8080" || ss -tuln 2>/dev/null | grep -q ":8080"; then
        log_success "Application is listening on port 8080"
        return 0
    else
        log_error "Application is not listening on port 8080"
        return 1
    fi
}

# Check HTTP health endpoint
check_health_endpoint() {
    log_info "Checking HTTP health endpoint..."
    
    local response_code
    local retry_count=0
    
    while [[ $retry_count -lt $MAX_RETRIES ]]; do
        if response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$WEBHOOK_TIMEOUT" http://localhost:8080/health 2>/dev/null); then
            if [[ "$response_code" == "200" ]]; then
                log_success "Health endpoint responding with HTTP 200"
                return 0
            else
                log_warning "Health endpoint responding with HTTP $response_code"
            fi
        else
            log_warning "Health endpoint request failed (attempt $((retry_count + 1))/$MAX_RETRIES)"
        fi
        
        ((retry_count++))
        if [[ $retry_count -lt $MAX_RETRIES ]]; then
            sleep 2
        fi
    done
    
    log_error "Health endpoint check failed after $MAX_RETRIES attempts"
    return 1
}

# Check database connectivity
check_database() {
    log_info "Checking database connectivity..."
    
    local db_file="$APP_DIR/chat_settings.db"
    
    if [[ -f "$db_file" ]]; then
        if [[ -r "$db_file" && -w "$db_file" ]]; then
            log_success "Database file is accessible"
            
            # Check if database is not corrupted
            if sqlite3 "$db_file" "PRAGMA integrity_check;" | grep -q "ok"; then
                log_success "Database integrity check passed"
                return 0
            else
                log_error "Database integrity check failed"
                return 1
            fi
        else
            log_error "Database file has incorrect permissions"
            return 1
        fi
    else
        log_warning "Database file not found - may be created on first use"
        return 0
    fi
}

# Check disk space
check_disk_space() {
    log_info "Checking disk space..."
    
    local app_usage
    local log_usage
    
    app_usage=$(du -sh "$APP_DIR" 2>/dev/null | cut -f1)
    log_usage=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
    
    log_info "Application directory usage: $app_usage"
    log_info "Log directory usage: $log_usage"
    
    # Check available space on root filesystem
    local available_space
    available_space=$(df / | awk 'NR==2 {print $4}')
    local available_mb=$((available_space / 1024))
    
    if [[ $available_mb -lt 1024 ]]; then  # Less than 1GB
        log_error "Low disk space: ${available_mb}MB available"
        return 1
    elif [[ $available_mb -lt 5120 ]]; then  # Less than 5GB
        log_warning "Disk space getting low: ${available_mb}MB available"
    else
        log_success "Disk space is adequate: ${available_mb}MB available"
    fi
    
    return 0
}

# Check memory usage
check_memory_usage() {
    log_info "Checking memory usage..."
    
    local service_pid
    if service_pid=$(systemctl show -p MainPID "$SERVICE_NAME" | cut -d'=' -f2) && [[ "$service_pid" != "0" ]]; then
        local memory_kb
        memory_kb=$(ps -o rss= -p "$service_pid" 2>/dev/null | tr -d ' ')
        
        if [[ -n "$memory_kb" ]]; then
            local memory_mb=$((memory_kb / 1024))
            log_info "Service memory usage: ${memory_mb}MB"
            
            if [[ $memory_mb -gt 1024 ]]; then  # More than 1GB
                log_warning "High memory usage: ${memory_mb}MB"
            else
                log_success "Memory usage is normal: ${memory_mb}MB"
            fi
        else
            log_warning "Could not determine memory usage"
        fi
    else
        log_warning "Could not find service process"
    fi
    
    # Check system memory
    local total_mem available_mem
    total_mem=$(free -m | awk 'NR==2{print $2}')
    available_mem=$(free -m | awk 'NR==2{print $7}')
    
    local mem_usage_percent=$(( (total_mem - available_mem) * 100 / total_mem ))
    
    log_info "System memory usage: ${mem_usage_percent}% (${available_mem}MB available)"
    
    if [[ $mem_usage_percent -gt 90 ]]; then
        log_error "Critical memory usage: ${mem_usage_percent}%"
        return 1
    elif [[ $mem_usage_percent -gt 80 ]]; then
        log_warning "High memory usage: ${mem_usage_percent}%"
    fi
    
    return 0
}

# Check log files for errors
check_logs_for_errors() {
    log_info "Checking recent logs for errors..."
    
    local error_count
    local recent_logs
    
    # Check systemd journal for recent errors
    if recent_logs=$(journalctl -u "$SERVICE_NAME" --since "1 hour ago" --no-pager -q); then
        error_count=$(echo "$recent_logs" | grep -c -i "error\|exception\|traceback\|failed" || true)
        
        if [[ $error_count -gt 0 ]]; then
            log_warning "Found $error_count error(s) in recent logs"
            echo "$recent_logs" | grep -i "error\|exception\|traceback\|failed" | tail -5
        else
            log_success "No errors found in recent logs"
        fi
    else
        log_warning "Could not read systemd journal"
    fi
    
    return 0
}

# Check external dependencies
check_external_dependencies() {
    log_info "Checking external dependencies..."
    
    # Check Telegram API connectivity
    if curl -s --max-time "$WEBHOOK_TIMEOUT" "https://api.telegram.org/bot" > /dev/null; then
        log_success "Telegram API is reachable"
    else
        log_error "Telegram API is not reachable"
        return 1
    fi
    
    # Check if we can resolve DNS
    if nslookup api.telegram.org > /dev/null 2>&1; then
        log_success "DNS resolution is working"
    else
        log_error "DNS resolution is not working"
        return 1
    fi
    
    return 0
}

# Check SSL certificate
check_ssl_certificate() {
    log_info "Checking SSL certificate..."
    
    local domain
    if domain=$(grep -o "server_name [^;]*" /etc/nginx/sites-enabled/tbuddy 2>/dev/null | awk '{print $2}'); then
        if [[ "$domain" != "_" && "$domain" != "localhost" ]]; then
            local cert_expiry
            if cert_expiry=$(echo | openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | openssl x509 -noout -dates | grep notAfter | cut -d= -f2); then
                local expiry_epoch
                expiry_epoch=$(date -d "$cert_expiry" +%s)
                local current_epoch
                current_epoch=$(date +%s)
                local days_until_expiry=$(( (expiry_epoch - current_epoch) / 86400 ))
                
                if [[ $days_until_expiry -lt 7 ]]; then
                    log_error "SSL certificate expires in $days_until_expiry days"
                    return 1
                elif [[ $days_until_expiry -lt 30 ]]; then
                    log_warning "SSL certificate expires in $days_until_expiry days"
                else
                    log_success "SSL certificate is valid for $days_until_expiry days"
                fi
            else
                log_error "Could not check SSL certificate for $domain"
                return 1
            fi
        else
            log_info "No domain configured for SSL check"
        fi
    else
        log_info "No nginx configuration found for SSL check"
    fi
    
    return 0
}

# Comprehensive health check
comprehensive_health_check() {
    log_info "Starting comprehensive health check..."
    
    local checks_passed=0
    local total_checks=8
    
    # Initialize health log
    init_health_log
    
    echo
    echo "=================================================================="
    echo "              T.BUDDY HEALTH CHECK REPORT"
    echo "=================================================================="
    echo
    
    # Run all health checks
    if check_service_status; then ((checks_passed++)); fi
    echo
    
    if check_port_listening; then ((checks_passed++)); fi
    echo
    
    if check_health_endpoint; then ((checks_passed++)); fi
    echo
    
    if check_database; then ((checks_passed++)); fi
    echo
    
    if check_disk_space; then ((checks_passed++)); fi
    echo
    
    if check_memory_usage; then ((checks_passed++)); fi
    echo
    
    if check_logs_for_errors; then ((checks_passed++)); fi
    echo
    
    if check_external_dependencies; then ((checks_passed++)); fi
    echo
    
    check_ssl_certificate
    echo
    
    # Summary
    echo "=================================================================="
    echo "                    HEALTH CHECK SUMMARY"
    echo "=================================================================="
    echo "Checks passed: $checks_passed/$total_checks"
    
    if [[ $checks_passed -eq $total_checks ]]; then
        log_success "All health checks passed - system is healthy"
        return 0
    elif [[ $checks_passed -ge $((total_checks * 3 / 4)) ]]; then
        log_warning "Most health checks passed - system has minor issues"
        return 1
    else
        log_error "Multiple health checks failed - system needs attention"
        return 2
    fi
}

# Quick health check (subset of comprehensive check)
quick_health_check() {
    log_info "Starting quick health check..."
    
    local issues=0
    
    if ! check_service_status; then ((issues++)); fi
    if ! check_port_listening; then ((issues++)); fi
    if ! check_health_endpoint; then ((issues++)); fi
    
    if [[ $issues -eq 0 ]]; then
        log_success "Quick health check passed"
        return 0
    else
        log_error "Quick health check failed ($issues issues found)"
        return 1
    fi
}

# Continuous monitoring mode
continuous_monitoring() {
    log_info "Starting continuous monitoring mode (Ctrl+C to stop)..."
    
    local check_interval=60  # seconds
    local consecutive_failures=0
    local max_consecutive_failures=3
    
    while true; do
        if quick_health_check; then
            consecutive_failures=0
        else
            ((consecutive_failures++))
            
            if [[ $consecutive_failures -ge $max_consecutive_failures ]]; then
                log_error "Service has failed $consecutive_failures consecutive health checks"
                log_error "Consider restarting the service or investigating the issue"
                
                # Optional: Auto-restart service
                if [[ "${AUTO_RESTART:-false}" == "true" ]]; then
                    log_info "Auto-restarting service..."
                    systemctl restart "$SERVICE_NAME"
                    consecutive_failures=0
                fi
            fi
        fi
        
        sleep $check_interval
    done
}

# Show service logs
show_logs() {
    local lines="${1:-50}"
    log_info "Showing last $lines lines of service logs..."
    journalctl -u "$SERVICE_NAME" -n "$lines" --no-pager
}

# Show detailed service status
show_status() {
    log_info "Showing detailed service status..."
    echo
    systemctl status "$SERVICE_NAME" --no-pager -l
    echo
    log_info "Recent log entries:"
    journalctl -u "$SERVICE_NAME" -n 10 --no-pager
}

# Generate health report
generate_health_report() {
    local report_file="/tmp/tbuddy_health_report_$(date +%Y%m%d_%H%M%S).json"
    
    log_info "Generating health report: $report_file"
    
    # Run comprehensive check and capture output
    local health_status=0
    comprehensive_health_check > /tmp/health_check_output.log 2>&1 || health_status=$?
    
    # Create JSON report
    cat > "$report_file" <<EOF
{
    "timestamp": "$(date -Iseconds)",
    "service_name": "$SERVICE_NAME",
    "health_status": $health_status,
    "checks": {
        "service_active": $(systemctl is-active --quiet "$SERVICE_NAME" && echo "true" || echo "false"),
        "port_listening": $(netstat -tuln 2>/dev/null | grep -q ":8080" && echo "true" || echo "false"),
        "disk_space_mb": $(df / | awk 'NR==2 {print $4}' | xargs -I {} expr {} / 1024),
        "database_exists": $([[ -f "$APP_DIR/chat_settings.db" ]] && echo "true" || echo "false")
    },
    "system_info": {
        "uptime": "$(uptime -p 2>/dev/null || echo 'unknown')",
        "load_average": "$(uptime | awk -F'load average:' '{print $2}' | xargs)",
        "memory_usage_percent": $(free | awk 'NR==2{printf "%.1f", $3*100/$2}')
    }
}
EOF
    
    log_success "Health report generated: $report_file"
    
    if command -v jq > /dev/null; then
        jq . "$report_file"
    else
        cat "$report_file"
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [command] [options]"
    echo
    echo "Commands:"
    echo "  check, health    Comprehensive health check (default)"
    echo "  quick           Quick health check"
    echo "  monitor         Continuous monitoring mode"
    echo "  logs [lines]    Show service logs (default: 50 lines)"
    echo "  status          Show detailed service status"
    echo "  report          Generate JSON health report"
    echo
    echo "Examples:"
    echo "  $0 check        # Comprehensive health check"
    echo "  $0 quick        # Quick health check"
    echo "  $0 monitor      # Continuous monitoring"
    echo "  $0 logs 100     # Show last 100 log lines"
    echo "  $0 report       # Generate health report"
    echo
    echo "Environment variables:"
    echo "  AUTO_RESTART=true   Enable auto-restart in monitor mode"
    echo
}

# Main script logic
main() {
    case "${1:-check}" in
        "check"|"health")
            comprehensive_health_check
            ;;
        "quick")
            quick_health_check
            ;;
        "monitor")
            continuous_monitoring
            ;;
        "logs")
            show_logs "${2:-50}"
            ;;
        "status")
            show_status
            ;;
        "report")
            generate_health_report
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
    log_warning "Health check interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function
main "$@"