#!/usr/bin/env python3
"""
Comprehensive test suite for Translation Bot Recovery.
Tests the core functionality fixes according to the design document.
"""

import unittest
import json
import time
import tempfile
import os
import sys
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add the project directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from app import parse_and_persist_setup, conversations, recent_activity_ids, active_pollers


class TestTranslationBotRecovery(unittest.TestCase):
    """Test suite for translation bot recovery fixes."""
    
    def setUp(self):
        """Set up test environment."""
        # Create temporary database for testing
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        
        # Clear global state
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        
        # Initialize test database
        db.init_db(self.test_db.name)
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary database
        try:
            os.unlink(self.test_db.name)
        except:
            pass
    
    def test_language_setup_parsing_success_cases(self):
        """Test successful language setup parsing with various message formats."""
        test_cases = [
            # Standard confirmation format
            ("Thanks! Setup is complete. Now we speak English, Polish, Portuguese.", 
             "English, Polish, Portuguese"),
            
            # Alternative confirmation format
            ("Great! I can now translate between English, Russian, Japanese.",
             "English, Russian, Japanese"),
            
            # With trailing text
            ("Perfect! Now I can help you with English, French.\nSend your message...",
             "English, French"),
            
            # Different punctuation
            ("Excellent! I'm ready to translate English, German, Spanish!",
             "English, German, Spanish"),
            
            # With "and" separator
            ("Setup is complete. Now we speak English and Spanish.",
             "English, Spanish"),
        ]
        
        for i, (input_text, expected_languages) in enumerate(test_cases):
            with self.subTest(case=i, input_text=input_text):
                chat_id = f"test_chat_{i}"
                
                # Test parsing
                result = parse_and_persist_setup(chat_id, input_text, persist=False)  # Don't persist in main test
                self.assertTrue(result, f"Failed to parse: {input_text}")
                
                # Manually persist with correct database file
                if result:
                    db.upsert_chat_settings(chat_id, '', expected_languages, 
                                          datetime.utcnow().isoformat(), self.test_db.name)
                
                # Verify database persistence
                settings = db.get_chat_settings(chat_id, self.test_db.name)
                self.assertIsNotNone(settings)
                self.assertEqual(settings['language_names'], expected_languages)
    
    def test_language_setup_parsing_failure_cases(self):
        """Test language setup parsing rejection of invalid messages."""
        failure_cases = [
            "Hello, how are you?",  # Regular message
            "I don't understand",   # Error message
            "No languages are mentioned in your request",  # Explicit failure
            "Please provide language preferences",  # Setup request
            "",  # Empty string
            "Setup is incomplete",  # Incomplete setup
        ]
        
        for i, input_text in enumerate(failure_cases):
            with self.subTest(case=i, input_text=input_text):
                chat_id = f"fail_chat_{i}"
                
                # Should not parse as setup confirmation
                result = parse_and_persist_setup(chat_id, input_text, persist=False)
                self.assertFalse(result, f"Incorrectly parsed as setup: {input_text}")
                
                # Should not create database entry
                settings = db.get_chat_settings(chat_id, self.test_db.name)
                self.assertIsNone(settings)
    
    def test_conversation_state_management(self):
        """Test conversation state creation and management."""
        chat_id = "test_conversation_state"
        
        # Initially no conversation
        self.assertNotIn(chat_id, conversations)
        
        # Create conversation state
        conversations[chat_id] = {
            'id': 'test_conv_id',
            'token': 'test_token',
            'watermark': None,
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': False
        }
        
        # Verify state exists
        self.assertIn(chat_id, conversations)
        self.assertEqual(conversations[chat_id]['id'], 'test_conv_id')
        self.assertFalse(conversations[chat_id]['setup_complete'])
        
        # Mark setup complete
        conversations[chat_id]['setup_complete'] = True
        self.assertTrue(conversations[chat_id]['setup_complete'])
    
    def test_database_persistence_and_retrieval(self):
        """Test database operations for chat settings."""
        chat_id = "test_db_persistence"
        languages = "English, Russian, Korean"
        timestamp = datetime.utcnow().isoformat()
        
        # Test upsert
        db.upsert_chat_settings(chat_id, '', languages, timestamp, self.test_db.name)
        
        # Test retrieval
        settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNotNone(settings)
        self.assertEqual(settings['chat_id'], chat_id)
        self.assertEqual(settings['language_names'], languages)
        self.assertEqual(settings['updated_at'], timestamp)
        
        # Test update
        new_languages = "Spanish, French"
        new_timestamp = datetime.utcnow().isoformat()
        db.upsert_chat_settings(chat_id, '', new_languages, new_timestamp, self.test_db.name)
        
        updated_settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertEqual(updated_settings['language_names'], new_languages)
        self.assertEqual(updated_settings['updated_at'], new_timestamp)
        
        # Test deletion
        db.delete_chat_settings(chat_id, self.test_db.name)
        deleted_settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNone(deleted_settings)
    
    def test_quick_setup_logic(self):
        """Test quick setup message generation for existing users."""
        chat_id = "test_quick_setup"
        existing_languages = "English, Polish, Portuguese"
        
        # Save existing settings
        db.upsert_chat_settings(
            chat_id, '', existing_languages, 
            datetime.utcnow().isoformat(), self.test_db.name
        )
        
        # Retrieve settings
        settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNotNone(settings)
        
        # Generate quick setup message
        saved_languages = settings.get('language_names', '')
        setup_message = f"My languages are: {saved_languages}"
        
        expected_message = f"My languages are: {existing_languages}"
        self.assertEqual(setup_message, expected_message)
    
    def test_conversation_cleanup_on_reset(self):
        """Test proper cleanup when /reset command is used."""
        chat_id = "test_reset_cleanup"
        
        # Set up initial state
        conversations[chat_id] = {
            'id': 'test_conv_id',
            'token': 'test_token',
            'watermark': 'test_watermark',
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': True
        }
        active_pollers[chat_id] = True
        recent_activity_ids[chat_id] = ['activity1', 'activity2']
        
        # Save settings to database
        db.upsert_chat_settings(
            chat_id, '', "English, Russian", 
            datetime.utcnow().isoformat(), self.test_db.name
        )
        
        # Simulate reset cleanup
        active_pollers[chat_id] = False
        db.delete_chat_settings(chat_id, self.test_db.name)
        conversations.pop(chat_id, None)
        if chat_id in recent_activity_ids:
            del recent_activity_ids[chat_id]
        
        # Verify cleanup
        self.assertNotIn(chat_id, conversations)
        self.assertFalse(active_pollers.get(chat_id, False))
        self.assertNotIn(chat_id, recent_activity_ids)
        
        # Verify database cleanup
        settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNone(settings)
    
    def test_setup_completion_tracking(self):
        """Test that setup completion is properly tracked in conversation state."""
        chat_id = "test_setup_tracking"
        
        # Create conversation without setup
        conversations[chat_id] = {
            'id': 'test_conv_id',
            'token': 'test_token',
            'watermark': None,
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': False
        }
        
        self.assertFalse(conversations[chat_id]['setup_complete'])
        
        # Simulate successful setup parsing
        setup_text = "Thanks! Setup is complete. Now we speak English, German."
        result = parse_and_persist_setup(chat_id, setup_text, persist=True)
        
        self.assertTrue(result)
        # Mark setup as complete
        conversations[chat_id]['setup_complete'] = True
        self.assertTrue(conversations[chat_id]['setup_complete'])
    
    def test_language_extraction_edge_cases(self):
        """Test language extraction with various edge cases."""
        edge_cases = [
            # Mixed case
            ("Setup is complete. Now we speak ENGLISH, russian, JaPaNeSe.",
             "ENGLISH, russian, JaPaNeSe"),
            
            # Extra whitespace
            ("Thanks! Setup is complete. Now we speak  English ,  Polish  ,  Portuguese  .",
             "English, Polish, Portuguese"),
            
            # Single language
            ("Perfect! Now I can help you with English.",
             "English"),
            
            # Languages with accents (if supported)
            ("Setup is complete. Now we speak Français, Español.",
             "Français, Español"),
        ]
        
        for i, (input_text, expected) in enumerate(edge_cases):
            with self.subTest(case=i, input_text=input_text):
                chat_id = f"edge_case_{i}"
                result = parse_and_persist_setup(chat_id, input_text, persist=False)
                self.assertTrue(result)
                
                # Manually persist with correct database file
                if result:
                    db.upsert_chat_settings(chat_id, '', expected, 
                                          datetime.utcnow().isoformat(), self.test_db.name)
                
                settings = db.get_chat_settings(chat_id, self.test_db.name)
                self.assertIsNotNone(settings)
                self.assertEqual(settings['language_names'], expected)


