#!/usr/bin/env bash
# Monitoring and Maintenance Utilities for T.Buddy Translation Tool
# Comprehensive monitoring, maintenance, and operational utilities

set -euo pipefail

# Configuration
SERVICE_NAME="tbuddy"
APP_DIR="/opt/tbuddy"
CONFIG_DIR="/etc/tbuddy"
LOG_DIR="/var/log/tbuddy"
DATA_DIR="/var/lib/tbuddy"
MONITORING_LOG="/var/log/tbuddy/monitoring.log"
METRICS_FILE="/var/log/tbuddy/metrics.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [INFO] $1" >> "$MONITORING_LOG"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [WARNING] $1" >> "$MONITORING_LOG"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [ERROR] $1" >> "$MONITORING_LOG"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUCCESS] $1" >> "$MONITORING_LOG"
}

# Initialize monitoring log
init_monitoring_log() {
    mkdir -p "$(dirname "$MONITORING_LOG")"
    touch "$MONITORING_LOG"
    chown tbuddy:www-data "$MONITORING_LOG" 2>/dev/null || true
}

# Collect system metrics
collect_system_metrics() {
    local timestamp
    timestamp=$(date -Iseconds)
    
    # CPU usage
    local cpu_usage
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    
    # Memory usage
    local memory_total memory_used memory_available
    memory_total=$(free -m | awk 'NR==2{print $2}')
    memory_used=$(free -m | awk 'NR==2{print $3}')
    memory_available=$(free -m | awk 'NR==2{print $7}')
    
    # Disk usage
    local disk_total disk_used disk_available
    disk_total=$(df / | awk 'NR==2{print $2}')
    disk_used=$(df / | awk 'NR==2{print $3}')
    disk_available=$(df / | awk 'NR==2{print $4}')
    
    # Load average
    local load_1m load_5m load_15m
    read -r load_1m load_5m load_15m < /proc/loadavg
    
    # Service-specific metrics
    local service_status="unknown"
    local service_memory=0
    local service_pid=0
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        service_status="active"
        service_pid=$(systemctl show -p MainPID "$SERVICE_NAME" | cut -d'=' -f2)
        
        if [[ "$service_pid" != "0" ]]; then
            service_memory=$(ps -o rss= -p "$service_pid" 2>/dev/null | tr -d ' ' || echo "0")
            service_memory=$((service_memory / 1024))  # Convert to MB
        fi
    elif systemctl is-failed --quiet "$SERVICE_NAME"; then
        service_status="failed"
    else
        service_status="inactive"
    fi
    
    # Network connections
    local connections_8080=0
    if command -v ss > /dev/null; then
        connections_8080=$(ss -tn | grep ":8080 " | wc -l)
    elif command -v netstat > /dev/null; then
        connections_8080=$(netstat -tn | grep ":8080 " | wc -l)
    fi
    
    # Database size
    local db_size=0
    if [[ -f "$APP_DIR/chat_settings.db" ]]; then
        db_size=$(stat -c%s "$APP_DIR/chat_settings.db" 2>/dev/null || echo "0")
        db_size=$((db_size / 1024))  # Convert to KB
    fi
    
    # Log files size
    local log_size=0
    if [[ -d "$LOG_DIR" ]]; then
        log_size=$(du -s "$LOG_DIR" 2>/dev/null | cut -f1 || echo "0")
    fi
    
    # Create metrics JSON
    cat > "$METRICS_FILE" <<EOF
{
    "timestamp": "$timestamp",
    "system": {
        "cpu_usage_percent": $cpu_usage,
        "memory": {
            "total_mb": $memory_total,
            "used_mb": $memory_used,
            "available_mb": $memory_available,
            "usage_percent": $(( memory_used * 100 / memory_total ))
        },
        "disk": {
            "total_kb": $disk_total,
            "used_kb": $disk_used,
            "available_kb": $disk_available,
            "usage_percent": $(( disk_used * 100 / disk_total ))
        },
        "load_average": {
            "1m": $load_1m,
            "5m": $load_5m,
            "15m": $load_15m
        }
    },
    "service": {
        "name": "$SERVICE_NAME",
        "status": "$service_status",
        "pid": $service_pid,
        "memory_mb": $service_memory,
        "connections_8080": $connections_8080
    },
    "application": {
        "database_size_kb": $db_size,
        "log_directory_size_kb": $log_size
    }
}
EOF
    
    log_info "System metrics collected"
}

