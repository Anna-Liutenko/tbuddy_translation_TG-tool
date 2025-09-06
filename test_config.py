"""
Test configuration and utilities for the Telegram Translation Bot testing framework.

This module provides configuration management, test database creation, and common
utilities for the comprehensive testing suite.
"""

import os
import tempfile
import time
import random
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

# Test configuration
class TestConfig:
    """Configuration for test environment"""
    
    # Database settings
    TEST_DB_PREFIX = "test_chat_settings_"
    ISOLATION_MODE = True  # Each test gets its own database
    
    # Test server settings
    TEST_SERVER_HOST = "127.0.0.1"
    TEST_SERVER_PORT = 5000
    
    # Test data settings
    MAX_TEST_CHATS = 1000
    TEST_TIMEOUT = 30  # seconds
    
    # Validation thresholds
    MIN_PARSING_SUCCESS_RATE = 0.95  # 95%
    MIN_DATABASE_SUCCESS_RATE = 1.0   # 100%
    MIN_CONVERSATION_SUCCESS_RATE = 1.0  # 100%

class TestDatabase:
    """Manages isolated test databases"""
    
    def __init__(self, test_name: str = None):
        """Create isolated test database"""
        self.test_name = test_name or f"test_{int(time.time())}"
        self.db_file = None
        self._create_temp_db()
    
    def _create_temp_db(self):
        """Create temporary database file"""
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, 
            suffix='.db',
            prefix=f"{TestConfig.TEST_DB_PREFIX}{self.test_name}_"
        )
        temp_file.close()
        self.db_file = temp_file.name
        
        # Initialize database
        import db
        db.init_db(self.db_file)
    
    def get_path(self) -> str:
        """Get database file path"""
        return self.db_file
    
    def cleanup(self):
        """Remove test database"""
        if self.db_file and os.path.exists(self.db_file):
            try:
                os.unlink(self.db_file)
            except:
                pass
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

class TestDataFactory:
    """Factory for generating test data"""
    
    SAMPLE_LANGUAGES = [
        "English", "Spanish", "French", "German", "Italian", "Portuguese",
        "Russian", "Japanese", "Korean", "Chinese", "Arabic", "Hindi",
        "Polish", "Dutch", "Swedish", "Norwegian", "Finnish"
    ]
    
    CONFIRMATION_TEMPLATES = [
        "Thanks! Setup is complete. Now we speak {languages}.",
        "Great! I can now translate between {languages}.",
        "Perfect! Now I can help you with {languages}.",
        "Setup is complete. Now we speak {languages}.",
        "Excellent! I'm ready to translate {languages}!",
        "Setup complete! Ready for {languages} translation.",
    ]
    
    FAILURE_MESSAGES = [
        "Hello, how are you?",
        "Please provide language preferences",
        "What languages do you prefer?",
        "Send your message and I'll translate it.",
        "I don't understand your request.",
        "No languages are mentioned in your request.",
        "Setup is incomplete. Please try again.",
        "",  # Empty message
        "Random text without language confirmation"
    ]
    
    @classmethod
    def generate_chat_id(cls, prefix: str = "test_chat") -> str:
        """Generate unique test chat ID"""
        timestamp = int(time.time() * 1000)  # milliseconds
        random_suffix = random.randint(1000, 9999)
        return f"{prefix}_{timestamp}_{random_suffix}"
    
    @classmethod
    def generate_language_set(cls, count: int = 3) -> List[str]:
        """Generate random set of languages"""
        return random.sample(cls.SAMPLE_LANGUAGES, min(count, len(cls.SAMPLE_LANGUAGES)))
    
    @classmethod
    def generate_confirmation_message(cls, languages: List[str]) -> str:
        """Generate confirmation message with languages"""
        template = random.choice(cls.CONFIRMATION_TEMPLATES)
        lang_string = ", ".join(languages)
        return template.format(languages=lang_string)
    
    @classmethod
    def generate_failure_message(cls) -> str:
        """Generate message that should not be parsed as confirmation"""
        return random.choice(cls.FAILURE_MESSAGES)
    
    @classmethod
    def generate_telegram_message(cls, chat_id: str, text: str, message_type: str = "private") -> Dict[str, Any]:
        """Generate Telegram webhook message payload"""
        return {
            "message": {
                "message_id": random.randint(1000, 99999),
                "from": {
                    "id": int(chat_id.split('_')[-1]) if chat_id.split('_')[-1].isdigit() else random.randint(100000, 999999),
                    "is_bot": False,
                    "first_name": "TestUser",
                    "username": f"testuser_{chat_id.split('_')[-1]}"
                },
                "chat": {
                    "id": int(chat_id.split('_')[-1]) if chat_id.split('_')[-1].isdigit() else random.randint(100000, 999999),
                    "type": message_type,
                    "first_name": "TestUser" if message_type == "private" else None,
                    "title": "Test Group" if message_type == "group" else None
                },
                "date": int(time.time()),
                "text": text
            }
        }
    
    @classmethod
    def generate_conversation_state(cls, chat_id: str, setup_complete: bool = False) -> Dict[str, Any]:
        """Generate conversation state dictionary"""
        return {
            'id': f'conv_{chat_id}_{int(time.time())}',
            'token': f'token_{chat_id}_{random.randint(1000, 9999)}',
            'watermark': f'wm_{random.randint(100, 999)}' if random.choice([True, False]) else None,
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': setup_complete
        }

