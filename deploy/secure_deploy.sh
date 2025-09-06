#!/usr/bin/env bash
# Secure Deployment Script for T.Buddy Translation Tool
# This script provides comprehensive deployment procedures with security best practices

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SERVICE_NAME="tbuddy"
SERVICE_USER="tbuddy"
SERVICE_GROUP="www-data"
APP_DIR="/opt/tbuddy"
CONFIG_DIR="/etc/tbuddy"
LOG_DIR="/var/log/tbuddy"
RUN_DIR="/var/run/tbuddy"
DATA_DIR="/var/lib/tbuddy"

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
    echo "          T.BUDDY SECURE DEPLOYMENT SCRIPT"
    echo "=================================================================="
    echo
}

print_separator() {
    echo
    echo "------------------------------------------------------------------"
    echo
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_info "Running as root - proceeding with system-level deployment"
        return 0
    else
        log_error "This script must be run as root for system deployment"
        log_info "Usage: sudo $0 [command]"
        exit 1
    fi
}

# Check if running on supported OS
check_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        case $ID in
            ubuntu|debian)
                log_info "Detected supported OS: $PRETTY_NAME"
                ;;
            *)
                log_warning "Untested OS: $PRETTY_NAME - proceeding with caution"
                ;;
        esac
    else
        log_warning "Could not detect OS - assuming compatible system"
    fi
}

# Install system dependencies
install_dependencies() {
    log_info "Installing system dependencies..."
    
    apt-get update
    apt-get install -y \
        python3 \
        python3-venv \
        python3-pip \
        python3-dev \
        build-essential \
        nginx \
        certbot \
        python3-certbot-nginx \
        git \
        curl \
        jq \
        htop \
        logrotate \
        fail2ban \
        ufw
    
    log_success "System dependencies installed"
}

# Create system user and directories
setup_user_and_directories() {
    log_info "Setting up service user and directories..."
    
    # Create service user
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$APP_DIR" "$SERVICE_USER"
        log_success "Created service user: $SERVICE_USER"
    else
        log_info "Service user already exists: $SERVICE_USER"
    fi
    
    # Create directories with proper permissions
    mkdir -p "$APP_DIR" "$CONFIG_DIR" "$LOG_DIR" "$RUN_DIR" "$DATA_DIR"
    
    # Set ownership and permissions
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$LOG_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$RUN_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$DATA_DIR"
    chown -R root:root "$CONFIG_DIR"
    
    # Set secure permissions
    chmod 755 "$APP_DIR"
    chmod 755 "$LOG_DIR"
    chmod 755 "$RUN_DIR"
    chmod 755 "$DATA_DIR"
    chmod 700 "$CONFIG_DIR"
    
    log_success "Directory structure created with secure permissions"
}

