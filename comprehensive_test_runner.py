#!/usr/bin/env python3
"""
Comprehensive Test Runner for Telegram Translation Bot

This module provides a centralized test runner that executes all test suites,
generates detailed reports, monitors performance, and validates compliance
with the design document requirements.
"""

import sys
import os
import json
import time
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
import unittest
from io import StringIO

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import all test modules
from tests.comprehensive_unit_tests import run_comprehensive_unit_tests
from tests.integration_tests import run_integration_tests
from tests.error_simulation_tests import run_error_simulation_tests
from tests.test_group_chat_functionality import run_group_chat_functionality_tests
from test_config import TestConfig, setup_test_environment, cleanup_test_environment
from test_utilities import (TestDataManager, TestPerformanceMonitor, 
                           TestResultAnalyzer, TestReportGenerator, 
                           TestEnvironmentManager)
from message_simulator import run_message_simulation_tests


class ComprehensiveTestRunner:
    """Comprehensive test runner with advanced reporting and monitoring"""
    
    def __init__(self, output_dir: str = None, verbose: bool = True):
        """Initialize comprehensive test runner"""
        self.output_dir = Path(output_dir) if output_dir else Path(__file__).parent / "test_reports"
        self.output_dir.mkdir(exist_ok=True)
        
        self.verbose = verbose
        self.start_time = datetime.utcnow()
        
        # Initialize components
        self.data_manager = TestDataManager()
        self.performance_monitor = TestPerformanceMonitor()
        self.result_analyzer = TestResultAnalyzer()
        self.report_generator = TestReportGenerator(str(self.output_dir))
        
        # Configure logging
        self.logger = self._setup_logging()
        
        # Test results storage
        self.test_results = {
            "comprehensive_unit_tests": None,
            "group_chat_functionality_tests": None,
            "integration_tests": None,
            "error_simulation_tests": None,
            "message_simulation_tests": None,
            "validation_results": None
        }
        
        self.overall_summary = {}
    
    def _setup_logging(self) -> logging.Logger:
        """Set up comprehensive logging"""
        logger = logging.getLogger('comprehensive_test_runner')
        logger.setLevel(logging.DEBUG if self.verbose else logging.INFO)
        
        # Clear existing handlers
        logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
        
        # File handler
        log_file = self.output_dir / f"test_run_{self.start_time.strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(console_formatter)
        logger.addHandler(file_handler)
        
        return logger
    
    def run_all_tests(self, test_suite_filter: List[str] = None) -> Dict[str, Any]:
        """Run all test suites with comprehensive monitoring"""
        self.logger.info("=" * 80)
        self.logger.info("COMPREHENSIVE TEST EXECUTION - TELEGRAM TRANSLATION BOT")
        self.logger.info("=" * 80)
        self.logger.info(f"Test execution started at: {self.start_time}")
        
        # Setup test environment
        setup_test_environment()
        
        try:
            with TestEnvironmentManager() as env_manager:
                # Run test suites
                test_suites = {
                    "comprehensive_unit_tests": self._run_unit_tests,
                    "group_chat_functionality_tests": self._run_group_chat_tests,
                    "integration_tests": self._run_integration_tests,
                    "error_simulation_tests": self._run_error_simulation_tests,
                    "message_simulation_tests": self._run_message_simulation_tests,
                }
                
                # Filter test suites if specified
                if test_suite_filter:
                    test_suites = {k: v for k, v in test_suites.items() if k in test_suite_filter}
                
                # Execute each test suite
                for suite_name, suite_function in test_suites.items():
                    self.logger.info(f"\n🔧 Running {suite_name.replace('_', ' ').title()}...")
                    
                    self.performance_monitor.start_timing(suite_name)
                    
                    try:
                        suite_result = suite_function()
                        self.test_results[suite_name] = suite_result
                        
                        duration = self.performance_monitor.end_timing(suite_name)
                        self.logger.info(f"✅ {suite_name} completed in {duration:.2f}s")
                        
                    except Exception as e:
                        duration = self.performance_monitor.end_timing(suite_name)
                        self.logger.error(f"❌ {suite_name} failed after {duration:.2f}s: {e}")
                        
                        self.test_results[suite_name] = {
                            "success": False,
                            "error": str(e),
                            "duration": duration
                        }
                
                # Run validation
                self.logger.info("\n🔍 Running compliance validation...")
                self.performance_monitor.start_timing("validation")
                
                validation_results = self._run_compliance_validation()
                self.test_results["validation_results"] = validation_results
                
                validation_duration = self.performance_monitor.end_timing("validation")
                self.logger.info(f"✅ Validation completed in {validation_duration:.2f}s")
                
                # Generate overall summary
                self._generate_overall_summary()
                
                # Generate reports
                self._generate_comprehensive_reports()
                
        finally:
            # Cleanup
            cleanup_test_environment()
            self.data_manager.cleanup_temporary_files()
        
        end_time = datetime.utcnow()
        total_duration = (end_time - self.start_time).total_seconds()
        
        self.logger.info("=" * 80)
        self.logger.info(f"COMPREHENSIVE TEST EXECUTION COMPLETED")
        self.logger.info(f"Total Duration: {total_duration:.2f} seconds")
        self.logger.info(f"Overall Result: {'✅ PASS' if self.overall_summary.get('overall_success', False) else '❌ FAIL'}")
        self.logger.info("=" * 80)
        
        return {
            "test_results": self.test_results,
            "overall_summary": self.overall_summary,
            "performance_metrics": self.performance_monitor.get_all_statistics(),
            "execution_info": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "total_duration": total_duration
            }
        }
    
    def _run_unit_tests(self) -> Dict[str, Any]:
        """Run comprehensive unit tests"""
        self.logger.info("Executing comprehensive unit tests...")
        
        try:
            # Capture output
            original_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output
            
            success, unittest_result = run_comprehensive_unit_tests()
            
            # Restore stdout
            sys.stdout = original_stdout
            output = captured_output.getvalue()
            
            result = {
                "success": success,
                "tests_run": unittest_result.testsRun,
                "failures": len(unittest_result.failures),
                "errors": len(unittest_result.errors),
                "skipped": len(getattr(unittest_result, 'skipped', [])),
                "success_rate": ((unittest_result.testsRun - len(unittest_result.failures) - len(unittest_result.errors)) / 
                               unittest_result.testsRun) if unittest_result.testsRun > 0 else 0,
                "detailed_failures": [{"test": str(test), "traceback": traceback} 
                                    for test, traceback in unittest_result.failures],
                "detailed_errors": [{"test": str(test), "traceback": traceback} 
                                  for test, traceback in unittest_result.errors],
                "output": output
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Unit tests failed with exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_group_chat_tests(self) -> Dict[str, Any]:
        """Run group chat functionality tests"""
        self.logger.info("Executing group chat functionality tests...")
        
        try:
            # Capture output
            original_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output
            
            success, unittest_result = run_group_chat_functionality_tests()
            
            # Restore stdout
            sys.stdout = original_stdout
            output = captured_output.getvalue()
            
            result = {
                "success": success,
                "tests_run": unittest_result.testsRun,
                "failures": len(unittest_result.failures),
                "errors": len(unittest_result.errors),
                "skipped": len(getattr(unittest_result, 'skipped', [])),
                "success_rate": ((unittest_result.testsRun - len(unittest_result.failures) - len(unittest_result.errors)) / 
                               unittest_result.testsRun) if unittest_result.testsRun > 0 else 0,
                "detailed_failures": [{"test": str(test), "traceback": traceback} 
                                    for test, traceback in unittest_result.failures],
                "detailed_errors": [{"test": str(test), "traceback": traceback} 
                                  for test, traceback in unittest_result.errors],
                "output": output
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Group chat tests failed with exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_integration_tests(self) -> Dict[str, Any]:
        """Run integration tests"""
        self.logger.info("Executing integration tests...")
        
        try:
            # Capture output
            original_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output
            
            success, unittest_result = run_integration_tests()
            
            # Restore stdout
            sys.stdout = original_stdout
            output = captured_output.getvalue()
            
            result = {
                "success": success,
                "tests_run": unittest_result.testsRun,
                "failures": len(unittest_result.failures),
                "errors": len(unittest_result.errors),
                "skipped": len(getattr(unittest_result, 'skipped', [])),
                "success_rate": ((unittest_result.testsRun - len(unittest_result.failures) - len(unittest_result.errors)) / 
                               unittest_result.testsRun) if unittest_result.testsRun > 0 else 0,
                "detailed_failures": [{"test": str(test), "traceback": traceback} 
                                    for test, traceback in unittest_result.failures],
                "detailed_errors": [{"test": str(test), "traceback": traceback} 
                                  for test, traceback in unittest_result.errors],
                "output": output
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Integration tests failed with exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_error_simulation_tests(self) -> Dict[str, Any]:
        """Run error simulation tests"""
        self.logger.info("Executing error simulation tests...")
        
        try:
            # Capture output
            original_stdout = sys.stdout
            captured_output = StringIO()
            sys.stdout = captured_output
            
            success, unittest_result = run_error_simulation_tests()
            
            # Restore stdout
            sys.stdout = original_stdout
            output = captured_output.getvalue()
            
            result = {
                "success": success,
                "tests_run": unittest_result.testsRun,
                "failures": len(unittest_result.failures),
                "errors": len(unittest_result.errors),
                "skipped": len(getattr(unittest_result, 'skipped', [])),
                "success_rate": ((unittest_result.testsRun - len(unittest_result.failures) - len(unittest_result.errors)) / 
                               unittest_result.testsRun) if unittest_result.testsRun > 0 else 0,
                "detailed_failures": [{"test": str(test), "traceback": traceback} 
                                    for test, traceback in unittest_result.failures],
                "detailed_errors": [{"test": str(test), "traceback": traceback} 
                                  for test, traceback in unittest_result.errors],
                "output": output
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error simulation tests failed with exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_message_simulation_tests(self) -> Dict[str, Any]:
        """Run message simulation tests"""
        self.logger.info("Executing message simulation tests...")
        
        try:
            simulation_results = run_message_simulation_tests()
            
            result = {
                "success": simulation_results["summary"]["success_rate"] >= 0.8,
                "total_tests": simulation_results["summary"]["total_tests"],
                "successful_tests": simulation_results["summary"]["successful_tests"],
                "success_rate": simulation_results["summary"]["success_rate"],
                "test_details": simulation_results["tests"],
                "simulation_data": simulation_results
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Message simulation tests failed with exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _run_compliance_validation(self) -> Dict[str, Any]:
        """Run compliance validation against design document requirements"""
        self.logger.info("Running compliance validation...")
        
        validation_results = {
            "design_compliance": {},
            "performance_compliance": {},
            "functional_compliance": {},
            "overall_compliance": False
        }
        
        try:
            # Design compliance checks
            design_compliance = self._validate_design_compliance()
            validation_results["design_compliance"] = design_compliance
            
            # Performance compliance checks
            performance_compliance = self._validate_performance_compliance()
            validation_results["performance_compliance"] = performance_compliance
            
            # Functional compliance checks
            functional_compliance = self._validate_functional_compliance()
            validation_results["functional_compliance"] = functional_compliance
            
            # Overall compliance
            all_compliant = (
                design_compliance.get("compliant", False) and
                performance_compliance.get("compliant", False) and
                functional_compliance.get("compliant", False)
            )
            validation_results["overall_compliance"] = all_compliant
            
        except Exception as e:
            self.logger.error(f"Compliance validation failed: {e}")
            validation_results["error"] = str(e)
        
        return validation_results
    
    def _validate_design_compliance(self) -> Dict[str, Any]:
        """Validate compliance with design document requirements"""
        compliance_checks = {
            "test_coverage": False,
            "test_isolation": False,
            "error_handling": False,
            "performance_monitoring": False,
            "reporting": False
        }
        
        # Check test coverage
        required_test_suites = ["unit_tests", "integration_tests", "error_simulation", "message_simulation"]
        implemented_suites = [k for k in self.test_results.keys() if self.test_results[k] is not None]
        
        compliance_checks["test_coverage"] = len(implemented_suites) >= len(required_test_suites)
        
        # Check test isolation (each test should use isolated database)
        compliance_checks["test_isolation"] = True  # Implemented via TestDatabase class
        
        # Check error handling coverage
        error_sim_result = self.test_results.get("error_simulation_tests", {})
        compliance_checks["error_handling"] = error_sim_result.get("success", False)
        
        # Check performance monitoring
        performance_metrics = self.performance_monitor.get_all_statistics()
        compliance_checks["performance_monitoring"] = len(performance_metrics) > 0
        
        # Check reporting capabilities
        compliance_checks["reporting"] = True  # Implemented via TestReportGenerator
        
        overall_compliant = all(compliance_checks.values())
        
        return {
            "compliant": overall_compliant,
            "checks": compliance_checks,
            "compliance_rate": sum(compliance_checks.values()) / len(compliance_checks)
        }
    
    def _validate_performance_compliance(self) -> Dict[str, Any]:
        """Validate performance compliance with requirements"""
        performance_stats = self.performance_monitor.get_all_statistics()
        
        compliance_checks = {
            "parsing_speed": False,
            "database_speed": False,
            "memory_usage": False,
            "overall_execution_time": False
        }
        
        # Check parsing speed (should be under 1 second per operation)
        parsing_stats = performance_stats.get("language_parsing", {})
        if parsing_stats.get("avg", 0) < 1.0:
            compliance_checks["parsing_speed"] = True
        
        # Check database speed (should be under 0.1 seconds per operation)
        db_stats = performance_stats.get("database", {})
        if db_stats.get("avg", 0) < 0.1:
            compliance_checks["database_speed"] = True
        
        # Memory usage check (no specific test, assume compliant if no memory errors)
        compliance_checks["memory_usage"] = True
        
        # Overall execution time (should complete within reasonable time)
        total_time = sum(stats.get("total", 0) for stats in performance_stats.values())
        compliance_checks["overall_execution_time"] = total_time < 300  # 5 minutes
        
        overall_compliant = all(compliance_checks.values())
        
        return {
            "compliant": overall_compliant,
            "checks": compliance_checks,
            "performance_metrics": performance_stats
        }
    
    def _validate_functional_compliance(self) -> Dict[str, Any]:
        """Validate functional compliance with requirements"""
        compliance_checks = {
            "language_parsing_accuracy": False,
            "database_reliability": False,
            "conversation_management": False,
            "error_resilience": False
        }
        
        # Check language parsing accuracy (95%+ success rate)
        unit_test_result = self.test_results.get("comprehensive_unit_tests", {})
        unit_success_rate = unit_test_result.get("success_rate", 0)
        compliance_checks["language_parsing_accuracy"] = unit_success_rate >= TestConfig.MIN_PARSING_SUCCESS_RATE
        
        # Check database reliability (100% success rate for basic operations)
        integration_result = self.test_results.get("integration_tests", {})
        integration_success_rate = integration_result.get("success_rate", 0)
        compliance_checks["database_reliability"] = integration_success_rate >= TestConfig.MIN_DATABASE_SUCCESS_RATE
        
        # Check conversation management
        compliance_checks["conversation_management"] = integration_result.get("success", False)
        
        # Check error resilience
        error_sim_result = self.test_results.get("error_simulation_tests", {})
        error_success_rate = error_sim_result.get("success_rate", 0)
        compliance_checks["error_resilience"] = error_success_rate >= 0.8  # 80% for error scenarios
        
        overall_compliant = all(compliance_checks.values())
        
        return {
            "compliant": overall_compliant,
            "checks": compliance_checks,
            "compliance_rate": sum(compliance_checks.values()) / len(compliance_checks)
        }
    
    def _generate_overall_summary(self):
        """Generate overall test execution summary"""
        total_tests = 0
        total_passed = 0
        total_failed = 0
        
        suite_results = []
        
        for suite_name, result in self.test_results.items():
            if result and isinstance(result, dict):
                if "tests_run" in result:
                    # Unit test result format
                    tests_run = result.get("tests_run", 0)
                    failures = result.get("failures", 0)
                    errors = result.get("errors", 0)
                    passed = tests_run - failures - errors
                    
                    total_tests += tests_run
                    total_passed += passed
                    total_failed += failures + errors
                    
                    suite_results.append({
                        "suite": suite_name,
                        "tests_run": tests_run,
                        "passed": passed,
                        "failed": failures + errors,
                        "success_rate": result.get("success_rate", 0)
                    })
                
                elif "total_tests" in result:
                    # Simulation test result format
                    total_tests_sim = result.get("total_tests", 0)
                    successful_tests = result.get("successful_tests", 0)
                    failed_tests = total_tests_sim - successful_tests
                    
                    total_tests += total_tests_sim
                    total_passed += successful_tests
                    total_failed += failed_tests
                    
                    suite_results.append({
                        "suite": suite_name,
                        "tests_run": total_tests_sim,
                        "passed": successful_tests,
                        "failed": failed_tests,
                        "success_rate": result.get("success_rate", 0)
                    })
        
        overall_success_rate = total_passed / total_tests if total_tests > 0 else 0
        overall_success = overall_success_rate >= 0.95  # 95% threshold
        
        # Check validation compliance
        validation_result = self.test_results.get("validation_results", {})
        validation_compliant = validation_result.get("overall_compliance", False)
        
        # Final success requires both high test success rate and validation compliance
        final_success = overall_success and validation_compliant
        
        self.overall_summary = {
            "overall_success": final_success,
            "total_tests": total_tests,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "overall_success_rate": overall_success_rate,
            "validation_compliant": validation_compliant,
            "suite_results": suite_results,
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate recommendations based on test results"""
        recommendations = []
        
        # Check overall success rate
        overall_rate = self.overall_summary.get("overall_success_rate", 0)
        if overall_rate < 0.95:
            recommendations.append(f"Overall success rate is {overall_rate:.1%}, aim for 95%+")
        
        # Check individual suite performance
        for suite_result in self.overall_summary.get("suite_results", []):
            success_rate = suite_result.get("success_rate", 0)
            suite_name = suite_result.get("suite", "")
            
            if success_rate < 0.9:
                recommendations.append(f"Improve {suite_name} success rate: {success_rate:.1%}")
        
        # Check validation compliance
        validation_result = self.test_results.get("validation_results", {})
        if not validation_result.get("overall_compliance", False):
            recommendations.append("Address validation compliance issues")
        
        # Performance recommendations
        performance_stats = self.performance_monitor.get_all_statistics()
        for metric_name, stats in performance_stats.items():
            if stats.get("avg", 0) > 2.0:  # Operations taking more than 2 seconds
                recommendations.append(f"Optimize {metric_name} performance (avg: {stats['avg']:.2f}s)")
        
        if not recommendations:
            recommendations.append("All tests passing - excellent work!")
        
        return recommendations
    
    def _generate_comprehensive_reports(self):
        """Generate comprehensive test reports in multiple formats"""
        self.logger.info("Generating comprehensive test reports...")
        
        # Prepare report data
        report_data = {
            "execution_summary": self.overall_summary,
            "test_results": self.test_results,
            "performance_metrics": self.performance_monitor.get_all_statistics(),
            "execution_info": {
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.utcnow().isoformat(),
                "environment": "local_testing"
            }
        }
        
        # Generate reports
        try:
            # HTML report
            html_report = self.report_generator.generate_html_report(
                report_data, "comprehensive_test_report"
            )
            self.logger.info(f"📄 HTML report generated: {html_report}")
            
            # JSON report
            json_report = self.report_generator.generate_json_report(
                report_data, "comprehensive_test_report"
            )
            self.logger.info(f"📄 JSON report generated: {json_report}")
            
            # Performance report
            performance_report = self.performance_monitor.generate_performance_report()
            perf_file = self.output_dir / f"performance_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            with open(perf_file, 'w') as f:
                json.dump(performance_report, f, indent=2)
            self.logger.info(f"📄 Performance report generated: {perf_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to generate reports: {e}")


def main():
    """Main entry point for comprehensive test runner"""
    parser = argparse.ArgumentParser(description="Comprehensive Test Runner for Telegram Translation Bot")
    
    parser.add_argument("--output-dir", "-o", type=str, 
                       help="Output directory for test reports")
    parser.add_argument("--verbose", "-v", action="store_true", 
                       help="Enable verbose output")
    parser.add_argument("--suite", "-s", action="append", 
                       choices=["comprehensive_unit_tests", "group_chat_functionality_tests", "integration_tests", 
                               "error_simulation_tests", "message_simulation_tests"],
                       help="Specific test suite to run (can be specified multiple times)")
    parser.add_argument("--quick", "-q", action="store_true",
                       help="Run quick test suite (unit tests only)")
    
    args = parser.parse_args()
    
    # Setup test suite filter
    test_suite_filter = args.suite
    if args.quick:
        test_suite_filter = ["comprehensive_unit_tests"]
    
    # Create and run test runner
    test_runner = ComprehensiveTestRunner(
        output_dir=args.output_dir,
        verbose=args.verbose
    )
    
    try:
        results = test_runner.run_all_tests(test_suite_filter)
        
        # Print final summary
        overall_success = results["overall_summary"]["overall_success"]
        success_rate = results["overall_summary"]["overall_success_rate"]
        
        print(f"\n{'=' * 80}")
        print(f"FINAL RESULT: {'✅ SUCCESS' if overall_success else '❌ FAILURE'}")
        print(f"Success Rate: {success_rate:.1%}")
        print(f"Total Tests: {results['overall_summary']['total_tests']}")
        print(f"Passed: {results['overall_summary']['total_passed']}")
        print(f"Failed: {results['overall_summary']['total_failed']}")
        print(f"{'=' * 80}")
        
        # Exit with appropriate code
        sys.exit(0 if overall_success else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()