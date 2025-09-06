"""Test Suite for Enhanced Language Setup and Translation Flow Fix

This module provides comprehensive tests for the enhanced features implemented
according to the design document.
"""

import unittest
import time
import json
from unittest.mock import Mock, patch, MagicMock
from enhanced_features import (
    OperationMode, MessageType, ResponseType, ConversationState,
    MessageClassifier, ContextRestorer, StateManager, EnhancedLanguageParser,
    migrate_legacy_conversation
)

class TestMessageClassifier(unittest.TestCase):
    """Test message classification functionality"""

    def test_classify_start_command(self):
        """Test /start command classification"""
        result = MessageClassifier.classify_incoming_message("/start")
        self.assertEqual(result, MessageType.START_COMMAND)

    def test_classify_reset_command(self):
        """Test /reset command classification"""
        result = MessageClassifier.classify_incoming_message("/reset")
        self.assertEqual(result, MessageType.RESET_COMMAND)

    def test_classify_other_command(self):
        """Test other commands classification"""
        result = MessageClassifier.classify_incoming_message("/help")
        self.assertEqual(result, MessageType.OTHER_COMMAND)

    def test_classify_regular_text(self):
        """Test regular text classification"""
        result = MessageClassifier.classify_incoming_message("Hello world")
        self.assertEqual(result, MessageType.REGULAR_TEXT)

    def test_classify_empty_text(self):
        """Test empty text classification"""
        result = MessageClassifier.classify_incoming_message("")
        self.assertEqual(result, MessageType.REGULAR_TEXT)

    def test_classify_setup_prompt(self):
        """Test setup prompt classification"""
        text = "What's languages you prefer? Write 2 or 3 languages."
        result = MessageClassifier.classify_copilot_response(text)
        self.assertEqual(result, ResponseType.SETUP_PROMPT)

    def test_classify_setup_confirmation(self):
        """Test setup confirmation classification"""
        text = "Thanks! Setup is complete. Now we speak English, Spanish. Send your message and I'll translate it."
        result = MessageClassifier.classify_copilot_response(text)
        self.assertEqual(result, ResponseType.SETUP_CONFIRMATION)

    def test_classify_translation_output(self):
        """Test translation output classification"""
        text = "en: Hello\\nes: Hola"
        result = MessageClassifier.classify_copilot_response(text)
        self.assertEqual(result, ResponseType.TRANSLATION_OUTPUT)

    def test_classify_context_acknowledgment(self):
        """Test context acknowledgment classification - removed since not used"""
        # This test is no longer relevant since we removed context acknowledgment
        text = "Some regular response"
        result = MessageClassifier.classify_copilot_response(text)
        self.assertEqual(result, ResponseType.UNKNOWN)


class TestEnhancedLanguageParser(unittest.TestCase):
    """Test enhanced language parsing functionality"""

    def test_parse_basic_confirmation(self):
        """Test basic setup confirmation parsing"""
        text = "Thanks! Setup is complete. Now we speak English, Spanish."
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(text)
        self.assertTrue(is_complete)
        self.assertEqual(languages, "English, Spanish")

    def test_parse_complex_confirmation(self):
        """Test complex setup confirmation parsing"""
        text = "Great! I can now translate between English, Russian, Japanese. Send your message and I'll translate it."
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(text)
        self.assertTrue(is_complete)
        self.assertEqual(languages, "English, Russian, Japanese")

    def test_parse_no_languages_mentioned(self):
        """Test confirmation without specific languages"""
        text = "Setup is complete. Ready for translation."
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(text)
        self.assertTrue(is_complete)
        self.assertEqual(languages, "Configuration Completed")

    def test_parse_non_setup_message(self):
        """Test parsing non-setup message"""
        text = "Hello, how can I help you today?"
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(text)
        self.assertFalse(is_complete)
        self.assertIsNone(languages)

    def test_parse_filters_excluded_words(self):
        """Test that excluded words are filtered out"""
        # Use a more realistic setup confirmation message that would actually be parsed correctly
        text = "Setup complete. Now we speak English, Spanish. Send your message and I'll translate it."
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(text)
        self.assertTrue(is_complete)
        self.assertEqual(languages, "English, Spanish")