# Display current system status
show_system_status() {
    log_info "Displaying current system status..."
    
    collect_system_metrics
    
    echo
    echo "=================================================================="
    echo "                 T.BUDDY SYSTEM STATUS"
    echo "=================================================================="
    echo
    
    # Service status
    echo "SERVICE STATUS:"
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo -e "  Status: ${GREEN}Active${NC}"
        echo "  Uptime: $(systemctl show -p ActiveEnterTimestamp "$SERVICE_NAME" | cut -d'=' -f2-)"
    else
        echo -e "  Status: ${RED}Inactive${NC}"
    fi
    
    # System resources
    echo
    echo "SYSTEM RESOURCES:"
    if command -v jq > /dev/null && [[ -f "$METRICS_FILE" ]]; then
        echo "  CPU Usage: $(jq -r '.system.cpu_usage_percent' "$METRICS_FILE")%"
        echo "  Memory: $(jq -r '.system.memory.used_mb' "$METRICS_FILE")MB / $(jq -r '.system.memory.total_mb' "$METRICS_FILE")MB ($(jq -r '.system.memory.usage_percent' "$METRICS_FILE")%)"
        echo "  Disk: $(jq -r '.system.disk.used_kb' "$METRICS_FILE" | awk '{print int($1/1024)}')MB / $(jq -r '.system.disk.total_kb' "$METRICS_FILE" | awk '{print int($1/1024)}')MB ($(jq -r '.system.disk.usage_percent' "$METRICS_FILE")%)"
        echo "  Load: $(jq -r '.system.load_average."1m"' "$METRICS_FILE") $(jq -r '.system.load_average."5m"' "$METRICS_FILE") $(jq -r '.system.load_average."15m"' "$METRICS_FILE")"
    else
        echo "  (Install jq for detailed metrics)"
    fi
    
    # Application metrics
    echo
    echo "APPLICATION METRICS:"
    if [[ -f "$APP_DIR/chat_settings.db" ]]; then
        local db_size
        db_size=$(stat -c%s "$APP_DIR/chat_settings.db" 2>/dev/null | awk '{print int($1/1024)}')
        echo "  Database Size: ${db_size}KB"
        
        # Count records in database if possible
        if command -v sqlite3 > /dev/null; then
            local chat_count
            chat_count=$(sqlite3 "$APP_DIR/chat_settings.db" "SELECT COUNT(*) FROM ChatSettings;" 2>/dev/null || echo "unknown")
            echo "  Chat Settings Records: $chat_count"
        fi
    else
        echo "  Database: Not found"
    fi
    
    # Recent errors
    echo
    echo "RECENT ERRORS (last hour):"
    local error_count
    error_count=$(journalctl -u "$SERVICE_NAME" --since "1 hour ago" --no-pager -q 2>/dev/null | grep -c -i "error\|exception\|failed" || echo "0")
    if [[ $error_count -gt 0 ]]; then
        echo -e "  ${RED}$error_count errors found${NC}"
        journalctl -u "$SERVICE_NAME" --since "1 hour ago" --no-pager -q | grep -i "error\|exception\|failed" | tail -3
    else
        echo -e "  ${GREEN}No errors found${NC}"
    fi
    
    echo
}

# Monitor real-time logs
monitor_logs() {
    log_info "Starting real-time log monitoring (Ctrl+C to stop)..."
    
    echo "=================================================================="
    echo "              T.BUDDY REAL-TIME LOG MONITOR"
    echo "=================================================================="
    echo
    
    # Use journalctl to follow logs
    journalctl -u "$SERVICE_NAME" -f --no-pager
}

