"""
Comprehensive Group Chat Functionality Tests for Telegram Translation Bot

This module contains tests for the new group chat message handling functionality
implemented according to the Group Chat Message Handling Fix design document.
"""

import unittest
import json
import os
import sys
import time
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from flask import Flask

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
from test_config import TestDatabase, TestDataFactory, TestValidator, TestConfig


class TestGroupChatMessageHandling(unittest.TestCase):
    """Test group chat message processing with the new implementation"""
    
    def setUp(self):
        """Set up test environment for each test"""
        self.test_db = TestDatabase("group_chat_test")
        app.conversations.clear()
        app.recent_activity_ids.clear()
        app.active_pollers.clear()
        
        # Store original environment variable
        self.original_group_processing = os.environ.get('ENABLE_GROUP_CHAT_PROCESSING')
        
        # Create test Flask app context
        self.app = app.app
        self.app_context = self.app.test_client()
    
    def tearDown(self):
        """Clean up after each test"""
        self.test_db.cleanup()
        
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
        
        group_payload = self._create_group_message_payload(-12345, "Hello world", "group")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg, \
             patch('app.get_copilot_response') as mock_get_response, \
             patch('app.send_telegram_message') as mock_send_telegram:
            
            # Mock successful DirectLine setup
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            mock_get_response.return_value = (["Bot response"], "watermark_789")
            
            response = self.app_context.post('/webhook', 
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            # Verify that message was processed (DirectLine conversation started)
            mock_start_conv.assert_called_once()
            mock_send_msg.assert_called_once()
    
    def test_group_chat_processing_can_be_disabled(self):
        """Test that group chat processing can be disabled via environment variable"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        group_payload = self._create_group_message_payload(-12345, "Hello world", "group")
        
        with patch('app.send_telegram_typing_action') as mock_typing, \
             patch('app.start_direct_line_conversation') as mock_start_conv:
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            # Verify that message was ignored (no DirectLine conversation started)
            mock_start_conv.assert_not_called()
            # Verify no typing indicator was sent for ignored message
            mock_typing.assert_not_called()
    
    def test_group_chat_commands_always_processed(self):
        """Test that commands are always processed in group chats regardless of setting"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        # Test /start command
        start_payload = self._create_group_message_payload(-12345, "/start", "group")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(start_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            mock_start_conv.assert_called_once()
        
        # Reset mocks for /reset command test
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv_reset, \
             patch('app.send_message_to_copilot') as mock_send_msg_reset, \
             patch('app.db.delete_chat_settings') as mock_delete:
            
            reset_payload = self._create_group_message_payload(-12345, "/reset", "group")
            mock_start_conv_reset.return_value = ("conv_456", "token_xyz")
            mock_send_msg_reset.return_value = "activity_789"
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(reset_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            mock_delete.assert_called_once()
            mock_start_conv_reset.assert_called_once()
    
    def test_supergroup_chat_processing(self):
        """Test that supergroup chats are handled the same as regular groups"""
        supergroup_payload = self._create_group_message_payload(-100123456789, "Test message", "supergroup")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(supergroup_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            mock_start_conv.assert_called_once()
    
    def test_group_chat_typing_indicator(self):
        """Test that typing indicators are sent for group chat messages"""
        group_payload = self._create_group_message_payload(-12345, "Test typing", "group")
        
        with patch('app.send_telegram_typing_action') as mock_typing, \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot'):
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            
            # Wait a bit for the typing thread to execute
            time.sleep(1.5)
            
            # Verify typing indicator was sent
            mock_typing.assert_called_once()
    
    def test_group_chat_conversation_isolation(self):
        """Test that group chats have isolated conversations from private chats"""
        group_chat_id = -12345
        private_chat_id = 54321
        
        group_payload = self._create_group_message_payload(group_chat_id, "Group message", "group")
        private_payload = self._create_private_message_payload(private_chat_id, "Private message")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg, \
             patch('app.get_copilot_response') as mock_get_response:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            mock_get_response.return_value = (["Response"], "watermark")
            
            # Process group message
            response1 = self.app_context.post('/webhook',
                                            data=json.dumps(group_payload),
                                            content_type='application/json')
            
            # Process private message  
            response2 = self.app_context.post('/webhook',
                                            data=json.dumps(private_payload),
                                            content_type='application/json')
            
            self.assertEqual(response1.status_code, 200)
            self.assertEqual(response2.status_code, 200)
            
            # Verify separate conversations were created
            self.assertIn(group_chat_id, app.conversations)
            self.assertIn(private_chat_id, app.conversations)
            self.assertNotEqual(app.conversations[group_chat_id], app.conversations[private_chat_id])
    
    def test_group_chat_error_messages_in_english(self):
        """Test that error messages in group chats are displayed in English"""
        group_payload = self._create_group_message_payload(-12345, "Test error", "group")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_telegram_message') as mock_send_telegram:
            
            # Simulate DirectLine connection failure
            mock_start_conv.return_value = (None, None)
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            # Should still return 200 but send error message
            self.assertEqual(response.status_code, 200)
            
            # Verify English error message was sent
            mock_send_telegram.assert_called_once()
            call_args = mock_send_telegram.call_args
            error_message = call_args[0][1]  # Second argument is the message text
            
            # Error message should be in English for group chats
            self.assertIn("Sorry", error_message)
            self.assertNotIn("Извините", error_message)  # Should not be in Russian
    
    def test_group_chat_multiple_users(self):
        """Test handling of messages from multiple users in the same group"""
        group_chat_id = -12345
        
        user1_payload = self._create_group_message_payload(group_chat_id, "Message from user 1", "group", user_id=111)
        user2_payload = self._create_group_message_payload(group_chat_id, "Message from user 2", "group", user_id=222)
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            
            # Process messages from both users
            response1 = self.app_context.post('/webhook',
                                            data=json.dumps(user1_payload),
                                            content_type='application/json')
            
            response2 = self.app_context.post('/webhook',
                                            data=json.dumps(user2_payload),
                                            content_type='application/json')
            
            self.assertEqual(response1.status_code, 200)
            self.assertEqual(response2.status_code, 200)
            
            # Both users should use the same group conversation but with different user IDs
            self.assertEqual(mock_send_msg.call_count, 2)
            
            # Verify user IDs were passed correctly to Copilot
            call_args_list = mock_send_msg.call_args_list
            user_id_1 = call_args_list[0].kwargs.get('from_id', None)
            user_id_2 = call_args_list[1].kwargs.get('from_id', None)
            
            self.assertEqual(user_id_1, 111)
            self.assertEqual(user_id_2, 222)
    
    def test_regression_private_chat_still_works(self):
        """Test that private chat functionality is not affected by group chat changes"""
        private_payload = self._create_private_message_payload(54321, "Private chat message")
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.send_message_to_copilot') as mock_send_msg, \
             patch('app.get_copilot_response') as mock_get_response, \
             patch('app.send_telegram_message') as mock_send_telegram:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            mock_send_msg.return_value = "activity_456"
            mock_get_response.return_value = (["Bot response"], "watermark_789")
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(private_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            mock_start_conv.assert_called_once()
            mock_send_msg.assert_called_once()
    
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
            ('', False),  # Empty string should default to false for missing env var
            ('invalid', False),
        ]
        
        for env_value, expected_processing in test_cases:
            with self.subTest(env_value=env_value):
                os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = env_value
                
                group_payload = self._create_group_message_payload(-12345, "Test config", "group")
                
                with patch('app.send_telegram_typing_action'), \
                     patch('app.start_direct_line_conversation') as mock_start_conv:
                    
                    mock_start_conv.return_value = ("conv_123", "token_abc")
                    
                    response = self.app_context.post('/webhook',
                                                   data=json.dumps(group_payload),
                                                   content_type='application/json')
                    
                    self.assertEqual(response.status_code, 200)
                    
                    if expected_processing:
                        mock_start_conv.assert_called_once()
                    else:
                        mock_start_conv.assert_not_called()
                    
                    # Reset mock for next iteration
                    mock_start_conv.reset_mock()

    def _get_comprehensive_mocks(self):
        """Helper method to get comprehensive mocks for all webhook tests"""
        return [
            patch('app.send_telegram_typing_action'),
            patch('app.start_direct_line_conversation'),
            patch('app.send_message_to_copilot'), 
            patch('app.get_copilot_response'),
            patch('app.send_telegram_message'),
            patch('app.db.delete_chat_settings'),
            patch('app.db.get_chat_settings'),
            patch('app.db.upsert_chat_settings')
        ]
    
    def _create_group_message_payload(self, chat_id: int, text: str, chat_type: str = "group", user_id: int = 12345):
        """Helper method to create group message payload"""
        return {
            "message": {
                "message_id": int(time.time()),
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": f"TestUser{user_id}",
                    "username": f"testuser_{user_id}"
                },
                "chat": {
                    "id": chat_id,
                    "type": chat_type,
                    "title": f"Test {chat_type.title()} Chat"
                },
                "date": int(time.time()),
                "text": text
            }
        }
    
    def _create_private_message_payload(self, chat_id: int, text: str, user_id: int = None):
        """Helper method to create private message payload"""
        if user_id is None:
            user_id = chat_id
        
        return {
            "message": {
                "message_id": int(time.time()),
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": f"TestUser{user_id}",
                    "username": f"testuser_{user_id}"
                },
                "chat": {
                    "id": chat_id,
                    "type": "private",
                    "first_name": f"TestUser{user_id}",
                    "username": f"testuser_{user_id}"
                },
                "date": int(time.time()),
                "text": text
            }
        }


class TestGroupChatLogging(unittest.TestCase):
    """Test logging behavior for group chat functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.app = app.app
        self.app_context = self.app.test_client()
        
        # Store original environment variable
        self.original_group_processing = os.environ.get('ENABLE_GROUP_CHAT_PROCESSING')
    
    def tearDown(self):
        """Clean up after test"""
        # Restore original environment variable
        if self.original_group_processing is not None:
            os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = self.original_group_processing
        elif 'ENABLE_GROUP_CHAT_PROCESSING' in os.environ:
            del os.environ['ENABLE_GROUP_CHAT_PROCESSING']
    
    def test_group_chat_processing_logged(self):
        """Test that group chat processing decisions are properly logged"""
        group_payload = {
            "message": {
                "message_id": 123,
                "from": {"id": 12345, "is_bot": False, "first_name": "TestUser"},
                "chat": {"id": -12345, "type": "group", "title": "Test Group"},
                "date": int(time.time()),
                "text": "Test message"
            }
        }
        
        with patch('app.send_telegram_typing_action'), \
             patch('app.start_direct_line_conversation') as mock_start_conv, \
             patch('app.app.logger.info') as mock_logger:
            
            mock_start_conv.return_value = ("conv_123", "token_abc")
            
            response = self.app_context.post('/webhook',
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            
            # Verify that group chat processing decision was logged
            log_calls = [call.args[0] for call in mock_logger.call_args_list]
            group_processing_logged = any("Processing message in group chat" in log for log in log_calls)
            self.assertTrue(group_processing_logged, "Group chat processing should be logged")
    
    def test_group_chat_disabled_logged(self):
        """Test that disabled group chat processing is properly logged"""
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'false'
        
        group_payload = {
            "message": {
                "message_id": 123,
                "from": {"id": 12345, "is_bot": False, "first_name": "TestUser"},
                "chat": {"id": -12345, "type": "group", "title": "Test Group"},
                "date": int(time.time()),
                "text": "Test message"
            }
        }
        
        with patch('app.app.logger.info') as mock_logger:
            response = self.app_context.post('/webhook',
                                           data=json.dumps(group_payload),
                                           content_type='application/json')
            
            self.assertEqual(response.status_code, 200)
            
            # Verify that the ignore message was logged
            log_calls = [call.args[0] for call in mock_logger.call_args_list]
            disabled_processing_logged = any("Group chat processing disabled" in log for log in log_calls)
            self.assertTrue(disabled_processing_logged, "Disabled group chat processing should be logged")


def run_group_chat_functionality_tests():
    """Run all group chat functionality tests with comprehensive reporting"""
    print("=" * 80)
    print("GROUP CHAT FUNCTIONALITY TESTS - TELEGRAM TRANSLATION BOT")
    print("=" * 80)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add group chat test classes
    group_chat_test_classes = [
        TestGroupChatMessageHandling,
        TestGroupChatLogging,
    ]
    
    for test_class in group_chat_test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, buffer=True)
    result = runner.run(suite)
    
    # Print detailed summary
    print("\n" + "=" * 80)
    print("GROUP CHAT FUNCTIONALITY TEST RESULTS")
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
    success, test_result = run_group_chat_functionality_tests()
    sys.exit(0 if success else 1)