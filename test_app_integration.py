"""Integration Tests for Enhanced Translation Bot

This module provides integration tests for the main application with enhanced features.
"""

import unittest
import json
import time
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock the db module before importing app
mock_db = Mock()
mock_db.get_chat_settings.return_value = None
mock_db.upsert_chat_settings.return_value = None
mock_db.delete_chat_settings.return_value = None
mock_db.init_db.return_value = None
sys.modules['db'] = mock_db

# Mock environment variables
os.environ['TELEGRAM_API_TOKEN'] = 'test_telegram_token'
os.environ['DIRECT_LINE_SECRET'] = 'test_direct_line_secret'
os.environ['DEBUG_LOCAL'] = '1'  # Enable local debug mode

import app
from enhanced_features import OperationMode, MessageType, ResponseType


class TestAppIntegration(unittest.TestCase):
    """Integration tests for the main application"""

    def setUp(self):
        """Set up test environment"""
        self.app = app.app.test_client()
        self.app.testing = True
        
        # Clear conversations state
        app.conversations.clear()
        app.active_pollers.clear()
        app.last_user_message.clear()
        app.recent_activity_ids.clear()
        
        # Reset database mock
        mock_db.reset_mock()

    def create_telegram_message(self, chat_id, user_id, text, chat_type='private'):
        """Helper to create Telegram webhook payload"""
        return {
            'message': {
                'chat': {
                    'id': chat_id,
                    'type': chat_type
                },
                'from': {
                    'id': user_id
                },
                'text': text
            }
        }

    @patch('app.start_direct_line_conversation')
    @patch('app.send_message_to_copilot')
    @patch('app.get_copilot_response')
    def test_fresh_user_start_command(self, mock_get_response, mock_send_message, mock_start_conv):
        """Test fresh user sending /start command"""
        # Mock Direct Line conversation
        mock_start_conv.return_value = ('test_conv_id', 'test_token')
        mock_send_message.return_value = 'test_activity_id'
        mock_get_response.return_value = ([], 'new_watermark')
        
        # No existing settings in database
        mock_db.get_chat_settings.return_value = None
        
        # Send /start command
        message = self.create_telegram_message(12345, 67890, '/start')
        response = self.app.post('/webhook', 
                                json=message,
                                content_type='application/json')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertTrue(result['success'])
        
        # Verify conversation was created
        self.assertIn(12345, app.conversations)
        
        # Verify conversation state
        state = app.state_manager.get_conversation_state(12345)
        self.assertIsNotNone(state)
        self.assertEqual(state.mode, OperationMode.INITIAL_SETUP)
        self.assertTrue(state.awaiting_setup_confirmation)
        
        # Verify Direct Line calls
        mock_start_conv.assert_called_once()
        mock_send_message.assert_called_with('test_conv_id', 'test_token', 'start', from_id=67890)

    @patch('app.start_direct_line_conversation')
    @patch('app.send_message_to_copilot')
    @patch('app.get_copilot_response')
    def test_reset_command_flow(self, mock_get_response, mock_send_message, mock_start_conv):
        """Test /reset command flow"""
        # Setup existing conversation
        app.state_manager.create_conversation_state(
            12345, 'old_conv_id', 'old_token', OperationMode.TRANSLATION
        )
        app.state_manager.mark_setup_complete(12345)
        
        # Mock new conversation
        mock_start_conv.return_value = ('new_conv_id', 'new_token')
        mock_send_message.return_value = 'test_activity_id'
        mock_get_response.return_value = ([], 'new_watermark')
        
        # Send /reset command
        message = self.create_telegram_message(12345, 67890, '/reset')
        response = self.app.post('/webhook',
                                json=message,
                                content_type='application/json')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertTrue(result['success'])
        
        # Verify database was cleared
        mock_db.delete_chat_settings.assert_called_with(12345)
        
        # Verify new conversation state
        state = app.state_manager.get_conversation_state(12345)
        self.assertIsNotNone(state)
        self.assertEqual(state.id, 'new_conv_id')
        self.assertEqual(state.mode, OperationMode.INITIAL_SETUP)
        
        # Verify reset message was sent (simplified approach)
        expected_calls = [
            unittest.mock.call('new_conv_id', 'new_token', 'start', from_id=67890)
        ]
        mock_send_message.assert_has_calls(expected_calls)

    @patch('app.start_direct_line_conversation')
    @patch('app.send_message_to_copilot')
    @patch('app.get_copilot_response')
    def test_returning_user_translation_request(self, mock_get_response, mock_send_message, mock_start_conv):
        """Test returning user sending translation request"""
        # Mock existing settings in database
        mock_db.get_chat_settings.return_value = {
            'language_names': 'English, Spanish, French'
        }
        
        # Mock Direct Line conversation
        mock_start_conv.return_value = ('test_conv_id', 'test_token')
        mock_send_message.return_value = 'test_activity_id'
        
        # Mock context restoration response (setup confirmation)
        context_response = [{
            'id': 'context_activity_id',
            'text': 'Thanks! Setup is complete. Now we speak English, Spanish, French.'
        }]
        mock_get_response.return_value = (context_response, 'new_watermark')
        
        # Send regular message
        message = self.create_telegram_message(12345, 67890, 'Hello world')
        response = self.app.post('/webhook',
                                json=message,
                                content_type='application/json')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertTrue(result['success'])
        
        # Verify conversation state
        state = app.state_manager.get_conversation_state(12345)
        self.assertIsNotNone(state)
        self.assertTrue(state.context_restored)
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.mode, OperationMode.TRANSLATION)

    @patch('app.send_telegram_message')
    def test_setup_confirmation_processing(self, mock_send_telegram):
        """Test processing setup confirmation from Copilot"""
        # Create conversation in setup mode
        app.state_manager.create_conversation_state(
            12345, 'test_conv_id', 'test_token', OperationMode.INITIAL_SETUP
        )
        app.state_manager.update_conversation_state(12345, awaiting_setup_confirmation=True)
        
        # Mock setup confirmation response
        setup_confirmation = "Thanks! Setup is complete. Now we speak English, Spanish. Send your message and I'll translate it."
        
        activity = {
            'id': 'setup_activity_id',
            'text': setup_confirmation
        }
        
        # Process the response
        app.process_copilot_response(12345, activity, 67890)
        
        # Verify setup was parsed and persisted
        mock_db.upsert_chat_settings.assert_called_once()
        args = mock_db.upsert_chat_settings.call_args[0]
        self.assertEqual(args[0], 12345)  # chat_id
        self.assertEqual(args[2], 'English, Spanish')  # language_names
        
        # Verify conversation state was updated
        state = app.state_manager.get_conversation_state(12345)
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.mode, OperationMode.TRANSLATION)
        self.assertFalse(state.awaiting_setup_confirmation)
        
        # Verify message was forwarded to user
        mock_send_telegram.assert_called_with(12345, setup_confirmation)

    @patch('app.send_telegram_message')
    def test_translation_output_processing(self, mock_send_telegram):
        """Test processing translation output from Copilot"""
        # Create conversation in translation mode
        app.state_manager.create_conversation_state(
            12345, 'test_conv_id', 'test_token', OperationMode.TRANSLATION
        )
        app.state_manager.mark_setup_complete(12345)
        app.state_manager.mark_context_restored(12345)
        
        # Mock translation response
        translation_output = "en: Hello world\\nes: Hola mundo\\nfr: Bonjour le monde"
        
        activity = {
            'id': 'translation_activity_id',
            'text': translation_output
        }
        
        # Process the response
        app.process_copilot_response(12345, activity, 67890)
        
        # Verify message was forwarded to user
        mock_send_telegram.assert_called_with(12345, translation_output)
        
        # Verify conversation state remained stable
        state = app.state_manager.get_conversation_state(12345)
        self.assertTrue(state.setup_complete)
        self.assertTrue(state.context_restored)
        self.assertEqual(state.mode, OperationMode.TRANSLATION)

    def test_context_acknowledgment_processing(self):
        """Test processing context acknowledgment (should not forward to user) - removed since not used"""
        # This test is no longer relevant since we simplified context restoration
        # Context is restored through setup confirmation messages instead
        pass

    @patch('app.start_direct_line_conversation')
    def test_connection_error_handling(self, mock_start_conv):
        """Test handling of connection errors"""
        # Mock connection failure
        mock_start_conv.return_value = (None, None)
        
        # Send /start command
        message = self.create_telegram_message(12345, 67890, '/start')
        
        with patch('app.send_telegram_message') as mock_send_telegram:
            response = self.app.post('/webhook',
                                    json=message,
                                    content_type='application/json')
            
            # Verify error response
            self.assertEqual(response.status_code, 200)
            result = json.loads(response.data)
            self.assertFalse(result['success'])
            
            # Verify error message was sent to user
            mock_send_telegram.assert_called_once()
            error_message = mock_send_telegram.call_args[0][1]
            self.assertIn("couldn't connect", error_message)

    def test_group_chat_processing(self):
        """Test processing messages in group chats"""
        # Test group chat with processing enabled
        os.environ['ENABLE_GROUP_CHAT_PROCESSING'] = 'true'
        
        message = self.create_telegram_message(12345, 67890, 'Hello world', 'group')
        
        with patch('app.handle_translation_request') as mock_handle:
            mock_handle.return_value = ('test_conv_id', 'test_token')
            
            response = self.app.post('/webhook',
                                    json=message,
                                    content_type='application/json')
            
            # Verify response
            self.assertEqual(response.status_code, 200)
            result = json.loads(response.data)
            self.assertTrue(result['success'])
            
            # Verify translation handler was called
            mock_handle.assert_called_once()

    def test_non_text_message_ignored(self):
        """Test that non-text messages are ignored"""
        # Create message without text
        message = {
            'message': {
                'chat': {'id': 12345, 'type': 'private'},
                'from': {'id': 67890},
                'photo': [{'file_id': 'test_photo'}]
            }
        }
        
        response = self.app.post('/webhook',
                                json=message,
                                content_type='application/json')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertTrue(result['success'])
        
        # Verify no conversation was created
        self.assertNotIn(12345, app.conversations)

    def test_empty_text_message_ignored(self):
        """Test that empty text messages are ignored"""
        message = self.create_telegram_message(12345, 67890, '')
        
        response = self.app.post('/webhook',
                                json=message,
                                content_type='application/json')
        
        # Verify response
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertTrue(result['success'])
        
        # Verify no conversation was created
        self.assertNotIn(12345, app.conversations)

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.app.get('/health')
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['message'], 'alive')

    def test_dump_settings_endpoint(self):
        """Test settings dump endpoint"""
        # Mock database dump
        mock_db.dump_all.return_value = [
            {'chat_id': '12345', 'language_names': 'English, Spanish'},
            {'chat_id': '67890', 'language_names': 'French, German'}
        ]
        
        response = self.app.get('/dump-settings')
        
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.data)
        self.assertEqual(result['count'], 2)
        self.assertEqual(len(result['rows']), 2)


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""

    def setUp(self):
        """Set up test environment"""
        self.app = app.app.test_client()
        self.app.testing = True
        
        # Clear conversations state
        app.conversations.clear()
        
        # Reset database mock
        mock_db.reset_mock()

    def test_database_error_handling(self):
        """Test handling of database errors"""
        # Mock database error
        mock_db.get_chat_settings.side_effect = Exception("Database connection failed")
        
        message = {
            'message': {
                'chat': {'id': 12345, 'type': 'private'},
                'from': {'id': 67890},
                'text': 'Hello world'
            }
        }
        
        with patch('app.start_direct_line_conversation') as mock_start_conv:
            mock_start_conv.return_value = ('test_conv_id', 'test_token')
            
            with patch('app.send_message_to_copilot') as mock_send_message:
                mock_send_message.return_value = 'test_activity_id'
                
                with patch('app.get_copilot_response') as mock_get_response:
                    mock_get_response.return_value = ([], 'new_watermark')
                    
                    response = self.app.post('/webhook',
                                            json=message,
                                            content_type='application/json')
                    
                    # Should still succeed despite database error
                    self.assertEqual(response.status_code, 200)
                    result = json.loads(response.data)
                    self.assertTrue(result['success'])

    def test_invalid_webhook_data(self):
        """Test handling of invalid webhook data"""
        # Send invalid JSON
        response = self.app.post('/webhook',
                                data='invalid json',
                                content_type='application/json')
        
        self.assertEqual(response.status_code, 400)

    def test_missing_message_fields(self):
        """Test handling of missing required fields"""
        # Message without 'from' field
        message = {
            'message': {
                'chat': {'id': 12345, 'type': 'private'},
                'text': 'Hello world'
            }
        }
        
        response = self.app.post('/webhook',
                                json=message,
                                content_type='application/json')
        
        # Should handle gracefully
        self.assertEqual(response.status_code, 500)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)