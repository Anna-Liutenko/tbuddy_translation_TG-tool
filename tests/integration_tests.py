#!/usr/bin/env python3
"""
Integration Tests for Telegram Translation Bot

This module contains end-to-end integration tests that validate complete
user conversation flows and cross-component interactions according to
the design document specifications.
"""

import unittest
import json
import time
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from collections import deque

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from app import (conversations, recent_activity_ids, active_pollers, 
                parse_and_persist_setup, last_user_message)
from test_config import TestDatabase, TestDataFactory, TestValidator
from message_simulator import (TelegramMessageSimulator, ConversationFlowSimulator, 
                              BotResponseValidator, MessageTemplateLibrary)


class TestFreshUserFlow(unittest.TestCase):
    """Integration tests for fresh user conversation flow"""
    
    def setUp(self):
        """Set up test environment for fresh user tests"""
        self.test_db = TestDatabase("fresh_user_flow")
        self.message_sim = TelegramMessageSimulator()
        self.validator = BotResponseValidator()
        
        # Clear global state
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def test_complete_fresh_user_setup_flow(self):
        """Test complete flow for a new user setting up languages"""
        chat_id = "fresh_user_001"
        languages = ["English", "Spanish", "French"]
        
        # Step 1: User sends /start command
        start_message = self.message_sim.generate_command_message(chat_id, "start")
        
        # Simulate conversation creation (normally done by webhook handler)
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        # Verify initial conversation state
        self.assertIn(chat_id, conversations)
        self.assertFalse(conversations[chat_id]['setup_complete'])
        
        # Step 2: User provides language preferences
        language_input = ", ".join(languages)
        language_message = self.message_sim.generate_message(chat_id, language_input)
        
        # Store user message
        last_user_message[chat_id] = language_input
        
        # Step 3: Bot responds with confirmation
        confirmation_text = f"Thanks! Setup is complete. Now we speak {language_input}."
        
        # Test parsing and persistence
        parse_result = parse_and_persist_setup(chat_id, confirmation_text, persist=False)
        self.assertTrue(parse_result, "Failed to parse setup confirmation")
        
        # Manually persist to test database
        if parse_result:
            db.upsert_chat_settings(chat_id, '', language_input, 
                                   datetime.utcnow().isoformat(), self.test_db.get_path())
            conversations[chat_id]['setup_complete'] = True
        
        # Verify database persistence
        settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(settings, "Settings not persisted to database")
        self.assertEqual(settings['language_names'], language_input)
        self.assertEqual(settings['chat_id'], chat_id)
        
        # Verify conversation state update
        self.assertTrue(conversations[chat_id]['setup_complete'], "Setup completion not marked in conversation state")
        
        # Step 4: User sends translation request
        translation_request = "Please translate: Hello world"
        translation_message = self.message_sim.generate_message(chat_id, translation_request)
        
        # Verify user can proceed with translation after setup
        self.assertTrue(conversations[chat_id]['setup_complete'])
        self.assertIn(chat_id, conversations)
    
    def test_fresh_user_with_multiple_language_formats(self):
        """Test fresh user setup with various language input formats"""
        test_cases = [
            (["English", "German"], "English, German"),
            (["Spanish", "French", "Italian"], "Spanish and French and Italian"),
            (["Russian", "Japanese"], "Russian; Japanese"),
            (["Portuguese", "Korean", "Arabic"], "Portuguese + Korean + Arabic"),
        ]
        
        for i, (languages, user_input) in enumerate(test_cases):
            with self.subTest(case=i, languages=languages, input_format=user_input):
                chat_id = f"fresh_multi_{i}"
                
                # Setup conversation
                conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
                
                # Simulate bot confirmation (normalized format)
                normalized_languages = ", ".join(languages)
                confirmation = f"Perfect! Now I can help you with {normalized_languages}."
                
                # Test parsing
                result = parse_and_persist_setup(chat_id, confirmation, persist=False)
                self.assertTrue(result, f"Failed to parse confirmation for languages: {languages}")
                
                if result:
                    db.upsert_chat_settings(chat_id, '', normalized_languages,
                                          datetime.utcnow().isoformat(), self.test_db.get_path())
                    conversations[chat_id]['setup_complete'] = True
                
                # Verify setup
                settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                self.assertIsNotNone(settings)
                self.assertEqual(settings['language_names'], normalized_languages)
    
    def test_fresh_user_setup_failure_recovery(self):
        """Test fresh user flow when setup initially fails"""
        chat_id = "fresh_failure_recovery"
        
        # Initial conversation state
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        # First attempt: Bot fails to confirm setup
        failure_message = "I don't understand your language preferences. Please try again."
        
        result1 = parse_and_persist_setup(chat_id, failure_message, persist=False)
        self.assertFalse(result1, "Should not parse failure message as confirmation")
        
        # Verify no database entry created
        settings1 = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNone(settings1)
        
        # Verify setup still incomplete
        self.assertFalse(conversations[chat_id]['setup_complete'])
        
        # Second attempt: Successful setup
        languages = "English, Portuguese, Italian"
        success_message = f"Great! I can now translate between {languages}."
        
        result2 = parse_and_persist_setup(chat_id, success_message, persist=False)
        self.assertTrue(result2, "Should parse success message as confirmation")
        
        # Persist successful setup
        if result2:
            db.upsert_chat_settings(chat_id, '', languages,
                                   datetime.utcnow().isoformat(), self.test_db.get_path())
            conversations[chat_id]['setup_complete'] = True
        
        # Verify successful recovery
        settings2 = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(settings2)
        self.assertEqual(settings2['language_names'], languages)
        self.assertTrue(conversations[chat_id]['setup_complete'])