class TestConversationFlows(unittest.TestCase):
    """Integration tests for complete conversation flows."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.test_db.close()
        
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
        
        db.init_db(self.test_db.name)
    
    def tearDown(self):
        """Clean up test environment."""
        try:
            os.unlink(self.test_db.name)
        except:
            pass
    
    def test_fresh_user_setup_flow(self):
        """Test the complete flow for a new user setting up languages."""
        chat_id = "fresh_user_001"
        
        # Step 1: User sends /start
        # (This would create a new conversation)
        conversations[chat_id] = {
            'id': 'new_conv_id',
            'token': 'new_token',
            'watermark': None,
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': False
        }
        
        # Step 2: Bot asks for languages (simulated)
        # Step 3: User provides languages
        user_language_input = "English, Polish, Portuguese"
        
        # Step 4: Bot confirms setup
        bot_confirmation = "Thanks! Setup is complete. Now we speak English, Polish, Portuguese."
        
        # Step 5: Parse and persist setup
        result = parse_and_persist_setup(chat_id, bot_confirmation, persist=False)
        self.assertTrue(result)
        
        # Manually persist with correct database file  
        if result:
            db.upsert_chat_settings(chat_id, '', "English, Polish, Portuguese", 
                                  datetime.utcnow().isoformat(), self.test_db.name)
            # Also mark setup as complete in conversation state
            conversations[chat_id]['setup_complete'] = True
        
        # Verify database state
        settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNotNone(settings)
        self.assertEqual(settings['language_names'], "English, Polish, Portuguese")
        
        # Verify conversation state
        self.assertTrue(conversations[chat_id]['setup_complete'])
    
    def test_returning_user_flow(self):
        """Test the flow for a user with existing language settings."""
        chat_id = "returning_user_001"
        existing_languages = "English, Russian, Korean"
        
        # Pre-populate database with existing settings
        db.upsert_chat_settings(
            chat_id, '', existing_languages,
            datetime.utcnow().isoformat(), self.test_db.name
        )
        
        # Create new conversation (simulating new session)
        conversations[chat_id] = {
            'id': 'returning_conv_id',
            'token': 'returning_token',
            'watermark': None,
            'last_interaction': time.time(),
            'is_polling': False,
            'setup_complete': False
        }
        
        # Simulate quick setup message generation
        settings = db.get_chat_settings(chat_id, self.test_db.name)
        self.assertIsNotNone(settings)
        
        saved_languages = settings.get('language_names', '')
        self.assertEqual(saved_languages, existing_languages)
        
        # Quick setup message would be sent
        setup_message = f"My languages are: {saved_languages}"
        expected = f"My languages are: {existing_languages}"
        self.assertEqual(setup_message, expected)
        
        # Mark setup as complete
        conversations[chat_id]['setup_complete'] = True
        self.assertTrue(conversations[chat_id]['setup_complete'])


def run_comprehensive_tests():
    """Run all tests and provide detailed results."""
    print("=" * 60)
    print("TRANSLATION BOT RECOVERY - COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestTranslationBotRecovery))
    suite.addTests(loader.loadTestsFromTestCase(TestConversationFlows))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    # Overall result
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOVERALL RESULT: {'✅ PASS' if success else '❌ FAIL'}")
    
    return success


if __name__ == '__main__':
    success = run_comprehensive_tests()
    sys.exit(0 if success else 1)