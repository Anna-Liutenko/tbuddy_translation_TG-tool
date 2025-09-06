#!/usr/bin/env python3
"""
Comprehensive Deployment Testing Framework for T.Buddy Translation Tool
Validates deployment integrity, security, and functionality
"""

import os
import sys
import json
import time
import subprocess
import requests
import sqlite3
import socket
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeploymentTester:
    """Comprehensive deployment testing and validation"""
    
    def __init__(self, config_path: str = "/etc/tbuddy/env"):
        self.config_path = config_path
        self.app_dir = "/opt/tbuddy"
        self.service_name = "tbuddy"
        self.test_results = []
        self.config = {}
        
        # Load configuration if available
        self.load_configuration()
        
    def load_configuration(self):
        """Load configuration from environment file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            self.config[key.strip()] = value.strip()
                logger.info(f"Loaded configuration from {self.config_path}")
            else:
                logger.warning(f"Configuration file not found: {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")

    def add_test_result(self, test_name: str, passed: bool, message: str, details: Dict = None):
        """Add a test result"""
        result = {
            'test_name': test_name,
            'passed': passed,
            'message': message,
            'timestamp': datetime.now().isoformat(),
            'details': details or {}
        }
        self.test_results.append(result)
        
        status = "PASS" if passed else "FAIL"
        logger.info(f"[{status}] {test_name}: {message}")

    def run_command(self, command: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
        """Run a shell command and return success, stdout, stderr"""
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def test_system_requirements(self) -> bool:
        """Test system requirements and dependencies"""
        logger.info("Testing system requirements...")
        
        all_passed = True
        
        # Test Python availability
        success, stdout, stderr = self.run_command(['python3', '--version'])
        if success:
            version = stdout.strip()
            self.add_test_result(
                "python_version",
                True,
                f"Python available: {version}",
                {"version": version}
            )
        else:
            self.add_test_result("python_version", False, "Python 3 not available")
            all_passed = False
        
        # Test required system packages
        required_packages = ['nginx', 'systemctl', 'curl']
        for package in required_packages:
            success, _, _ = self.run_command(['which', package])
            self.add_test_result(
                f"package_{package}",
                success,
                f"Package {package} {'available' if success else 'not found'}"
            )
            if not success:
                all_passed = False
        
        # Test disk space
        try:
            import shutil
            total, used, free = shutil.disk_usage('/')
            free_gb = free // (1024**3)
            
            disk_ok = free_gb >= 1  # At least 1GB free
            self.add_test_result(
                "disk_space",
                disk_ok,
                f"Disk space: {free_gb}GB free",
                {"free_gb": free_gb, "total_gb": total // (1024**3)}
            )
            if not disk_ok:
                all_passed = False
        except Exception as e:
            self.add_test_result("disk_space", False, f"Failed to check disk space: {e}")
            all_passed = False
        
        return all_passed

    def test_service_deployment(self) -> bool:
        """Test service deployment and configuration"""
        logger.info("Testing service deployment...")
        
        all_passed = True
        
        # Test application directory
        app_exists = os.path.exists(self.app_dir)
        self.add_test_result(
            "app_directory",
            app_exists,
            f"Application directory {'exists' if app_exists else 'not found'}: {self.app_dir}"
        )
        if not app_exists:
            all_passed = False
        
        # Test essential files
        essential_files = [
            f"{self.app_dir}/app.py",
            f"{self.app_dir}/requirements.txt",
            f"{self.app_dir}/venv/bin/python"
        ]
        
        for file_path in essential_files:
            file_exists = os.path.exists(file_path)
            self.add_test_result(
                f"essential_file_{os.path.basename(file_path)}",
                file_exists,
                f"Essential file {'exists' if file_exists else 'not found'}: {file_path}"
            )
            if not file_exists:
                all_passed = False
        
        # Test systemd service file
        service_file = f"/etc/systemd/system/{self.service_name}.service"
        service_exists = os.path.exists(service_file)
        self.add_test_result(
            "systemd_service",
            service_exists,
            f"Systemd service {'exists' if service_exists else 'not found'}: {service_file}"
        )
        if not service_exists:
            all_passed = False
        
        # Test nginx configuration
        nginx_config = f"/etc/nginx/sites-available/{self.service_name}"
        nginx_exists = os.path.exists(nginx_config)
        self.add_test_result(
            "nginx_config",
            nginx_exists,
            f"Nginx configuration {'exists' if nginx_exists else 'not found'}: {nginx_config}"
        )
        
        return all_passed

    def test_service_status(self) -> bool:
        """Test service status and health"""
        logger.info("Testing service status...")
        
        all_passed = True
        
        # Test systemd service status
        success, stdout, stderr = self.run_command(['systemctl', 'is-active', self.service_name])
        service_active = success and 'active' in stdout
        self.add_test_result(
            "service_active",
            service_active,
            f"Service {'is active' if service_active else 'is not active'}: {stdout.strip() if stdout else stderr.strip()}"
        )
        if not service_active:
            all_passed = False
            
            # Get detailed service status
            success, stdout, stderr = self.run_command(['systemctl', 'status', self.service_name, '--no-pager'])
            self.add_test_result(
                "service_status_details",
                False,
                "Service status details",
                {"status_output": stdout, "error_output": stderr}
            )
        
        # Test port listening
        port_listening = self.is_port_listening(8080)
        self.add_test_result(
            "port_8080_listening",
            port_listening,
            f"Port 8080 {'is listening' if port_listening else 'is not listening'}"
        )
        if not port_listening:
            all_passed = False
        
        return all_passed

    def is_port_listening(self, port: int, host: str = 'localhost') -> bool:
        """Check if a port is listening"""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception:
            return False

    def test_http_endpoints(self) -> bool:
        """Test HTTP endpoints"""
        logger.info("Testing HTTP endpoints...")
        
        all_passed = True
        base_url = "http://localhost:8080"
        
        # Test basic connectivity
        try:
            response = requests.get(f"{base_url}/", timeout=10)
            endpoint_reachable = True
            status_code = response.status_code
        except requests.exceptions.RequestException as e:
            endpoint_reachable = False
            status_code = None
        
        self.add_test_result(
            "http_basic_connectivity",
            endpoint_reachable,
            f"HTTP endpoint {'reachable' if endpoint_reachable else 'not reachable'}" + 
            (f" (status: {status_code})" if status_code else "")
        )
        
        if not endpoint_reachable:
            all_passed = False
            return all_passed
        
        # Test health endpoint
        try:
            response = requests.get(f"{base_url}/health", timeout=10)
            health_ok = response.status_code == 200
            self.add_test_result(
                "health_endpoint",
                health_ok,
                f"Health endpoint returned status {response.status_code}",
                {"response_body": response.text[:500] if hasattr(response, 'text') else ""}
            )
            if not health_ok:
                all_passed = False
        except requests.exceptions.RequestException as e:
            self.add_test_result("health_endpoint", False, f"Health endpoint error: {e}")
            all_passed = False
        
        # Test webhook endpoint
        try:
            # POST to webhook endpoint (should handle gracefully even with invalid data)
            response = requests.post(
                f"{base_url}/webhook",
                json={"test": "deployment_validation"},
                timeout=10
            )
            webhook_responsive = response.status_code in [200, 400, 405]  # Any reasonable response
            self.add_test_result(
                "webhook_endpoint",
                webhook_responsive,
                f"Webhook endpoint returned status {response.status_code}",
                {"response_body": response.text[:200] if hasattr(response, 'text') else ""}
            )
        except requests.exceptions.RequestException as e:
            self.add_test_result("webhook_endpoint", False, f"Webhook endpoint error: {e}")
            all_passed = False
        
        return all_passed

    def test_database_connectivity(self) -> bool:
        """Test database connectivity and integrity"""
        logger.info("Testing database connectivity...")
        
        all_passed = True
        db_path = f"{self.app_dir}/chat_settings.db"
        
        # Test database file existence
        db_exists = os.path.exists(db_path)
        self.add_test_result(
            "database_file_exists",
            db_exists,
            f"Database file {'exists' if db_exists else 'not found'}: {db_path}"
        )
        
        if not db_exists:
            # This might be normal for new deployments
            self.add_test_result(
                "database_file_note",
                True,
                "Database file will be created on first use"
            )
            return True
        
        # Test database connectivity
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            cursor = conn.cursor()
            
            # Test basic query
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            self.add_test_result(
                "database_connectivity",
                True,
                f"Database connectivity successful, {len(tables)} tables found",
                {"tables": [table[0] for table in tables]}
            )
            
            # Test integrity check
            cursor.execute("PRAGMA integrity_check;")
            integrity_result = cursor.fetchone()[0]
            integrity_ok = integrity_result == "ok"
            
            self.add_test_result(
                "database_integrity",
                integrity_ok,
                f"Database integrity check: {integrity_result}"
            )
            
            if not integrity_ok:
                all_passed = False
            
            conn.close()
            
        except sqlite3.Error as e:
            self.add_test_result("database_connectivity", False, f"Database error: {e}")
            all_passed = False
        except Exception as e:
            self.add_test_result("database_connectivity", False, f"Unexpected database error: {e}")
            all_passed = False
        
        return all_passed

    def test_external_dependencies(self) -> bool:
        """Test external dependencies and APIs"""
        logger.info("Testing external dependencies...")
        
        all_passed = True
        
        # Test DNS resolution
        try:
            import socket
            socket.gethostbyname('api.telegram.org')
            self.add_test_result("dns_resolution", True, "DNS resolution working")
        except socket.gaierror as e:
            self.add_test_result("dns_resolution", False, f"DNS resolution failed: {e}")
            all_passed = False
        
        # Test Telegram API reachability
        try:
            response = requests.get("https://api.telegram.org/bot", timeout=10)
            telegram_reachable = response.status_code in [200, 401, 404]  # Any response means reachable
            self.add_test_result(
                "telegram_api_reachable",
                telegram_reachable,
                f"Telegram API {'reachable' if telegram_reachable else 'not reachable'} (status: {response.status_code})"
            )
            if not telegram_reachable:
                all_passed = False
        except requests.exceptions.RequestException as e:
            self.add_test_result("telegram_api_reachable", False, f"Telegram API unreachable: {e}")
            all_passed = False
        
        # Test Direct Line API if configured
        if 'DIRECT_LINE_SECRET' in self.config and self.config['DIRECT_LINE_SECRET']:
            try:
                headers = {
                    'Authorization': f"Bearer {self.config['DIRECT_LINE_SECRET']}",
                    'Content-Type': 'application/json'
                }
                response = requests.post(
                    "https://directline.botframework.com/v3/directline/conversations",
                    headers=headers,
                    timeout=10
                )
                directline_ok = response.status_code in [200, 201]
                self.add_test_result(
                    "directline_api_test",
                    directline_ok,
                    f"Direct Line API test {'passed' if directline_ok else 'failed'} (status: {response.status_code})"
                )
                if not directline_ok:
                    all_passed = False
            except requests.exceptions.RequestException as e:
                self.add_test_result("directline_api_test", False, f"Direct Line API test failed: {e}")
                all_passed = False
        else:
            self.add_test_result("directline_api_test", True, "Direct Line secret not configured - skipping test")
        
        return all_passed

    def test_security_configuration(self) -> bool:
        """Test security configuration"""
        logger.info("Testing security configuration...")
        
        all_passed = True
        
        # Test environment file permissions
        if os.path.exists(self.config_path):
            try:
                stat_info = os.stat(self.config_path)
                permissions = oct(stat_info.st_mode)[-3:]
                secure_permissions = permissions in ['600', '640', '644']
                
                self.add_test_result(
                    "env_file_permissions",
                    secure_permissions,
                    f"Environment file permissions: {permissions} ({'secure' if secure_permissions else 'insecure'})"
                )
                if not secure_permissions:
                    all_passed = False
            except Exception as e:
                self.add_test_result("env_file_permissions", False, f"Failed to check permissions: {e}")
                all_passed = False
        
        # Test that no sensitive files are world-readable
        sensitive_patterns = ['.env', 'secret', 'key', 'password']
        world_readable_files = []
        
        try:
            for root, dirs, files in os.walk(self.app_dir):
                for file in files:
                    if any(pattern in file.lower() for pattern in sensitive_patterns):
                        file_path = os.path.join(root, file)
                        if os.path.exists(file_path):
                            stat_info = os.stat(file_path)
                            if stat_info.st_mode & 0o004:  # World readable
                                world_readable_files.append(file_path)
            
            no_world_readable = len(world_readable_files) == 0
            self.add_test_result(
                "no_world_readable_secrets",
                no_world_readable,
                f"{'No' if no_world_readable else len(world_readable_files)} sensitive files are world-readable",
                {"world_readable_files": world_readable_files}
            )
            if not no_world_readable:
                all_passed = False
        except Exception as e:
            self.add_test_result("no_world_readable_secrets", False, f"Failed to check file permissions: {e}")
            all_passed = False
        
        # Test firewall status (if ufw is available)
        success, stdout, stderr = self.run_command(['ufw', 'status'])
        if success:
            firewall_active = 'Status: active' in stdout
            self.add_test_result(
                "firewall_status",
                firewall_active,
                f"Firewall {'is active' if firewall_active else 'is not active'}"
            )
        else:
            self.add_test_result("firewall_status", True, "UFW not available - skipping firewall test")
        
        return all_passed

    def test_nginx_configuration(self) -> bool:
        """Test nginx configuration"""
        logger.info("Testing nginx configuration...")
        
        all_passed = True
        
        # Test nginx configuration syntax
        success, stdout, stderr = self.run_command(['nginx', '-t'])
        config_valid = success and 'syntax is ok' in stderr and 'test is successful' in stderr
        
        self.add_test_result(
            "nginx_config_syntax",
            config_valid,
            f"Nginx configuration {'is valid' if config_valid else 'has errors'}",
            {"nginx_output": stderr}
        )
        if not config_valid:
            all_passed = False
        
        # Test nginx service status
        success, stdout, stderr = self.run_command(['systemctl', 'is-active', 'nginx'])
        nginx_active = success and 'active' in stdout
        
        self.add_test_result(
            "nginx_service_active",
            nginx_active,
            f"Nginx service {'is active' if nginx_active else 'is not active'}"
        )
        if not nginx_active:
            all_passed = False
        
        # Test if nginx is proxying to our service
        if nginx_active and self.is_port_listening(80):
            try:
                response = requests.get("http://localhost/health", timeout=10)
                proxy_working = response.status_code == 200
                self.add_test_result(
                    "nginx_proxy_test",
                    proxy_working,
                    f"Nginx proxy {'is working' if proxy_working else 'is not working'} (status: {response.status_code})"
                )
            except requests.exceptions.RequestException as e:
                self.add_test_result("nginx_proxy_test", False, f"Nginx proxy test failed: {e}")
                all_passed = False
        else:
            self.add_test_result("nginx_proxy_test", True, "Nginx not listening on port 80 - skipping proxy test")
        
        return all_passed

    def test_ssl_configuration(self) -> bool:
        """Test SSL configuration"""
        logger.info("Testing SSL configuration...")
        
        all_passed = True
        
        # Check if HTTPS port is listening
        https_listening = self.is_port_listening(443)
        self.add_test_result(
            "https_port_listening",
            https_listening,
            f"HTTPS port {'is listening' if https_listening else 'is not listening'}"
        )
        
        if not https_listening:
            self.add_test_result("ssl_configuration", True, "HTTPS not configured - this is optional")
            return True
        
        # Test SSL certificate if HTTPS is configured
        try:
            import ssl
            import socket
            
            context = ssl.create_default_context()
            with socket.create_connection(('localhost', 443), timeout=10) as sock:
                with context.wrap_socket(sock, server_hostname='localhost') as ssock:
                    cert = ssock.getpeercert()
                    
            self.add_test_result(
                "ssl_certificate_valid",
                True,
                "SSL certificate is valid",
                {"cert_subject": dict(x[0] for x in cert.get('subject', []))}
            )
        except Exception as e:
            self.add_test_result("ssl_certificate_valid", False, f"SSL certificate validation failed: {e}")
            all_passed = False
        
        return all_passed

    def run_performance_tests(self) -> bool:
        """Run basic performance tests"""
        logger.info("Running performance tests...")
        
        all_passed = True
        
        if not self.is_port_listening(8080):
            self.add_test_result("performance_tests", False, "Service not running - skipping performance tests")
            return False
        
        # Test response time
        try:
            start_time = time.time()
            response = requests.get("http://localhost:8080/health", timeout=30)
            response_time = time.time() - start_time
            
            response_time_ok = response_time < 5.0  # Less than 5 seconds
            self.add_test_result(
                "response_time_test",
                response_time_ok,
                f"Response time: {response_time:.2f}s ({'good' if response_time_ok else 'slow'})",
                {"response_time_seconds": response_time}
            )
            if not response_time_ok:
                all_passed = False
        except Exception as e:
            self.add_test_result("response_time_test", False, f"Response time test failed: {e}")
            all_passed = False
        
        # Test concurrent requests (light load test)
        try:
            import threading
            import queue
            
            def make_request(results_queue):
                try:
                    start = time.time()
                    response = requests.get("http://localhost:8080/health", timeout=10)
                    end = time.time()
                    results_queue.put(('success', end - start, response.status_code))
                except Exception as e:
                    results_queue.put(('error', 0, str(e)))
            
            results_queue = queue.Queue()
            threads = []
            num_threads = 5
            
            # Start threads
            for _ in range(num_threads):
                thread = threading.Thread(target=make_request, args=(results_queue,))
                thread.start()
                threads.append(thread)
            
            # Wait for completion
            for thread in threads:
                thread.join(timeout=30)
            
            # Collect results
            successful_requests = 0
            total_time = 0
            
            while not results_queue.empty():
                status, response_time, _ = results_queue.get()
                if status == 'success':
                    successful_requests += 1
                    total_time += response_time
            
            concurrent_test_ok = successful_requests >= num_threads * 0.8  # 80% success rate
            avg_response_time = total_time / successful_requests if successful_requests > 0 else 0
            
            self.add_test_result(
                "concurrent_requests_test",
                concurrent_test_ok,
                f"Concurrent requests: {successful_requests}/{num_threads} successful, avg {avg_response_time:.2f}s",
                {
                    "successful_requests": successful_requests,
                    "total_requests": num_threads,
                    "average_response_time": avg_response_time
                }
            )
            if not concurrent_test_ok:
                all_passed = False
                
        except Exception as e:
            self.add_test_result("concurrent_requests_test", False, f"Concurrent requests test failed: {e}")
            all_passed = False
        
        return all_passed

    def generate_test_report(self) -> Dict:
        """Generate comprehensive test report"""
        passed_tests = len([r for r in self.test_results if r['passed']])
        total_tests = len(self.test_results)
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_tests': total_tests,
                'passed_tests': passed_tests,
                'failed_tests': total_tests - passed_tests,
                'success_rate': (passed_tests / total_tests * 100) if total_tests > 0 else 0
            },
            'overall_status': 'PASS' if passed_tests == total_tests else 'FAIL',
            'test_results': self.test_results,
            'configuration': {
                'app_dir': self.app_dir,
                'service_name': self.service_name,
                'config_path': self.config_path
            }
        }
        
        return report

    def run_all_tests(self) -> bool:
        """Run all deployment tests"""
        logger.info("Starting comprehensive deployment tests...")
        
        test_categories = [
            ("System Requirements", self.test_system_requirements),
            ("Service Deployment", self.test_service_deployment),
            ("Service Status", self.test_service_status),
            ("HTTP Endpoints", self.test_http_endpoints),
            ("Database Connectivity", self.test_database_connectivity),
            ("External Dependencies", self.test_external_dependencies),
            ("Security Configuration", self.test_security_configuration),
            ("Nginx Configuration", self.test_nginx_configuration),
            ("SSL Configuration", self.test_ssl_configuration),
            ("Performance Tests", self.run_performance_tests)
        ]
        
        all_passed = True
        
        for category_name, test_function in test_categories:
            logger.info(f"Running {category_name} tests...")
            try:
                category_passed = test_function()
                if not category_passed:
                    all_passed = False
                    logger.warning(f"{category_name} tests failed")
                else:
                    logger.info(f"{category_name} tests passed")
            except Exception as e:
                logger.error(f"Error running {category_name} tests: {e}")
                self.add_test_result(f"{category_name.lower()}_error", False, f"Test category error: {e}")
                all_passed = False
        
        return all_passed

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Deployment testing for T.Buddy Translation Tool')
    parser.add_argument('--config', default='/etc/tbuddy/env', help='Path to environment configuration')
    parser.add_argument('--output', help='Output file for test report (JSON)')
    parser.add_argument('--quick', action='store_true', help='Run quick tests only')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Create tester
    tester = DeploymentTester(args.config)
    
    # Run tests
    if args.quick:
        logger.info("Running quick deployment tests...")
        all_passed = (
            tester.test_service_status() and
            tester.test_http_endpoints() and
            tester.test_database_connectivity()
        )
    else:
        all_passed = tester.run_all_tests()
    
    # Generate report
    report = tester.generate_test_report()
    
    # Save report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2)
        logger.info(f"Test report saved to {args.output}")
    
    # Print summary
    print("\n" + "="*70)
    print("DEPLOYMENT TEST SUMMARY")
    print("="*70)
    print(f"Total tests: {report['summary']['total_tests']}")
    print(f"Passed: {report['summary']['passed_tests']}")
    print(f"Failed: {report['summary']['failed_tests']}")
    print(f"Success rate: {report['summary']['success_rate']:.1f}%")
    print(f"Overall status: {report['overall_status']}")
    
    if report['summary']['failed_tests'] > 0:
        print("\nFAILED TESTS:")
        for result in tester.test_results:
            if not result['passed']:
                print(f"  - {result['test_name']}: {result['message']}")
    
    print("="*70)
    
    sys.exit(0 if all_passed else 1)

if __name__ == '__main__':
    main()