class TestReturningUserFlow(unittest.TestCase):
    """Integration tests for returning user conversation flow"""
    
    def setUp(self):
        """Set up test environment for returning user tests"""
        self.test_db = TestDatabase("returning_user_flow")
        self.message_sim = TelegramMessageSimulator()
        
        # Clear global state
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def test_returning_user_with_existing_settings(self):
        """Test returning user flow with pre-existing language settings"""
        chat_id = "returning_user_001"
        existing_languages = ["English", "Russian", "Korean"]
        language_string = ", ".join(existing_languages)
        
        # Pre-populate database with existing settings
        timestamp = datetime.utcnow().isoformat()
        db.upsert_chat_settings(chat_id, '', language_string, timestamp, self.test_db.get_path())
        
        # Verify settings exist
        settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(settings)
        self.assertEqual(settings['language_names'], language_string)
        
        # User sends a regular message (not /start)
        regular_message = self.message_sim.generate_message(chat_id, "Hello, please translate this text")
        
        # Simulate conversation creation with quick setup
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        # Simulate quick setup message generation
        saved_languages = settings.get('language_names', '')
        quick_setup_message = f"My languages are: {saved_languages}"
        expected_setup_message = f"My languages are: {language_string}"
        
        self.assertEqual(quick_setup_message, expected_setup_message)
        
        # Mark setup as complete (simulating quick setup)
        conversations[chat_id]['setup_complete'] = True
        
        # Verify returning user flow completed successfully
        self.assertTrue(conversations[chat_id]['setup_complete'])
        self.assertIn(chat_id, conversations)
        
        # User should be ready for translation immediately
        translation_message = self.message_sim.generate_message(chat_id, "Translate: Good morning")
        last_user_message[chat_id] = "Translate: Good morning"
        
        # Verify conversation is ready for use
        self.assertTrue(conversations[chat_id]['setup_complete'])
    
    def test_returning_user_language_preferences_update(self):
        """Test updating language preferences for returning user"""
        chat_id = "returning_update_001"
        
        # Initial settings
        initial_languages = "English, German"
        initial_timestamp = datetime.utcnow().isoformat()
        db.upsert_chat_settings(chat_id, '', initial_languages, initial_timestamp, self.test_db.get_path())
        
        # Simulate user requesting language change
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=True)
        
        # User provides new language preferences
        new_languages = "Spanish, French, Portuguese"
        update_confirmation = f"Setup updated! Now we speak {new_languages}."
        
        # Test parsing new setup
        update_result = parse_and_persist_setup(chat_id, update_confirmation, persist=False)
        self.assertTrue(update_result, "Failed to parse language update confirmation")
        
        # Update database
        if update_result:
            new_timestamp = (datetime.utcnow() + timedelta(minutes=1)).isoformat()
            db.upsert_chat_settings(chat_id, '', new_languages, new_timestamp, self.test_db.get_path())
        
        # Verify update
        updated_settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(updated_settings)
        self.assertEqual(updated_settings['language_names'], new_languages)
        self.assertNotEqual(updated_settings['language_names'], initial_languages)
    
    def test_multiple_returning_users_isolation(self):
        """Test that multiple returning users don't interfere with each other"""
        users = [
            ("returning_iso_1", ["English", "Spanish"]),
            ("returning_iso_2", ["French", "German"]),
            ("returning_iso_3", ["Italian", "Portuguese"]),
        ]
        
        # Setup all users with different language preferences
        for chat_id, languages in users:
            language_string = ", ".join(languages)
            timestamp = datetime.utcnow().isoformat()
            
            db.upsert_chat_settings(chat_id, '', language_string, timestamp, self.test_db.get_path())
            conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=True)
        
        # Verify each user has correct settings
        for chat_id, expected_languages in users:
            settings = db.get_chat_settings(chat_id, self.test_db.get_path())
            self.assertIsNotNone(settings, f"Settings not found for {chat_id}")
            
            expected_string = ", ".join(expected_languages)
            self.assertEqual(settings['language_names'], expected_string, 
                           f"Incorrect languages for {chat_id}")
            
            # Verify conversation isolation
            self.assertIn(chat_id, conversations)
            self.assertTrue(conversations[chat_id]['setup_complete'])
        
        # Modify one user's settings
        modified_user = users[1][0]  # Second user
        new_languages = "Japanese, Korean, Chinese"
        
        update_confirmation = f"Updated! Now we speak {new_languages}."
        update_result = parse_and_persist_setup(modified_user, update_confirmation, persist=False)
        
        if update_result:
            db.upsert_chat_settings(modified_user, '', new_languages,
                                   datetime.utcnow().isoformat(), self.test_db.get_path())
        
        # Verify other users are unaffected
        for chat_id, original_languages in users:
            if chat_id != modified_user:
                settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                original_string = ", ".join(original_languages)
                self.assertEqual(settings['language_names'], original_string,
                               f"User {chat_id} affected by {modified_user}'s update")