# Analyze log patterns
analyze_logs() {
    local hours="${1:-24}"
    
    log_info "Analyzing logs for the last $hours hours..."
    
    echo
    echo "=================================================================="
    echo "                T.BUDDY LOG ANALYSIS"
    echo "=================================================================="
    echo
    
    # Get logs from specified time period
    local logs
    logs=$(journalctl -u "$SERVICE_NAME" --since "$hours hours ago" --no-pager -q 2>/dev/null)
    
    if [[ -z "$logs" ]]; then
        log_warning "No logs found for the specified time period"
        return 1
    fi
    
    # Count different log levels
    local total_lines
    total_lines=$(echo "$logs" | wc -l)
    
    local errors
    errors=$(echo "$logs" | grep -c -i "error\|exception\|traceback" || echo "0")
    
    local warnings
    warnings=$(echo "$logs" | grep -c -i "warning\|warn" || echo "0")
    
    local info
    info=$(echo "$logs" | grep -c -i "info" || echo "0")
    
    echo "LOG SUMMARY (last $hours hours):"
    echo "  Total log lines: $total_lines"
    echo "  Errors: $errors"
    echo "  Warnings: $warnings"
    echo "  Info messages: $info"
    
    # Show most common error patterns
    if [[ $errors -gt 0 ]]; then
        echo
        echo "MOST COMMON ERRORS:"
        echo "$logs" | grep -i "error\|exception" | sed 's/.*tbuddy\[.*\]: //' | sort | uniq -c | sort -nr | head -5
    fi
    
    # Show recent critical events
    echo
    echo "RECENT CRITICAL EVENTS:"
    echo "$logs" | grep -i "error\|critical\|exception\|failed" | tail -5
    
    # Check for specific patterns
    echo
    echo "SPECIFIC PATTERN ANALYSIS:"
    
    local telegram_errors
    telegram_errors=$(echo "$logs" | grep -c -i "telegram.*error" || echo "0")
    echo "  Telegram API errors: $telegram_errors"
    
    local copilot_errors
    copilot_errors=$(echo "$logs" | grep -c -i "copilot\|direct.*line.*error" || echo "0")
    echo "  Copilot Studio errors: $copilot_errors"
    
    local db_errors
    db_errors=$(echo "$logs" | grep -c -i "database.*error\|sqlite.*error" || echo "0")
    echo "  Database errors: $db_errors"
    
    echo
}

# Perform maintenance tasks
perform_maintenance() {
    log_info "Performing routine maintenance tasks..."
    
    echo
    echo "=================================================================="
    echo "              T.BUDDY MAINTENANCE TASKS"
    echo "=================================================================="
    echo
    
    # Clean old log files
    log_info "Cleaning old log files..."
    if [[ -d "$LOG_DIR" ]]; then
        find "$LOG_DIR" -name "*.log" -mtime +30 -delete 2>/dev/null || true
        find "$LOG_DIR" -name "*.log.*" -mtime +7 -delete 2>/dev/null || true
        log_success "Old log files cleaned"
    fi
    
    # Optimize database
    log_info "Optimizing database..."
    if [[ -f "$APP_DIR/chat_settings.db" ]]; then
        if command -v sqlite3 > /dev/null; then
            sqlite3 "$APP_DIR/chat_settings.db" "VACUUM;" 2>/dev/null || log_warning "Database optimization failed"
            sqlite3 "$APP_DIR/chat_settings.db" "ANALYZE;" 2>/dev/null || log_warning "Database analysis failed"
            log_success "Database optimized"
        else
            log_warning "sqlite3 not available for database optimization"
        fi
    fi
    
    # Check for updates to Python packages
    log_info "Checking for package updates..."
    if [[ -f "$APP_DIR/requirements.txt" ]] && [[ -d "$APP_DIR/venv" ]]; then
        cd "$APP_DIR"
        local outdated_packages
        outdated_packages=$(./venv/bin/pip list --outdated 2>/dev/null | wc -l)
        
        if [[ $outdated_packages -gt 0 ]]; then
            log_warning "$outdated_packages packages have updates available"
            log_info "Run 'sudo ./venv/bin/pip install -r requirements.txt --upgrade' to update"
        else
            log_success "All packages are up to date"
        fi
    fi
    
    # Check SSL certificate expiry
    log_info "Checking SSL certificate..."
    if command -v certbot > /dev/null; then
        local cert_status
        cert_status=$(certbot certificates 2>/dev/null | grep -i "tbuddy\|anna.floripa.br" || echo "No certificates found")
        echo "  Certificate status: $cert_status"
        
        # Run dry-run renewal
        if certbot renew --dry-run 2>/dev/null; then
            log_success "SSL certificate renewal test passed"
        else
            log_warning "SSL certificate renewal test failed"
        fi
    fi
    
    # Clean temporary files
    log_info "Cleaning temporary files..."
    find /tmp -name "*tbuddy*" -mtime +1 -delete 2>/dev/null || true
    log_success "Temporary files cleaned"
    
    # Check system resources
    log_info "Checking system resources..."
    collect_system_metrics
    
    if command -v jq > /dev/null && [[ -f "$METRICS_FILE" ]]; then
        local disk_usage
        disk_usage=$(jq -r '.system.disk.usage_percent' "$METRICS_FILE")
        
        if [[ $disk_usage -gt 90 ]]; then
            log_error "Critical disk usage: ${disk_usage}%"
        elif [[ $disk_usage -gt 80 ]]; then
            log_warning "High disk usage: ${disk_usage}%"
        else
            log_success "Disk usage is normal: ${disk_usage}%"
        fi
        
        local memory_usage
        memory_usage=$(jq -r '.system.memory.usage_percent' "$METRICS_FILE")
        
        if [[ $memory_usage -gt 90 ]]; then
            log_error "Critical memory usage: ${memory_usage}%"
        elif [[ $memory_usage -gt 80 ]]; then
            log_warning "High memory usage: ${memory_usage}%"
        else
            log_success "Memory usage is normal: ${memory_usage}%"
        fi
    fi
    
    echo
    log_success "Maintenance tasks completed"
    echo
}