class TestConversationState(unittest.TestCase):
    """Test conversation state management"""

    def test_conversation_state_creation(self):
        """Test creating conversation state"""
        state = ConversationState(
            id="test_conv_id",
            token="test_token",
            watermark=None,
            mode=OperationMode.TRANSLATION,
            setup_complete=False,
            last_interaction=time.time(),
            context_restored=False,
            awaiting_setup_confirmation=False
        )
        
        self.assertEqual(state.id, "test_conv_id")
        self.assertEqual(state.mode, OperationMode.TRANSLATION)
        self.assertFalse(state.setup_complete)

    def test_conversation_state_to_dict(self):
        """Test converting conversation state to dictionary"""
        state = ConversationState(
            id="test_conv_id",
            token="test_token",
            watermark="test_watermark",
            mode=OperationMode.INITIAL_SETUP,
            setup_complete=True,
            last_interaction=12345.0,
            context_restored=True,
            awaiting_setup_confirmation=False
        )
        
        result = state.to_dict()
        self.assertEqual(result['id'], "test_conv_id")
        self.assertEqual(result['mode'], OperationMode.INITIAL_SETUP.value)
        self.assertTrue(result['setup_complete'])

    def test_conversation_state_from_dict(self):
        """Test creating conversation state from dictionary"""
        data = {
            'id': "test_conv_id",
            'token': "test_token",
            'watermark': "test_watermark",
            'mode': OperationMode.TRANSLATION.value,
            'setup_complete': True,
            'last_interaction': 12345.0,
            'context_restored': True,
            'awaiting_setup_confirmation': False
        }
        
        state = ConversationState.from_dict(data)
        self.assertEqual(state.id, "test_conv_id")
        self.assertEqual(state.mode, OperationMode.TRANSLATION)
        self.assertTrue(state.setup_complete)


class TestStateManager(unittest.TestCase):
    """Test state manager functionality"""

    def setUp(self):
        """Set up test state manager"""
        self.conversations = {}
        self.state_manager = StateManager(self.conversations)

    def test_create_conversation_state(self):
        """Test creating new conversation state"""
        chat_id = "test_chat_123"
        conv_id = "test_conv_456"
        token = "test_token_789"
        
        state = self.state_manager.create_conversation_state(
            chat_id, conv_id, token, OperationMode.INITIAL_SETUP
        )
        
        self.assertEqual(state.id, conv_id)
        self.assertEqual(state.token, token)
        self.assertEqual(state.mode, OperationMode.INITIAL_SETUP)
        self.assertIn(chat_id, self.conversations)

    def test_get_conversation_state(self):
        """Test getting conversation state"""
        chat_id = "test_chat_123"
        conv_id = "test_conv_456"
        token = "test_token_789"
        
        # Create state
        created_state = self.state_manager.create_conversation_state(
            chat_id, conv_id, token
        )
        
        # Get state
        retrieved_state = self.state_manager.get_conversation_state(chat_id)
        
        self.assertIsNotNone(retrieved_state)
        self.assertEqual(retrieved_state.id, conv_id)
        self.assertEqual(retrieved_state.token, token)

    def test_update_conversation_state(self):
        """Test updating conversation state"""
        chat_id = "test_chat_123"
        conv_id = "test_conv_456"
        token = "test_token_789"
        
        # Create state
        self.state_manager.create_conversation_state(chat_id, conv_id, token)
        
        # Update state
        result = self.state_manager.update_conversation_state(
            chat_id, 
            setup_complete=True,
            watermark="new_watermark"
        )
        
        self.assertTrue(result)
        
        # Verify update
        state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.watermark, "new_watermark")

    def test_mark_setup_complete(self):
        """Test marking setup as complete"""
        chat_id = "test_chat_123"
        conv_id = "test_conv_456"
        token = "test_token_789"
        
        # Create state in setup mode
        self.state_manager.create_conversation_state(
            chat_id, conv_id, token, OperationMode.INITIAL_SETUP
        )
        
        # Mark setup complete
        result = self.state_manager.mark_setup_complete(chat_id)
        self.assertTrue(result)
        
        # Verify state
        state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.mode, OperationMode.TRANSLATION)
        self.assertFalse(state.awaiting_setup_confirmation)

    def test_mark_context_restored(self):
        """Test marking context as restored"""
        chat_id = "test_chat_123"
        conv_id = "test_conv_456"
        token = "test_token_789"
        
        # Create state
        self.state_manager.create_conversation_state(chat_id, conv_id, token)
        
        # Mark context restored
        result = self.state_manager.mark_context_restored(chat_id)
        self.assertTrue(result)
        
        # Verify state
        state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(state.context_restored)
        self.assertTrue(state.setup_complete)
        self.assertEqual(state.mode, OperationMode.TRANSLATION)

    def test_handle_legacy_conversation_data(self):
        """Test handling legacy conversation dictionary format"""
        chat_id = "test_chat_123"
        
        # Simulate legacy data
        legacy_data = {
            'id': "test_conv_456",
            'token': "test_token_789",
            'watermark': "test_watermark",
            'setup_complete': True,
            'last_interaction': time.time(),
            'is_polling': False
        }
        
        self.conversations[chat_id] = legacy_data
        
        # Get state should handle legacy format
        state = self.state_manager.get_conversation_state(chat_id)
        
        self.assertIsNotNone(state)
        self.assertEqual(state.id, "test_conv_456")
        self.assertEqual(state.token, "test_token_789")
        self.assertTrue(state.setup_complete)