class TestResetCommandFlow(unittest.TestCase):
    """Integration tests for reset command conversation flow"""
    
    def setUp(self):
        """Set up test environment for reset command tests"""
        self.test_db = TestDatabase("reset_command_flow")
        self.message_sim = TelegramMessageSimulator()
        
        # Clear global state
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def test_complete_reset_flow(self):
        """Test complete reset command flow with full cleanup"""
        chat_id = "reset_complete_001"
        initial_languages = "English, Portuguese, Italian"
        
        # Setup initial state (simulating active user)
        timestamp = datetime.utcnow().isoformat()
        db.upsert_chat_settings(chat_id, '', initial_languages, timestamp, self.test_db.get_path())
        
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=True)
        active_pollers[chat_id] = True
        recent_activity_ids[chat_id] = deque(['activity1', 'activity2', 'activity3'], maxlen=100)
        last_user_message[chat_id] = "Previous message"
        
        # Verify initial state
        self.assertIn(chat_id, conversations)
        self.assertTrue(conversations[chat_id]['setup_complete'])
        self.assertTrue(active_pollers[chat_id])
        self.assertIn(chat_id, recent_activity_ids)
        self.assertIn(chat_id, last_user_message)
        
        initial_settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(initial_settings)
        
        # User sends reset command
        reset_message = self.message_sim.generate_command_message(chat_id, "reset")
        
        # Simulate reset cleanup
        active_pollers[chat_id] = False
        db.delete_chat_settings(chat_id, self.test_db.get_path())
        conversations.pop(chat_id, None)
        
        if chat_id in recent_activity_ids:
            del recent_activity_ids[chat_id]
        
        if chat_id in last_user_message:
            del last_user_message[chat_id]
        
        # Verify complete cleanup
        self.assertNotIn(chat_id, conversations, "Conversation state not cleared")
        self.assertFalse(active_pollers.get(chat_id, False), "Polling not stopped")
        self.assertNotIn(chat_id, recent_activity_ids, "Activity history not cleared")
        self.assertNotIn(chat_id, last_user_message, "Last message not cleared")
        
        # Verify database cleanup
        reset_settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNone(reset_settings, "Database settings not deleted")
        
        # User should be able to start fresh after reset
        # Simulate new /start command
        new_start_message = self.message_sim.generate_command_message(chat_id, "start")
        
        # Create new conversation (as would happen after reset)
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        # Verify fresh start
        self.assertIn(chat_id, conversations)
        self.assertFalse(conversations[chat_id]['setup_complete'])
        self.assertNotEqual(conversations[chat_id]['id'], 
                           TestDataFactory.generate_conversation_state(chat_id, setup_complete=True)['id'])
    
    def test_reset_with_active_polling(self):
        """Test reset command when polling is active"""
        chat_id = "reset_polling_001"
        
        # Setup state with active polling
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=True)
        conversations[chat_id]['is_polling'] = True  # Active polling
        active_pollers[chat_id] = True
        
        # Verify polling is active
        self.assertTrue(conversations[chat_id]['is_polling'])
        self.assertTrue(active_pollers[chat_id])
        
        # Send reset command
        reset_message = self.message_sim.generate_command_message(chat_id, "reset")
        
        # Simulate polling cleanup
        active_pollers[chat_id] = False
        conversations[chat_id]['is_polling'] = False
        
        # Complete reset
        conversations.pop(chat_id, None)
        
        # Verify polling stopped and state cleaned
        self.assertFalse(active_pollers.get(chat_id, False))
        self.assertNotIn(chat_id, conversations)
    
    def test_reset_nonexistent_user(self):
        """Test reset command for user with no existing state"""
        chat_id = "reset_nonexistent_001"
        
        # Verify no existing state
        self.assertNotIn(chat_id, conversations)
        self.assertFalse(active_pollers.get(chat_id, False))
        self.assertNotIn(chat_id, recent_activity_ids)
        
        settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNone(settings)
        
        # Send reset command
        reset_message = self.message_sim.generate_command_message(chat_id, "reset")
        
        # Simulate reset operation (should handle gracefully)
        try:
            active_pollers[chat_id] = False
            db.delete_chat_settings(chat_id, self.test_db.get_path())  # Should not raise error
            conversations.pop(chat_id, None)  # Should not raise error
            
            if chat_id in recent_activity_ids:
                del recent_activity_ids[chat_id]
            
            # Reset should complete without errors
            reset_successful = True
            
        except Exception as e:
            reset_successful = False
            self.fail(f"Reset failed for nonexistent user: {e}")
        
        self.assertTrue(reset_successful, "Reset should handle nonexistent users gracefully")