# Generate monitoring report
generate_monitoring_report() {
    local report_file="/tmp/tbuddy_monitoring_report_$(date +%Y%m%d_%H%M%S).html"
    
    log_info "Generating monitoring report: $report_file"
    
    # Collect current metrics
    collect_system_metrics
    
    # Generate HTML report
    cat > "$report_file" <<'EOF'
<!DOCTYPE html>
<html>
<head>
    <title>T.Buddy Monitoring Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }
        .section { margin: 20px 0; }
        .metric { margin: 5px 0; }
        .status-ok { color: green; }
        .status-warning { color: orange; }
        .status-error { color: red; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        .chart { width: 100%; height: 200px; background-color: #f9f9f9; border: 1px solid #ddd; }
    </style>
</head>
<body>
    <div class="header">
        <h1>T.Buddy Translation Tool - Monitoring Report</h1>
        <p>Generated on: $(date)</p>
    </div>
EOF
    
    # Add system metrics if available
    if command -v jq > /dev/null && [[ -f "$METRICS_FILE" ]]; then
        cat >> "$report_file" <<EOF
    <div class="section">
        <h2>System Overview</h2>
        <div class="metric">Service Status: <span class="status-$(jq -r '.service.status' "$METRICS_FILE" | sed 's/active/ok/;s/failed/error/;s/inactive/warning/')">$(jq -r '.service.status' "$METRICS_FILE")</span></div>
        <div class="metric">CPU Usage: $(jq -r '.system.cpu_usage_percent' "$METRICS_FILE")%</div>
        <div class="metric">Memory Usage: $(jq -r '.system.memory.usage_percent' "$METRICS_FILE")%</div>
        <div class="metric">Disk Usage: $(jq -r '.system.disk.usage_percent' "$METRICS_FILE")%</div>
        <div class="metric">Active Connections: $(jq -r '.service.connections_8080' "$METRICS_FILE")</div>
    </div>
    
    <div class="section">
        <h2>Detailed Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th><th>Status</th></tr>
            <tr><td>Service Memory</td><td>$(jq -r '.service.memory_mb' "$METRICS_FILE") MB</td><td class="status-ok">Normal</td></tr>
            <tr><td>Database Size</td><td>$(jq -r '.application.database_size_kb' "$METRICS_FILE") KB</td><td class="status-ok">Normal</td></tr>
            <tr><td>Log Directory Size</td><td>$(jq -r '.application.log_directory_size_kb' "$METRICS_FILE") KB</td><td class="status-ok">Normal</td></tr>
            <tr><td>Load Average (1m)</td><td>$(jq -r '.system.load_average."1m"' "$METRICS_FILE")</td><td class="status-ok">Normal</td></tr>
        </table>
    </div>
EOF
    fi
    
    # Add log analysis
    cat >> "$report_file" <<EOF
    <div class="section">
        <h2>Recent Log Analysis (Last 24 Hours)</h2>
        <pre>
$(analyze_logs 24 2>/dev/null | sed 's/</\&lt;/g;s/>/\&gt;/g')
        </pre>
    </div>
    
    <div class="section">
        <h2>Service Information</h2>
        <pre>
$(systemctl status "$SERVICE_NAME" --no-pager 2>/dev/null | sed 's/</\&lt;/g;s/>/\&gt;/g')
        </pre>
    </div>
    
    <div class="section">
        <h2>Recent Logs</h2>
        <pre>
$(journalctl -u "$SERVICE_NAME" -n 50 --no-pager 2>/dev/null | sed 's/</\&lt;/g;s/>/\&gt;/g')
        </pre>
    </div>
    
</body>
</html>
EOF
    
    log_success "Monitoring report generated: $report_file"
    
    # Open report if possible
    if command -v xdg-open > /dev/null; then
        xdg-open "$report_file" 2>/dev/null &
    elif command -v firefox > /dev/null; then
        firefox "$report_file" 2>/dev/null &
    else
        log_info "Open the report in your browser: file://$report_file"
    fi
}

# Setup monitoring cron jobs
setup_monitoring_cron() {
    log_info "Setting up monitoring cron jobs..."
    
    # Create cron job for regular health checks
    local cron_file="/etc/cron.d/tbuddy-monitoring"
    
    cat > "$cron_file" <<EOF
# T.Buddy Translation Tool Monitoring Cron Jobs
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# Collect metrics every 5 minutes
*/5 * * * * root cd $(dirname "$0") && ./monitor.sh collect-metrics

# Perform maintenance daily at 2 AM
0 2 * * * root cd $(dirname "$0") && ./monitor.sh maintenance

# Generate weekly report on Sundays at 6 AM
0 6 * * 0 root cd $(dirname "$0") && ./monitor.sh report

# Clean old backups weekly
0 3 * * 0 root cd $(dirname "$0") && ./rollback.sh clean 10
EOF
    
    chmod 644 "$cron_file"
    
    log_success "Monitoring cron jobs configured"
    log_info "Check cron logs with: sudo tail -f /var/log/cron"
}

# Show usage
show_usage() {
    echo "Usage: $0 [command] [options]"
    echo
    echo "Commands:"
    echo "  status                     Show current system status"
    echo "  collect-metrics           Collect and save system metrics"
    echo "  monitor                   Monitor real-time logs"
    echo "  analyze [hours]           Analyze logs (default: 24 hours)"
    echo "  maintenance               Perform routine maintenance"
    echo "  report                    Generate HTML monitoring report"
    echo "  setup-cron               Setup monitoring cron jobs"
    echo
    echo "Examples:"
    echo "  $0 status                 # Show system status"
    echo "  $0 monitor                # Monitor real-time logs"
    echo "  $0 analyze 48             # Analyze last 48 hours of logs"
    echo "  $0 maintenance            # Perform maintenance"
    echo "  $0 report                 # Generate HTML report"
    echo
}

# Main script logic
main() {
    # Initialize logging
    init_monitoring_log
    
    case "${1:-status}" in
        "status")
            show_system_status
            ;;
        "collect-metrics")
            collect_system_metrics
            ;;
        "monitor")
            monitor_logs
            ;;
        "analyze")
            analyze_logs "${2:-24}"
            ;;
        "maintenance")
            perform_maintenance
            ;;
        "report")
            generate_monitoring_report
            ;;
        "setup-cron")
            if [[ $EUID -ne 0 ]]; then
                log_error "Root privileges required for cron setup"
                exit 1
            fi
            setup_monitoring_cron
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
    log_warning "Monitoring script interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function
main "$@"