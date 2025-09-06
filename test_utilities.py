"""
Test Utilities for Telegram Translation Bot Testing Framework

This module provides comprehensive utilities for test data management,
result reporting, performance monitoring, and test environment management.
"""

import os
import json
import time
import sqlite3
import tempfile
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from collections import defaultdict
import csv

from test_config import TestConfig, TestDatabase, TestReporter


class TestDataManager:
    """Manages test data generation, storage, and cleanup"""
    
    def __init__(self, base_dir: str = None):
        """Initialize test data manager"""
        self.base_dir = Path(base_dir) if base_dir else Path(__file__).parent / "test_data"
        self.base_dir.mkdir(exist_ok=True)
        
        self.fixtures_dir = self.base_dir / "fixtures"
        self.results_dir = self.base_dir / "results"
        self.temp_dir = self.base_dir / "temp"
        
        # Create directories
        for directory in [self.fixtures_dir, self.results_dir, self.temp_dir]:
            directory.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('test_data_manager')
    
    def create_test_fixture(self, fixture_name: str, fixture_data: Dict[str, Any]) -> str:
        """Create a test fixture file"""
        fixture_path = self.fixtures_dir / f"{fixture_name}.json"
        
        with open(fixture_path, 'w', encoding='utf-8') as f:
            json.dump(fixture_data, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Created test fixture: {fixture_path}")
        return str(fixture_path)
    
    def load_test_fixture(self, fixture_name: str) -> Dict[str, Any]:
        """Load a test fixture"""
        fixture_path = self.fixtures_dir / f"{fixture_name}.json"
        
        if not fixture_path.exists():
            raise FileNotFoundError(f"Test fixture not found: {fixture_path}")
        
        with open(fixture_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def save_test_results(self, test_name: str, results: Dict[str, Any]) -> str:
        """Save test results to file"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = self.results_dir / f"{test_name}_{timestamp}.json"
        
        # Add metadata
        results_with_metadata = {
            "test_name": test_name,
            "timestamp": datetime.utcnow().isoformat(),
            "test_environment": "local",
            "results": results
        }
        
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results_with_metadata, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Saved test results: {results_file}")
        return str(results_file)
    
    def create_temporary_database(self, test_name: str) -> str:
        """Create a temporary database for testing"""
        db_file = self.temp_dir / f"temp_db_{test_name}_{int(time.time())}.db"
        
        # Initialize database
        import db
        db.init_db(str(db_file))
        
        self.logger.info(f"Created temporary database: {db_file}")
        return str(db_file)
    
    def cleanup_temporary_files(self, max_age_hours: int = 24):
        """Clean up temporary files older than max_age_hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
        cleaned_count = 0
        
        for file_path in self.temp_dir.iterdir():
            if file_path.is_file():
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                    except Exception as e:
                        self.logger.warning(f"Failed to clean up {file_path}: {e}")
        
        self.logger.info(f"Cleaned up {cleaned_count} temporary files")
        return cleaned_count
    
    def generate_test_data_set(self, count: int = 100) -> Dict[str, Any]:
        """Generate a comprehensive test data set"""
        from test_config import TestDataFactory
        from message_simulator import MessageTemplateLibrary
        
        test_data = {
            "fresh_user_scenarios": [],
            "returning_user_scenarios": [],
            "reset_scenarios": [],
            "language_parsing_cases": [],
            "failure_cases": [],
            "edge_cases": []
        }
        
        # Generate fresh user scenarios
        for i in range(count // 4):
            scenario = TestDataFactory.fresh_user_scenario()
            test_data["fresh_user_scenarios"].append(scenario)
        
        # Generate returning user scenarios
        for i in range(count // 4):
            scenario = TestDataFactory.returning_user_scenario()
            test_data["returning_user_scenarios"].append(scenario)
        
        # Generate reset scenarios
        for i in range(count // 4):
            scenario = TestDataFactory.reset_user_scenario()
            test_data["reset_scenarios"].append(scenario)
        
        # Generate language parsing test cases
        languages_list = [
            ["English", "Spanish"],
            ["French", "German", "Italian"],
            ["Russian", "Japanese", "Korean"],
            ["Portuguese", "Dutch", "Swedish"],
            ["Arabic", "Chinese", "Hindi"],
        ]
        
        for languages in languages_list:
            confirmations = MessageTemplateLibrary.get_confirmation_variations(languages)
            for confirmation in confirmations:
                test_data["language_parsing_cases"].append({
                    "languages": languages,
                    "confirmation_text": confirmation,
                    "expected_result": True
                })
        
        # Generate failure cases
        failure_messages = MessageTemplateLibrary.get_failure_messages()
        for message in failure_messages:
            test_data["failure_cases"].append({
                "message": message,
                "expected_result": False
            })
        
        # Generate edge cases
        edge_cases = [
            {"type": "empty_input", "input": "", "expected": False},
            {"type": "very_long_input", "input": "A" * 1000, "expected": False},
            {"type": "special_characters", "input": "Special: !@#$%^&*()", "expected": False},
            {"type": "unicode_languages", "input": "Setup complete! Languages: 中文, العربية, 日本語.", "expected": True},
        ]
        
        test_data["edge_cases"] = edge_cases
        
        return test_data


class TestPerformanceMonitor:
    """Monitors test performance and execution metrics"""
    
    def __init__(self):
        """Initialize performance monitor"""
        self.metrics = defaultdict(list)
        self.start_times = {}
        self.logger = logging.getLogger('performance_monitor')
    
    def start_timing(self, operation_name: str):
        """Start timing an operation"""
        self.start_times[operation_name] = time.time()
    
    def end_timing(self, operation_name: str) -> float:
        """End timing an operation and record duration"""
        if operation_name not in self.start_times:
            self.logger.warning(f"No start time recorded for operation: {operation_name}")
            return 0.0
        
        duration = time.time() - self.start_times[operation_name]
        self.metrics[operation_name].append(duration)
        del self.start_times[operation_name]
        
        return duration
    
    def record_metric(self, metric_name: str, value: float):
        """Record a custom metric"""
        self.metrics[metric_name].append(value)
    
    def get_statistics(self, metric_name: str) -> Dict[str, float]:
        """Get statistics for a metric"""
        if metric_name not in self.metrics or not self.metrics[metric_name]:
            return {"count": 0}
        
        values = self.metrics[metric_name]
        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "total": sum(values)
        }
    
    def get_all_statistics(self) -> Dict[str, Dict[str, float]]:
        """Get statistics for all metrics"""
        return {name: self.get_statistics(name) for name in self.metrics.keys()}
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": self.get_all_statistics(),
            "summary": {},
            "recommendations": []
        }
        
        # Calculate summary statistics
        all_durations = []
        for metric_name, values in self.metrics.items():
            if "time" in metric_name.lower() or "duration" in metric_name.lower():
                all_durations.extend(values)
        
        if all_durations:
            report["summary"] = {
                "total_operations": len(all_durations),
                "total_time": sum(all_durations),
                "average_operation_time": sum(all_durations) / len(all_durations),
                "slowest_operation": max(all_durations),
                "fastest_operation": min(all_durations)
            }
        
        # Generate recommendations
        recommendations = []
        
        # Check for slow operations
        for metric_name, stats in report["metrics"].items():
            if "time" in metric_name.lower() and stats.get("avg", 0) > 1.0:
                recommendations.append(f"Operation '{metric_name}' is slow (avg: {stats['avg']:.2f}s)")
        
        # Check for high variance
        for metric_name, values in self.metrics.items():
            if len(values) > 1:
                avg = sum(values) / len(values)
                variance = sum((x - avg) ** 2 for x in values) / len(values)
                if variance > avg * 0.5:  # High variance threshold
                    recommendations.append(f"Operation '{metric_name}' has high variance")
        
        report["recommendations"] = recommendations
        
        return report


class TestResultAnalyzer:
    """Analyzes test results and generates insights"""
    
    def __init__(self):
        """Initialize result analyzer"""
        self.logger = logging.getLogger('result_analyzer')
    
    def analyze_test_suite_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze results from a test suite"""
        analysis = {
            "summary": {},
            "success_patterns": [],
            "failure_patterns": [],
            "performance_insights": [],
            "recommendations": []
        }
        
        # Calculate summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.get("success", False))
        failed_tests = total_tests - passed_tests
        
        analysis["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": failed_tests,
            "success_rate": passed_tests / total_tests if total_tests > 0 else 0
        }
        
        # Analyze failure patterns
        failure_reasons = defaultdict(int)
        for result in results:
            if not result.get("success", False) and "error" in result:
                error_type = self._categorize_error(result["error"])
                failure_reasons[error_type] += 1
        
        analysis["failure_patterns"] = [
            {"error_type": error_type, "count": count, "percentage": count / failed_tests}
            for error_type, count in failure_reasons.items()
        ]
        
        # Analyze success patterns
        success_categories = defaultdict(int)
        for result in results:
            if result.get("success", False):
                test_category = self._categorize_test(result)
                success_categories[test_category] += 1
        
        analysis["success_patterns"] = [
            {"category": category, "count": count}
            for category, count in success_categories.items()
        ]
        
        # Generate recommendations
        recommendations = []
        
        if analysis["summary"]["success_rate"] < 0.95:
            recommendations.append("Success rate below 95% - investigate failing tests")
        
        if failure_reasons:
            most_common_failure = max(failure_reasons.items(), key=lambda x: x[1])
            recommendations.append(f"Address most common failure: {most_common_failure[0]}")
        
        analysis["recommendations"] = recommendations
        
        return analysis
    
    def _categorize_error(self, error_message: str) -> str:
        """Categorize an error message"""
        error_lower = error_message.lower()
        
        if "database" in error_lower or "sqlite" in error_lower:
            return "database_error"
        elif "parsing" in error_lower or "regex" in error_lower:
            return "parsing_error"
        elif "network" in error_lower or "connection" in error_lower:
            return "network_error"
        elif "timeout" in error_lower:
            return "timeout_error"
        elif "assertion" in error_lower:
            return "assertion_error"
        else:
            return "unknown_error"
    
    def _categorize_test(self, result: Dict[str, Any]) -> str:
        """Categorize a test result"""
        test_name = result.get("test_name", "").lower()
        
        if "parsing" in test_name or "language" in test_name:
            return "language_parsing"
        elif "database" in test_name:
            return "database_operations"
        elif "conversation" in test_name:
            return "conversation_management"
        elif "integration" in test_name:
            return "integration"
        else:
            return "other"
    
    def generate_trend_analysis(self, historical_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate trend analysis from historical test results"""
        if not historical_results:
            return {"error": "No historical data available"}
        
        # Sort by timestamp
        sorted_results = sorted(historical_results, key=lambda x: x.get("timestamp", ""))
        
        trends = {
            "timestamp_range": {
                "start": sorted_results[0].get("timestamp"),
                "end": sorted_results[-1].get("timestamp")
            },
            "success_rate_trend": [],
            "performance_trend": [],
            "stability_metrics": {}
        }
        
        # Calculate success rate trend
        for result in sorted_results:
            summary = result.get("summary", {})
            success_rate = summary.get("success_rate", 0)
            trends["success_rate_trend"].append({
                "timestamp": result.get("timestamp"),
                "success_rate": success_rate
            })
        
        # Calculate stability metrics
        success_rates = [item["success_rate"] for item in trends["success_rate_trend"]]
        if success_rates:
            avg_success_rate = sum(success_rates) / len(success_rates)
            variance = sum((x - avg_success_rate) ** 2 for x in success_rates) / len(success_rates)
            
            trends["stability_metrics"] = {
                "average_success_rate": avg_success_rate,
                "variance": variance,
                "stability_score": max(0, 1 - variance)  # Higher is more stable
            }
        
        return trends


class TestReportGenerator:
    """Generates comprehensive test reports in various formats"""
    
    def __init__(self, output_dir: str = None):
        """Initialize report generator"""
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "reports"
        self.output_dir.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('report_generator')
    
    def generate_html_report(self, test_results: Dict[str, Any], report_name: str = "test_report") -> str:
        """Generate HTML test report"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"{report_name}_{timestamp}.html"
        
        html_content = self._create_html_template(test_results)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.logger.info(f"Generated HTML report: {report_file}")
        return str(report_file)
    
    def generate_json_report(self, test_results: Dict[str, Any], report_name: str = "test_report") -> str:
        """Generate JSON test report"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"{report_name}_{timestamp}.json"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(test_results, f, indent=2, ensure_ascii=False)
        
        self.logger.info(f"Generated JSON report: {report_file}")
        return str(report_file)
    
    def generate_csv_summary(self, test_results: List[Dict[str, Any]], report_name: str = "test_summary") -> str:
        """Generate CSV summary of test results"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        report_file = self.output_dir / f"{report_name}_{timestamp}.csv"
        
        if not test_results:
            return ""
        
        # Extract CSV headers from first result
        headers = ["test_name", "success", "timestamp", "duration", "error"]
        
        with open(report_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            
            for result in test_results:
                row = {
                    "test_name": result.get("test_name", ""),
                    "success": result.get("success", False),
                    "timestamp": result.get("timestamp", ""),
                    "duration": result.get("duration", 0),
                    "error": result.get("error", "")
                }
                writer.writerow(row)
        
        self.logger.info(f"Generated CSV summary: {report_file}")
        return str(report_file)
    
    def _create_html_template(self, test_results: Dict[str, Any]) -> str:
        """Create HTML template for test report"""
        summary = test_results.get("summary", {})
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Translation Bot - Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
        .summary {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .metric {{ background: #e9ecef; padding: 15px; border-radius: 5px; text-align: center; flex: 1; }}
        .metric h3 {{ margin: 0; color: #495057; }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #007cba; }}
        .success {{ color: #28a745; }}
        .failure {{ color: #dc3545; }}
        .section {{ margin-bottom: 30px; }}
        .test-result {{ margin: 10px 0; padding: 10px; border-left: 4px solid #ccc; }}
        .test-success {{ border-left-color: #28a745; background: #f8fff9; }}
        .test-failure {{ border-left-color: #dc3545; background: #fff8f8; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f8f9fa; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Telegram Translation Bot - Test Report</h1>
        <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
    </div>
    
    <div class="summary">
        <div class="metric">
            <h3>Total Tests</h3>
            <div class="value">{summary.get('total_tests', 0)}</div>
        </div>
        <div class="metric">
            <h3>Passed</h3>
            <div class="value success">{summary.get('passed_tests', 0)}</div>
        </div>
        <div class="metric">
            <h3>Failed</h3>
            <div class="value failure">{summary.get('failed_tests', 0)}</div>
        </div>
        <div class="metric">
            <h3>Success Rate</h3>
            <div class="value">{summary.get('success_rate', 0):.1%}</div>
        </div>
    </div>
    
    <div class="section">
        <h2>Test Results Details</h2>
        <div id="test-details">
            {self._generate_test_details_html(test_results)}
        </div>
    </div>
    
    <div class="section">
        <h2>Performance Metrics</h2>
        <div id="performance-metrics">
            {self._generate_performance_html(test_results)}
        </div>
    </div>
</body>
</html>"""
        return html
    
    def _generate_test_details_html(self, test_results: Dict[str, Any]) -> str:
        """Generate HTML for test details"""
        details = test_results.get("detailed_results", {})
        html_parts = []
        
        for category, results in details.items():
            if isinstance(results, list):
                html_parts.append(f"<h3>{category.replace('_', ' ').title()}</h3>")
                
                for result in results:
                    success = result.get("success", False)
                    css_class = "test-success" if success else "test-failure"
                    status = "✅ PASS" if success else "❌ FAIL"
                    
                    html_parts.append(f"""
                    <div class="test-result {css_class}">
                        <strong>{status}</strong> - {result.get('test_name', 'Unknown Test')}
                        {f"<br>Error: {result.get('error', '')}" if not success else ""}
                    </div>
                    """)
        
        return "".join(html_parts)
    
    def _generate_performance_html(self, test_results: Dict[str, Any]) -> str:
        """Generate HTML for performance metrics"""
        performance = test_results.get("performance", {})
        
        if not performance:
            return "<p>No performance data available</p>"
        
        html = "<table><tr><th>Metric</th><th>Value</th></tr>"
        
        for metric, value in performance.items():
            if isinstance(value, (int, float)):
                formatted_value = f"{value:.3f}" if isinstance(value, float) else str(value)
                html += f"<tr><td>{metric.replace('_', ' ').title()}</td><td>{formatted_value}</td></tr>"
        
        html += "</table>"
        return html


class TestEnvironmentManager:
    """Manages test environment setup and cleanup"""
    
    def __init__(self):
        """Initialize environment manager"""
        self.temp_databases = []
        self.temp_files = []
        self.logger = logging.getLogger('env_manager')
    
    def setup_isolated_environment(self, test_name: str) -> Dict[str, str]:
        """Set up isolated test environment"""
        # Create temporary database
        test_db = TestDatabase(test_name)
        self.temp_databases.append(test_db)
        
        # Set environment variables for testing
        os.environ['TESTING'] = '1'
        os.environ['TEST_DATABASE_PATH'] = test_db.get_path()
        
        environment_info = {
            "test_name": test_name,
            "database_path": test_db.get_path(),
            "temp_dir": str(Path(test_db.get_path()).parent),
            "isolation_level": "high"
        }
        
        self.logger.info(f"Set up isolated environment for test: {test_name}")
        return environment_info
    
    def cleanup_environment(self):
        """Clean up test environment"""
        # Clean up temporary databases
        for test_db in self.temp_databases:
            test_db.cleanup()
        
        # Clean up temporary files
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                self.logger.warning(f"Failed to clean up {temp_file}: {e}")
        
        # Reset environment variables
        os.environ.pop('TESTING', None)
        os.environ.pop('TEST_DATABASE_PATH', None)
        
        # Clear lists
        self.temp_databases.clear()
        self.temp_files.clear()
        
        self.logger.info("Cleaned up test environment")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup_environment()


# Utility functions for common test operations
def run_with_timeout(func, timeout_seconds: int = 30, *args, **kwargs):
    """Run a function with timeout"""
    import signal
    
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Function timed out after {timeout_seconds} seconds")
    
    # Set up timeout
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)
    
    try:
        result = func(*args, **kwargs)
        return result
    finally:
        # Clean up
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def compare_test_results(result1: Dict[str, Any], result2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two test results and identify differences"""
    comparison = {
        "identical": result1 == result2,
        "differences": [],
        "summary": {}
    }
    
    # Compare success rates
    sr1 = result1.get("summary", {}).get("success_rate", 0)
    sr2 = result2.get("summary", {}).get("success_rate", 0)
    
    if sr1 != sr2:
        comparison["differences"].append({
            "field": "success_rate",
            "result1": sr1,
            "result2": sr2,
            "difference": sr2 - sr1
        })
    
    # Compare test counts
    tc1 = result1.get("summary", {}).get("total_tests", 0)
    tc2 = result2.get("summary", {}).get("total_tests", 0)
    
    if tc1 != tc2:
        comparison["differences"].append({
            "field": "total_tests",
            "result1": tc1,
            "result2": tc2,
            "difference": tc2 - tc1
        })
    
    comparison["summary"] = {
        "has_differences": len(comparison["differences"]) > 0,
        "difference_count": len(comparison["differences"])
    }
    
    return comparison


if __name__ == '__main__':
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    # Create test data manager
    data_manager = TestDataManager()
    
    # Generate test data set
    test_data = data_manager.generate_test_data_set(50)
    fixture_path = data_manager.create_test_fixture("comprehensive_test_set", test_data)
    print(f"Created test fixture: {fixture_path}")
    
    # Create performance monitor
    monitor = TestPerformanceMonitor()
    
    # Simulate some operations
    monitor.start_timing("test_operation")
    time.sleep(0.1)  # Simulate work
    duration = monitor.end_timing("test_operation")
    
    # Generate performance report
    perf_report = monitor.generate_performance_report()
    print(f"Performance report: {json.dumps(perf_report, indent=2)}")
    
    # Create report generator
    report_gen = TestReportGenerator()
    
    # Example test results
    example_results = {
        "summary": {
            "total_tests": 50,
            "passed_tests": 47,
            "failed_tests": 3,
            "success_rate": 0.94
        },
        "detailed_results": {
            "language_parsing": [
                {"test_name": "test_parsing_1", "success": True},
                {"test_name": "test_parsing_2", "success": False, "error": "Parsing failed"}
            ]
        },
        "performance": perf_report["metrics"]
    }
    
    # Generate reports
    html_report = report_gen.generate_html_report(example_results)
    json_report = report_gen.generate_json_report(example_results)
    
    print(f"Generated HTML report: {html_report}")
    print(f"Generated JSON report: {json_report}")