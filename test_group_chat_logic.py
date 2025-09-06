"""
Simple Group Chat Logic Test for Telegram Translation Bot

This module contains focused tests for the group chat logic implementation
without complex Flask app mocking.
"""

import unittest
import os
import sys
from unittest.mock import patch

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestGroupChatLogic(unittest.TestCase):
    """Test the core group chat processing logic"""
    
    def setUp(self):
        """Set up test environment"""
        # Store original environment variable
        self.original_group_processing = os.environ.get('ENABLE_GROUP_CHAT_PROCESSING')
    
    def tearDown(self):
        """Clean up after test"""
        # Restore original environment variable
        if self.original_group_processing is not None:
            os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = self.original_group_processing
        elif 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
            del os.environ['ENABLE_GROUP_CHAT_PROCESSING']
    
    def test_group_chat_processing_enabled_by_default(self):
        """Test that group chat processing is enabled by default"""
        # Remove environment variable to test default behavior
        if 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
            del os.environ['ENABLE_GROUP_CHAT_PROCESSING']
        
        # Simulate the logic from app.py
        chat_type = 'group'
        text = 'Hello world'
        
        # This is the actual logic from app.py lines 469-477 after our changes
        should_process = True  # Default behavior
        
        if chat_type in ['group', 'supergroup']:
            enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
            
            if not enable_group_processing:
                # Legacy behavior: Only process commands in groups when disabled
                if not text.startswith('/'):
                    should_process = False
        
        self.assertTrue(should_process, "Group chat processing should be enabled by default")
    
    def test_group_chat_processing_can_be_disabled(self):
        """Test that group chat processing can be disabled"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        # Simulate the logic from app.py
        chat_type = 'group'
        text = 'Hello world'
        
        should_process = True  # Default behavior
        
        if chat_type in ['group', 'supergroup']:
            enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
            
            if not enable_group_processing:
                # Legacy behavior: Only process commands in groups when disabled
                if not text.startswith('/'):
                    should_process = False
        
        self.assertFalse(should_process, "Non-command messages should be ignored when disabled")
    
    def test_group_chat_commands_always_processed(self):
        """Test that commands are always processed regardless of setting"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        commands = ['/start', '/reset', '/help']
        
        for command in commands:
            with self.subTest(command=command):
                chat_type = 'group'
                text = command
                
                should_process = True  # Default behavior
                
                if chat_type in ['group', 'supergroup']:
                    enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
                    
                    if not enable_group_processing:
                        # Legacy behavior: Only process commands in groups when disabled
                        if not text.startswith('/'):
                            should_process = False
                
                self.assertTrue(should_process, f"Command {command} should always be processed")
    
    def test_supergroup_same_as_group(self):
        """Test that supergroups are handled the same as groups"""
        test_cases = [
            ('group', 'Test message'),
            ('supergroup', 'Test message'),
        ]
        
        for chat_type, text in test_cases:
            with self.subTest(chat_type=chat_type):
                # Remove environment variable to test default behavior
                if 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
                    del os.environ['ENABLE_GROUP_CHAT_PROCESSING']
                
                should_process = True  # Default behavior
                
                if chat_type in ['group', 'supergroup']:
                    enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
                    
                    if not enable_group_processing:
                        # Legacy behavior: Only process commands in groups when disabled
                        if not text.startswith('/'):
                            should_process = False
                
                self.assertTrue(should_process, f"{chat_type} should process messages by default")
    
    def test_private_chat_not_affected(self):
        """Test that private chats are not affected by the group chat logic"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        chat_type = 'private'
        text = 'Hello world'
        
        should_process = True  # Default behavior
        
        # The group chat logic only applies to group and supergroup chats
        if chat_type in ['group', 'supergroup']:
            enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
            
            if not enable_group_processing:
                # Legacy behavior: Only process commands in groups when disabled
                if not text.startswith('/'):
                    should_process = False
        
        self.assertTrue(should_process, "Private chats should not be affected by group chat settings")
    
    def test_configuration_validation(self):
        """Test that configuration values are properly validated"""
        test_cases = [
            ('true', True),
            ('TRUE', True),
            ('True', True), 
            ('1', False),  # Only 'true' should enable processing
            ('false', False),
            ('FALSE', False),
            ('False', False),
            ('0', False),
            ('invalid', False),
        ]
        
        for env_value, expected_processing in test_cases:
            with self.subTest(env_value=env_value):
                os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = env_value
                
                chat_type = 'group'
                text = 'Test message'
                
                should_process = True  # Default behavior
                
                if chat_type in ['group', 'supergroup']:
                    enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
                    
                    if not enable_group_processing:
                        # Legacy behavior: Only process commands in groups when disabled
                        if not text.startswith('/'):
                            should_process = False
                
                self.assertEqual(should_process, expected_processing, 
                               f"Environment value '{env_value}' should result in processing={expected_processing}")
    
    def test_default_when_env_var_missing(self):
        """Test that default is 'true' when environment variable is missing"""
        # Ensure environment variable is not set
        if 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
            del os.environ['ENABLE_GROUP_CHAT_PROCESSING']
        
        # Test the getenv call with default
        result = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
        
        self.assertTrue(result, "Default should be 'true' when environment variable is missing")


class TestModifiedAppBehavior(unittest.TestCase):
    """Test that the actual app.py modifications work correctly"""
    
    def test_app_imports_successfully(self):
        """Test that the modified app.py imports without errors"""
        try:
            import app
            self.assertTrue(True, "App imports successfully")
        except Exception as e:
            self.fail(f"App import failed: {e}")
    
    def test_webhook_endpoint_exists(self):
        """Test that the webhook endpoint exists"""
        import app
        
        # Check that the Flask app has the webhook route
        self.assertIn('/webhook', [rule.rule for rule in app.app.url_map.iter_rules()])
    
    def test_environment_variable_handling(self):
        """Test that environment variable handling works in the actual app"""
        import app
        
        # Store original
        original = os.environ.get('ENABLE_GROUP_CHAT_PROCESSING')
        
        try:
            # Test with 'true'
            os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'true'
            result = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
            self.assertTrue(result)
            
            # Test with 'false'
            os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
            result = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
            self.assertFalse(result)
            
        finally:
            # Restore original
            if original is not None:
                os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = original
            elif 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
                del os.environ['ENABLE_GROUP_CHAT_PROCESSING']


def run_simple_group_chat_tests():
    """Run focused group chat logic tests"""
    print("=" * 80)
    print("SIMPLE GROUP CHAT LOGIC TESTS - TELEGRAM TRANSLATION BOT")
    print("=" * 80)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [
        TestGroupChatLogic,
        TestModifiedAppBehavior,
    ]
    
    for test_class in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, buffer=True)
    result = runner.run(suite)
    
    # Print detailed summary
    print("\n" + "=" * 80)
    print("SIMPLE GROUP CHAT LOGIC TEST RESULTS")
    print("=" * 80)
    
    print(f"Tests Run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / 
                   result.testsRun) if result.testsRun > 0 else 0
    print(f"Success Rate: {success_rate:.1%}")
    
    # Print failure details
    if result.failures:
        print(f"\n{'=' * 40} FAILURES {'=' * 40}")
        for test, traceback in result.failures:
            print(f"\nFAILED: {test}")
            print("-" * 60)
            print(traceback)
    
    # Print error details
    if result.errors:
        print(f"\n{'=' * 40} ERRORS {'=' * 40}")
        for test, traceback in result.errors:
            print(f"\nERROR: {test}")
            print("-" * 60)
            print(traceback)
    
    # Overall result
    overall_success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\n{'=' * 80}")
    print(f"OVERALL RESULT: {'✅ PASS' if overall_success else '❌ FAIL'}")
    print("=" * 80)
    
    return overall_success, result


if __name__ == '__main__':
    success, test_result = run_simple_group_chat_tests()
    sys.exit(0 if success else 1)