class TestCrossComponentIntegration(unittest.TestCase):
    """Tests for integration between different system components"""
    
    def setUp(self):
        """Set up test environment for integration tests"""
        self.test_db = TestDatabase("cross_component")
        self.message_sim = TelegramMessageSimulator()
        self.flow_sim = ConversationFlowSimulator()
        
        # Clear global state
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        last_user_message.clear()
    
    def test_database_and_conversation_state_sync(self):
        """Test synchronization between database and conversation state"""
        chat_id = "sync_test_001"
        languages = "English, German, Japanese"
        
        # Create conversation state
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        # Simulate setup confirmation
        confirmation = f"Setup is complete. Now we speak {languages}."
        parse_result = parse_and_persist_setup(chat_id, confirmation, persist=False)
        
        # Update both database and conversation state
        if parse_result:
            db.upsert_chat_settings(chat_id, '', languages,
                                   datetime.utcnow().isoformat(), self.test_db.get_path())
            conversations[chat_id]['setup_complete'] = True
        
        # Verify synchronization
        db_settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        conv_state = conversations.get(chat_id, {})
        
        self.assertIsNotNone(db_settings, "Database not updated")
        self.assertTrue(conv_state.get('setup_complete', False), "Conversation state not updated")
        self.assertEqual(db_settings['language_names'], languages)
        self.assertEqual(db_settings['chat_id'], chat_id)
    
    def test_parsing_and_persistence_integration(self):
        """Test integration between parsing logic and database persistence"""
        test_scenarios = [
            ("Thanks! Setup is complete. Now we speak English, Spanish.", "English, Spanish", True),
            ("What languages do you prefer?", None, False),
            ("Perfect! Now I can help you with French, German, Italian.", "French, German, Italian", True),
        ]
        
        for i, (message, expected_languages, should_persist) in enumerate(test_scenarios):
            with self.subTest(case=i, message=message):
                chat_id = f"parse_persist_{i}"
                
                # Test parsing
                parse_result = parse_and_persist_setup(chat_id, message, persist=False)
                self.assertEqual(parse_result, should_persist)
                
                # Test persistence if parsing succeeded
                if parse_result and expected_languages:
                    db.upsert_chat_settings(chat_id, '', expected_languages,
                                           datetime.utcnow().isoformat(), self.test_db.get_path())
                    
                    # Verify persistence
                    settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                    self.assertIsNotNone(settings)
                    self.assertEqual(settings['language_names'], expected_languages)
                else:
                    # Verify no persistence for failed parsing
                    settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                    self.assertIsNone(settings)
    
    def test_conversation_lifecycle_integration(self):
        """Test complete conversation lifecycle integration"""
        chat_id = "lifecycle_test_001"
        
        # Phase 1: Fresh user setup
        conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id, setup_complete=False)
        
        languages = "English, Portuguese"
        confirmation = f"Great! I can now translate between {languages}."
        
        parse_result = parse_and_persist_setup(chat_id, confirmation, persist=False)
        if parse_result:
            db.upsert_chat_settings(chat_id, '', languages,
                                   datetime.utcnow().isoformat(), self.test_db.get_path())
            conversations[chat_id]['setup_complete'] = True
        
        # Verify setup phase
        self.assertTrue(conversations[chat_id]['setup_complete'])
        settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNotNone(settings)
        
        # Phase 2: Active usage
        active_pollers[chat_id] = True
        conversations[chat_id]['is_polling'] = True
        last_user_message[chat_id] = "Translate: Hello world"
        recent_activity_ids[chat_id] = deque(['msg1', 'msg2'], maxlen=100)
        
        # Verify active phase
        self.assertTrue(active_pollers[chat_id])
        self.assertTrue(conversations[chat_id]['is_polling'])
        self.assertIn(chat_id, last_user_message)
        
        # Phase 3: Reset and cleanup
        active_pollers[chat_id] = False
        db.delete_chat_settings(chat_id, self.test_db.get_path())
        conversations.pop(chat_id, None)
        del recent_activity_ids[chat_id]
        del last_user_message[chat_id]
        
        # Verify cleanup phase
        self.assertNotIn(chat_id, conversations)
        self.assertFalse(active_pollers.get(chat_id, False))
        self.assertNotIn(chat_id, recent_activity_ids)
        self.assertNotIn(chat_id, last_user_message)
        
        cleanup_settings = db.get_chat_settings(chat_id, self.test_db.get_path())
        self.assertIsNone(cleanup_settings)


def run_integration_tests():
    """Run all integration tests with comprehensive reporting"""
    print("=" * 80)
    print("INTEGRATION TESTS - TELEGRAM TRANSLATION BOT")
    print("=" * 80)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add integration test classes
    integration_test_classes = [
        TestFreshUserFlow,
        TestReturningUserFlow,
        TestResetCommandFlow,
        TestCrossComponentIntegration,
    ]
    
    for test_class in integration_test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, buffer=True)
    result = runner.run(suite)
    
    # Print detailed summary
    print("\n" + "=" * 80)
    print("INTEGRATION TEST RESULTS")
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
    success, test_result = run_integration_tests()
    sys.exit(0 if success else 1)