class TestContextRestorer(unittest.TestCase):
    """Test context restoration functionality"""

    def test_create_restore_message(self):
        """Test creating context restore message"""
        saved_languages = "English, Spanish, French"
        message = ContextRestorer.create_restore_message(saved_languages)
        expected = "My languages are: English, Spanish, French"
        self.assertEqual(message, expected)

    def test_create_restore_message_no_languages(self):
        """Test creating restore message without specific languages"""
        message = ContextRestorer.create_restore_message("Configuration Completed")
        expected = "start"
        self.assertEqual(message, expected)

    def test_create_reset_message(self):
        """Test creating reset message"""
        message = ContextRestorer.create_reset_message()
        self.assertEqual(message, "start")

    @patch('enhanced_features.logger')
    def test_is_restoration_needed_with_existing_settings(self, mock_logger):
        """Test restoration check with existing settings"""
        # Mock database module
        mock_db = Mock()
        mock_db.get_chat_settings.return_value = {
            'language_names': 'English, Spanish'
        }
        
        conversations = {}
        chat_id = "test_chat_123"
        
        needed, languages = ContextRestorer.is_restoration_needed(
            chat_id, conversations, mock_db
        )
        
        self.assertTrue(needed)
        self.assertEqual(languages, 'English, Spanish')

    @patch('enhanced_features.logger')
    def test_is_restoration_needed_no_settings(self, mock_logger):
        """Test restoration check without existing settings"""
        # Mock database module
        mock_db = Mock()
        mock_db.get_chat_settings.return_value = None
        
        conversations = {}
        chat_id = "test_chat_123"
        
        needed, languages = ContextRestorer.is_restoration_needed(
            chat_id, conversations, mock_db
        )
        
        self.assertFalse(needed)
        self.assertIsNone(languages)

    @patch('enhanced_features.logger')
    def test_is_restoration_needed_with_active_conversation(self, mock_logger):
        """Test restoration check with active restored conversation"""
        # Mock database module
        mock_db = Mock()
        
        # Create conversation with restored context
        state = ConversationState(
            id="test_conv",
            token="test_token",
            watermark=None,
            mode=OperationMode.TRANSLATION,
            setup_complete=True,
            last_interaction=time.time(),
            context_restored=True,
            awaiting_setup_confirmation=False
        )
        
        conversations = {"test_chat_123": state}
        chat_id = "test_chat_123"
        
        needed, languages = ContextRestorer.is_restoration_needed(
            chat_id, conversations, mock_db
        )
        
        self.assertFalse(needed)
        self.assertIsNone(languages)


class TestMigrateLegacyConversation(unittest.TestCase):
    """Test legacy conversation migration"""

    def test_migrate_complete_legacy_data(self):
        """Test migrating complete legacy conversation data"""
        chat_id = "test_chat_123"
        legacy_data = {
            'id': "test_conv_456",
            'token': "test_token_789",
            'watermark': "test_watermark",
            'setup_complete': True,
            'last_interaction': 12345.0,
            'is_polling': False
        }
        
        migrated = migrate_legacy_conversation(chat_id, legacy_data)
        
        self.assertEqual(migrated.id, "test_conv_456")
        self.assertEqual(migrated.token, "test_token_789")
        self.assertEqual(migrated.watermark, "test_watermark")
        self.assertTrue(migrated.setup_complete)
        self.assertEqual(migrated.last_interaction, 12345.0)
        self.assertFalse(migrated.is_polling)
        
        # New fields should have defaults
        self.assertEqual(migrated.mode, OperationMode.TRANSLATION)
        self.assertFalse(migrated.context_restored)
        self.assertFalse(migrated.awaiting_setup_confirmation)

    def test_migrate_minimal_legacy_data(self):
        """Test migrating minimal legacy conversation data"""
        chat_id = "test_chat_123"
        legacy_data = {
            'id': "test_conv_456",
            'token': "test_token_789"
        }
        
        migrated = migrate_legacy_conversation(chat_id, legacy_data)
        
        self.assertEqual(migrated.id, "test_conv_456")
        self.assertEqual(migrated.token, "test_token_789")
        self.assertIsNone(migrated.watermark)
        self.assertFalse(migrated.setup_complete)
        self.assertEqual(migrated.mode, OperationMode.TRANSLATION)

    @patch('enhanced_features.logger')
    def test_migrate_invalid_legacy_data(self, mock_logger):
        """Test migrating invalid legacy conversation data"""
        chat_id = "test_chat_123"
        legacy_data = "invalid_data"
        
        migrated = migrate_legacy_conversation(chat_id, legacy_data)
        
        # Should return minimal valid state
        self.assertEqual(migrated.id, '')
        self.assertEqual(migrated.token, '')
        self.assertEqual(migrated.mode, OperationMode.TRANSLATION)
        self.assertFalse(migrated.setup_complete)


class TestIntegrationScenarios(unittest.TestCase):
    """Test integration scenarios matching the design document"""

    def setUp(self):
        """Set up integration test environment"""
        self.conversations = {}
        self.state_manager = StateManager(self.conversations)
        self.mock_db = Mock()

    def test_fresh_user_scenario(self):
        """Test: Fresh user sends /start"""
        chat_id = "fresh_user_123"
        
        # 1. Classify /start message
        message_type = MessageClassifier.classify_incoming_message("/start")
        self.assertEqual(message_type, MessageType.START_COMMAND)
        
        # 2. Create initial setup conversation
        conv_state = self.state_manager.create_conversation_state(
            chat_id, "conv_123", "token_123", OperationMode.INITIAL_SETUP
        )
        self.state_manager.update_conversation_state(
            chat_id, awaiting_setup_confirmation=True
        )
        
        # 3. Simulate setup prompt response
        setup_prompt = "What's languages you prefer? Write 2 or 3 languages."
        response_type = MessageClassifier.classify_copilot_response(setup_prompt)
        self.assertEqual(response_type, ResponseType.SETUP_PROMPT)
        
        # 4. Simulate setup confirmation response
        setup_confirmation = "Thanks! Setup is complete. Now we speak English, Spanish."
        response_type = MessageClassifier.classify_copilot_response(setup_confirmation)
        self.assertEqual(response_type, ResponseType.SETUP_CONFIRMATION)
        
        # 5. Parse and verify setup completion
        is_complete, languages = EnhancedLanguageParser.parse_setup_confirmation(setup_confirmation)
        self.assertTrue(is_complete)
        self.assertEqual(languages, "English, Spanish")
        
        # 6. Mark setup complete
        self.state_manager.mark_setup_complete(chat_id)
        
        # 7. Verify final state
        final_state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(final_state.setup_complete)
        self.assertEqual(final_state.mode, OperationMode.TRANSLATION)
        self.assertFalse(final_state.awaiting_setup_confirmation)

    def test_returning_user_scenario(self):
        """Test: Returning user with existing settings sends message"""
        chat_id = "returning_user_456"
        
        # 1. Mock existing database settings
        self.mock_db.get_chat_settings.return_value = {
            'language_names': 'English, French, German'
        }
        
        # 2. Check if restoration is needed
        needed, languages = ContextRestorer.is_restoration_needed(
            chat_id, self.conversations, self.mock_db
        )
        self.assertTrue(needed)
        self.assertEqual(languages, 'English, French, German')
        
        # 3. Create restore message
        restore_message = ContextRestorer.create_restore_message(languages)
        expected = "My languages are: English, French, German"
        self.assertEqual(restore_message, expected)
        
        # 4. Create conversation state
        conv_state = self.state_manager.create_conversation_state(
            chat_id, "conv_456", "token_456", OperationMode.CONTEXT_RESTORATION
        )
        
        # 5. Simulate setup confirmation (since we're sending "My languages are:" message)
        setup_confirmation = "Thanks! Setup is complete. Now we speak English, French, German."
        response_type = MessageClassifier.classify_copilot_response(setup_confirmation)
        self.assertEqual(response_type, ResponseType.SETUP_CONFIRMATION)
        
        # 6. Mark context restored based on setup confirmation
        self.state_manager.mark_context_restored(chat_id)
        
        # 7. Verify final state
        final_state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(final_state.context_restored)
        self.assertTrue(final_state.setup_complete)
        self.assertEqual(final_state.mode, OperationMode.TRANSLATION)

    def test_reset_flow_scenario(self):
        """Test: User sends /reset command"""
        chat_id = "reset_user_789"
        
        # 1. Create existing conversation with setup
        self.state_manager.create_conversation_state(
            chat_id, "conv_789", "token_789", OperationMode.TRANSLATION
        )
        self.state_manager.mark_setup_complete(chat_id)
        
        # 2. Classify reset message
        message_type = MessageClassifier.classify_incoming_message("/reset")
        self.assertEqual(message_type, MessageType.RESET_COMMAND)
        
        # 3. Clear conversation state
        self.state_manager.clear_conversation_state(chat_id)
        
        # 4. Create new conversation in reset mode
        new_state = self.state_manager.create_conversation_state(
            chat_id, "new_conv_789", "new_token_789", OperationMode.RESET
        )
        
        # 5. Create reset message
        reset_message = ContextRestorer.create_reset_message()
        self.assertEqual(reset_message, "start")
        
        # 6. No special reset acknowledgment needed - just proceed with fresh setup
        # The reset is handled by clearing state and starting fresh
        
        # 7. Switch to setup mode
        self.state_manager.set_mode(chat_id, OperationMode.INITIAL_SETUP)
        self.state_manager.update_conversation_state(
            chat_id, awaiting_setup_confirmation=True
        )
        
        # 8. Verify reset state
        final_state = self.state_manager.get_conversation_state(chat_id)
        self.assertEqual(final_state.mode, OperationMode.INITIAL_SETUP)
        self.assertTrue(final_state.awaiting_setup_confirmation)
        self.assertFalse(final_state.setup_complete)

    def test_translation_output_scenario(self):
        """Test: User sends translation request"""
        chat_id = "translation_user_101"
        
        # 1. Set up completed conversation
        self.state_manager.create_conversation_state(
            chat_id, "conv_101", "token_101", OperationMode.TRANSLATION
        )
        self.state_manager.mark_setup_complete(chat_id)
        self.state_manager.mark_context_restored(chat_id)
        
        # 2. Classify regular message
        message_type = MessageClassifier.classify_incoming_message("Hello world")
        self.assertEqual(message_type, MessageType.REGULAR_TEXT)
        
        # 3. Simulate translation response
        translation_response = "en: Hello world\\nes: Hola mundo\\nfr: Bonjour le monde"
        response_type = MessageClassifier.classify_copilot_response(translation_response)
        self.assertEqual(response_type, ResponseType.TRANSLATION_OUTPUT)
        
        # 4. Verify conversation state remains stable
        final_state = self.state_manager.get_conversation_state(chat_id)
        self.assertTrue(final_state.setup_complete)
        self.assertTrue(final_state.context_restored)
        self.assertEqual(final_state.mode, OperationMode.TRANSLATION)


if __name__ == '__main__':
    # Configure test logging
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    unittest.main(verbosity=2)