# Deploy application code
deploy_application() {
    log_info "Deploying application code..."
    
    # Stop service if running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_info "Stopping existing service..."
        systemctl stop "$SERVICE_NAME"
    fi
    
    # Backup existing installation if it exists
    if [[ -d "$APP_DIR/app.py" ]]; then
        BACKUP_DIR="/opt/backups/tbuddy-$(date +%Y%m%d-%H%M%S)"
        mkdir -p "/opt/backups"
        cp -r "$APP_DIR" "$BACKUP_DIR"
        log_info "Backed up existing installation to $BACKUP_DIR"
    fi
    
    # Deploy code (assuming we're in the repo directory)
    if [[ -f "$REPO_ROOT/app.py" ]]; then
        cp -r "$REPO_ROOT"/* "$APP_DIR/"
        
        # Remove sensitive files that shouldn't be in production
        rm -f "$APP_DIR"/.env*
        rm -rf "$APP_DIR"/.git*
        rm -rf "$APP_DIR"/__pycache__
        rm -f "$APP_DIR"/*.db
        rm -f "$APP_DIR"/*.log
        
        chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR"
        log_success "Application code deployed"
    else
        log_error "Could not find application code in $REPO_ROOT"
        exit 1
    fi
}

# Setup Python virtual environment
setup_python_environment() {
    log_info "Setting up Python virtual environment..."
    
    cd "$APP_DIR"
    
    # Create virtual environment as service user
    sudo -u "$SERVICE_USER" python3 -m venv venv
    
    # Install dependencies
    sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
    sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install -r requirements.txt
    
    # Install production WSGI server
    sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install gunicorn
    
    log_success "Python environment configured"
}

# Configure environment variables
configure_environment() {
    log_info "Configuring environment variables..."
    
    ENV_FILE="$CONFIG_DIR/env"
    
    if [[ ! -f "$ENV_FILE" ]]; then
        # Create environment file from production template
        if [[ -f "$REPO_ROOT/.env.production.example" ]]; then
            cp "$REPO_ROOT/.env.production.example" "$ENV_FILE"
        else
            log_error "Production environment template not found"
            exit 1
        fi
        
        # Set secure permissions
        chmod 640 "$ENV_FILE"
        chown root:root "$ENV_FILE"
        
        log_warning "Environment file created: $ENV_FILE"
        log_warning "Please edit this file and add your actual secrets:"
        log_warning "  - TELEGRAM_API_TOKEN"
        log_warning "  - DIRECT_LINE_SECRET"
        log_warning "  - GITHUB_TOKEN (optional)"
        
        echo
        log_warning "Example configuration:"
        echo "TELEGRAM_API_TOKEN=YOUR_BOT_TOKEN_FROM_BOTFATHER"
        echo "DIRECT_LINE_SECRET=YOUR_DIRECT_LINE_SECRET_FROM_COPILOT_STUDIO"
        echo "GITHUB_TOKEN=YOUR_GITHUB_TOKEN_HERE"
        echo
    else
        log_info "Environment file already exists: $ENV_FILE"
    fi
}

# Install systemd service
install_systemd_service() {
    log_info "Installing systemd service..."
    
    if [[ -f "$REPO_ROOT/deploy/tbuddy.service" ]]; then
        cp "$REPO_ROOT/deploy/tbuddy.service" "/etc/systemd/system/$SERVICE_NAME.service"
        
        # Reload systemd and enable service
        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"
        
        log_success "Systemd service installed and enabled"
    else
        log_error "Systemd service file not found: $REPO_ROOT/deploy/tbuddy.service"
        exit 1
    fi
}

# Configure nginx
configure_nginx() {
    log_info "Configuring nginx reverse proxy..."
    
    if [[ -f "$REPO_ROOT/deploy/tbuddy.nginx.conf" ]]; then
        cp "$REPO_ROOT/deploy/tbuddy.nginx.conf" "/etc/nginx/sites-available/$SERVICE_NAME"
        
        # Enable site
        ln -sf "/etc/nginx/sites-available/$SERVICE_NAME" "/etc/nginx/sites-enabled/$SERVICE_NAME"
        
        # Test nginx configuration
        if nginx -t; then
            log_success "Nginx configuration is valid"
        else
            log_error "Nginx configuration test failed"
            exit 1
        fi
    else
        log_error "Nginx configuration file not found: $REPO_ROOT/deploy/tbuddy.nginx.conf"
        exit 1
    fi
}

# Configure firewall
configure_firewall() {
    log_info "Configuring firewall..."
    
    # Enable UFW if not already enabled
    if ! ufw status | grep -q "Status: active"; then
        ufw --force enable
    fi
    
    # Allow SSH, HTTP, and HTTPS
    ufw allow ssh
    ufw allow 'Nginx Full'
    
    log_success "Firewall configured"
}

# Setup SSL certificate
setup_ssl() {
    log_info "Setting up SSL certificate..."
    
    read -p "Enter your domain name (e.g., anna.floripa.br): " DOMAIN_NAME
    
    if [[ -n "$DOMAIN_NAME" ]]; then
        # Restart nginx to load new configuration
        systemctl reload nginx
        
        # Obtain SSL certificate
        certbot --nginx -d "$DOMAIN_NAME" --non-interactive --agree-tos --email admin@"$DOMAIN_NAME"
        
        # Setup automatic renewal
        systemctl enable certbot.timer
        
        log_success "SSL certificate configured for $DOMAIN_NAME"
    else
        log_warning "No domain provided - skipping SSL setup"
    fi
}

# Start services
start_services() {
    log_info "Starting services..."
    
    # Start and check tbuddy service
    systemctl start "$SERVICE_NAME"
    
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "T.Buddy service started successfully"
    else
        log_error "Failed to start T.Buddy service"
        systemctl status "$SERVICE_NAME"
        exit 1
    fi
    
    # Reload nginx
    systemctl reload nginx
    
    if systemctl is-active --quiet nginx; then
        log_success "Nginx reloaded successfully"
    else
        log_error "Failed to reload nginx"
        systemctl status nginx
        exit 1
    fi
}

# Health check
perform_health_check() {
    log_info "Performing health check..."
    
    # Wait a moment for service to fully start
    sleep 5
    
    # Check if service is running
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Service is active"
    else
        log_error "Service is not active"
        return 1
    fi
    
    # Check if port is listening
    if netstat -tuln | grep -q ":8080"; then
        log_success "Application is listening on port 8080"
    else
        log_error "Application is not listening on port 8080"
        return 1
    fi
    
    # Test HTTP endpoint
    if curl -s http://localhost:8080/health > /dev/null; then
        log_success "Health endpoint is responding"
    else
        log_warning "Health endpoint test failed - this may be normal if not implemented"
    fi
    
    return 0
}

# Security hardening
apply_security_hardening() {
    log_info "Applying security hardening..."
    
    # Configure fail2ban
    cat > /etc/fail2ban/jail.local <<EOF
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[nginx-http-auth]
enabled = true

[nginx-limit-req]
enabled = true
filter = nginx-limit-req
action = iptables-multiport[name=ReqLimit, port="http,https", protocol=tcp]
logpath = /var/log/nginx/error.log
findtime = 600
bantime = 7200
maxretry = 10
EOF
    
    systemctl enable fail2ban
    systemctl restart fail2ban
    
    # Set up log rotation
    cat > /etc/logrotate.d/tbuddy <<EOF
$LOG_DIR/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $SERVICE_USER $SERVICE_GROUP
    postrotate
        systemctl reload $SERVICE_NAME
    endscript
}
EOF
    
    log_success "Security hardening applied"
}

# Full deployment
full_deployment() {
    print_header
    log_info "Starting full secure deployment..."
    
    check_root
    check_os
    
    install_dependencies
    print_separator
    
    setup_user_and_directories
    print_separator
    
    deploy_application
    print_separator
    
    setup_python_environment
    print_separator
    
    configure_environment
    print_separator
    
    install_systemd_service
    print_separator
    
    configure_nginx
    print_separator
    
    configure_firewall
    print_separator
    
    setup_ssl
    print_separator
    
    apply_security_hardening
    print_separator
    
    start_services
    print_separator
    
    if perform_health_check; then
        print_separator
        log_success "Deployment completed successfully!"
        echo
        log_info "Next steps:"
        echo "  1. Edit $CONFIG_DIR/env with your actual secrets"
        echo "  2. Restart the service: sudo systemctl restart $SERVICE_NAME"
        echo "  3. Check service status: sudo systemctl status $SERVICE_NAME"
        echo "  4. View logs: sudo journalctl -u $SERVICE_NAME -f"
        echo
        log_info "Service URLs:"
        echo "  Local: http://localhost:8080/"
        echo "  Public: https://your-domain.com/"
        echo
    else
        log_error "Deployment completed with issues - please check the logs"
        exit 1
    fi
}

# Update deployment
update_deployment() {
    log_info "Updating existing deployment..."
    
    check_root
    
    # Stop service
    systemctl stop "$SERVICE_NAME"
    
    # Deploy new code
    deploy_application
    
    # Update Python dependencies
    cd "$APP_DIR"
    sudo -u "$SERVICE_USER" "$APP_DIR/venv/bin/pip" install -r requirements.txt
    
    # Restart service
    systemctl start "$SERVICE_NAME"
    
    if perform_health_check; then
        log_success "Update completed successfully!"
    else
        log_error "Update completed with issues"
        exit 1
    fi
}

# Rollback deployment
rollback_deployment() {
    log_info "Rolling back deployment..."
    
    check_root
    
    BACKUP_DIR=$(ls -1 /opt/backups/tbuddy-* | tail -1)
    
    if [[ -d "$BACKUP_DIR" ]]; then
        log_info "Rolling back to: $BACKUP_DIR"
        
        systemctl stop "$SERVICE_NAME"
        
        # Remove current installation
        rm -rf "$APP_DIR"/*
        
        # Restore backup
        cp -r "$BACKUP_DIR"/* "$APP_DIR/"
        chown -R "$SERVICE_USER:$SERVICE_GROUP" "$APP_DIR"
        
        systemctl start "$SERVICE_NAME"
        
        if perform_health_check; then
            log_success "Rollback completed successfully!"
        else
            log_error "Rollback completed with issues"
            exit 1
        fi
    else
        log_error "No backup found for rollback"
        exit 1
    fi
}

# Show usage
show_usage() {
    echo "Usage: $0 [command]"
    echo
    echo "Commands:"
    echo "  full       Full deployment (default)"
    echo "  update     Update existing deployment"
    echo "  rollback   Rollback to previous version"
    echo "  health     Perform health check"
    echo "  logs       Show service logs"
    echo "  status     Show service status"
    echo
    echo "Examples:"
    echo "  $0 full       # Full deployment"
    echo "  $0 update     # Update deployment"
    echo "  $0 rollback   # Rollback deployment"
    echo
}

# Main script logic
main() {
    case "${1:-full}" in
        "full")
            full_deployment
            ;;
        "update")
            update_deployment
            ;;
        "rollback")
            rollback_deployment
            ;;
        "health")
            check_root
            perform_health_check
            ;;
        "logs")
            journalctl -u "$SERVICE_NAME" -f
            ;;
        "status")
            systemctl status "$SERVICE_NAME"
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
    log_warning "Deployment script interrupted"
    exit 130
}

trap cleanup INT TERM

# Execute main function
main "$@"