class TestScenarios:
    """Predefined test scenarios for different user flows"""
    
    @staticmethod
    def fresh_user_scenario() -> Dict[str, Any]:
        """Generate fresh user test scenario"""
        chat_id = TestDataFactory.generate_chat_id("fresh_user")
        languages = TestDataFactory.generate_language_set(3)
        confirmation = TestDataFactory.generate_confirmation_message(languages)
        
        return {
            "scenario_type": "fresh_user",
            "chat_id": chat_id,
            "languages": languages,
            "confirmation_message": confirmation,
            "expected_languages": ", ".join(languages),
            "start_message": "/start",
            "user_input": ", ".join(languages),
            "conversation_state": TestDataFactory.generate_conversation_state(chat_id, False)
        }
    
    @staticmethod
    def returning_user_scenario() -> Dict[str, Any]:
        """Generate returning user test scenario"""
        chat_id = TestDataFactory.generate_chat_id("returning_user")
        existing_languages = TestDataFactory.generate_language_set(2)
        
        return {
            "scenario_type": "returning_user",
            "chat_id": chat_id,
            "existing_languages": existing_languages,
            "expected_setup_message": f"My languages are: {', '.join(existing_languages)}",
            "test_message": "Hello, please translate this text",
            "conversation_state": TestDataFactory.generate_conversation_state(chat_id, True),
            "database_entry": {
                "language_names": ", ".join(existing_languages),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    
    @staticmethod
    def reset_user_scenario() -> Dict[str, Any]:
        """Generate reset command test scenario"""
        chat_id = TestDataFactory.generate_chat_id("reset_user")
        initial_languages = TestDataFactory.generate_language_set(2)
        
        return {
            "scenario_type": "reset_user",
            "chat_id": chat_id,
            "initial_languages": initial_languages,
            "reset_command": "/reset",
            "conversation_state": TestDataFactory.generate_conversation_state(chat_id, True),
            "database_entry": {
                "language_names": ", ".join(initial_languages),
                "updated_at": datetime.utcnow().isoformat()
            }
        }

# Add scenario methods to TestDataFactory for backward compatibility
TestDataFactory.fresh_user_scenario = TestScenarios.fresh_user_scenario
TestDataFactory.returning_user_scenario = TestScenarios.returning_user_scenario
TestDataFactory.reset_user_scenario = TestScenarios.reset_user_scenario

class TestValidator:
    """Validation utilities for test results"""
    
    @staticmethod
    def validate_parsing_result(expected: bool, actual: bool, test_case: str) -> Dict[str, Any]:
        """Validate language parsing result"""
        success = expected == actual
        return {
            "test_case": test_case,
            "expected": expected,
            "actual": actual,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def validate_database_operation(operation: str, expected: Any, actual: Any) -> Dict[str, Any]:
        """Validate database operation result"""
        success = expected == actual
        return {
            "operation": operation,
            "expected": expected,
            "actual": actual,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def validate_conversation_state(expected_state: Dict[str, Any], actual_state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate conversation state"""
        success = True
        differences = []
        
        for key, expected_value in expected_state.items():
            actual_value = actual_state.get(key)
            if actual_value != expected_value:
                success = False
                differences.append({
                    "key": key,
                    "expected": expected_value,
                    "actual": actual_value
                })
        
        return {
            "success": success,
            "differences": differences,
            "timestamp": datetime.utcnow().isoformat()
        }

class TestReporter:
    """Test result reporting and summary generation"""
    
    def __init__(self):
        self.results = []
        self.start_time = datetime.utcnow()
    
    def add_result(self, test_name: str, success: bool, details: Dict[str, Any] = None):
        """Add test result"""
        self.results.append({
            "test_name": test_name,
            "success": success,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate test execution summary"""
        end_time = datetime.utcnow()
        duration = (end_time - self.start_time).total_seconds()
        
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r["success"])
        failed_tests = total_tests - passed_tests
        success_rate = (passed_tests / total_tests) if total_tests > 0 else 0.0
        
        return {
            "execution_summary": {
                "start_time": self.start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "duration_seconds": duration,
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": success_rate
            },
            "test_details": self.results,
            "validation_status": {
                "parsing_validation": self._validate_component("parsing"),
                "database_validation": self._validate_component("database"),
                "conversation_validation": self._validate_component("conversation"),
                "integration_validation": self._validate_component("integration")
            }
        }
    
    def _validate_component(self, component: str) -> Dict[str, Any]:
        """Validate specific component results"""
        component_tests = [r for r in self.results if component.lower() in r["test_name"].lower()]
        
        if not component_tests:
            return {"status": "SKIPPED", "reason": "No tests found"}
        
        passed = sum(1 for r in component_tests if r["success"])
        total = len(component_tests)
        success_rate = passed / total
        
        # Apply validation thresholds
        threshold_map = {
            "parsing": TestConfig.MIN_PARSING_SUCCESS_RATE,
            "database": TestConfig.MIN_DATABASE_SUCCESS_RATE,
            "conversation": TestConfig.MIN_CONVERSATION_SUCCESS_RATE,
            "integration": TestConfig.MIN_CONVERSATION_SUCCESS_RATE
        }
        
        threshold = threshold_map.get(component, 1.0)
        status = "PASSED" if success_rate >= threshold else "FAILED"
        
        return {
            "status": status,
            "tests_run": total,
            "tests_passed": passed,
            "success_rate": success_rate,
            "threshold": threshold
        }
    
    def print_summary(self):
        """Print formatted test summary"""
        summary = self.generate_summary()
        
        print("\n" + "=" * 80)
        print("TELEGRAM TRANSLATION BOT - COMPREHENSIVE TEST RESULTS")
        print("=" * 80)
        
        exec_summary = summary["execution_summary"]
        print(f"Execution Time: {exec_summary['duration_seconds']:.2f} seconds")
        print(f"Total Tests: {exec_summary['total_tests']}")
        print(f"Passed: {exec_summary['passed_tests']}")
        print(f"Failed: {exec_summary['failed_tests']}")
        print(f"Success Rate: {exec_summary['success_rate']:.1%}")
        
        print("\n" + "-" * 80)
        print("COMPONENT VALIDATION RESULTS")
        print("-" * 80)
        
        for component, validation in summary["validation_status"].items():
            if validation["status"] != "SKIPPED":
                status_icon = "✅" if validation["status"] == "PASSED" else "❌"
                print(f"{status_icon} {component.title()}: {validation['status']} "
                      f"({validation['tests_passed']}/{validation['tests_run']}, "
                      f"{validation['success_rate']:.1%})")
        
        return summary

# Environment setup utilities
def setup_test_environment():
    """Set up test environment with proper configuration"""
    # Load test environment variables
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / '.env.testing'
    load_dotenv(env_path)
    
    # Set testing flag
    os.environ['TESTING'] = '1'
    
    # Ensure required directories exist
    test_dirs = ['tests/temp', 'tests/reports', 'tests/fixtures']
    for dir_path in test_dirs:
        full_path = Path(__file__).parent / dir_path
        full_path.mkdir(parents=True, exist_ok=True)

def cleanup_test_environment():
    """Clean up test environment and temporary files"""
    import glob
    
    # Clean up temporary database files
    test_db_pattern = str(Path(__file__).parent / f"{TestConfig.TEST_DB_PREFIX}*.db")
    for db_file in glob.glob(test_db_pattern):
        try:
            os.unlink(db_file)
        except:
            pass
    
    # Clean up temporary test directories
    temp_dir = Path(__file__).parent / 'tests' / 'temp'
    if temp_dir.exists():
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass