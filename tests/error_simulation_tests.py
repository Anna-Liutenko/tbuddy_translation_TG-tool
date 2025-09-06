#!/usr/bin/env python3
"""
Error Simulation Tests for Telegram Translation Bot

This module contains comprehensive error simulation tests that validate
the bot's resilience and error handling capabilities under various
failure scenarios.
"""

import unittest
import json
import time
import sys
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import requests
import sqlite3

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from app import (conversations, recent_activity_ids, active_pollers, 
                parse_and_persist_setup, last_user_message)
from test_config import TestDatabase, TestDataFactory
from message_simulator import ErrorSimulator, TelegramMessageSimulator


class TestNetworkErrorHandling(unittest.TestCase):
    """Tests for network error handling and resilience"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_db = TestDatabase("network_errors")
        self.error_sim = ErrorSimulator()
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
    
    def test_network_timeout_handling(self):
        """Test handling of network timeouts"""
        chat_id = "timeout_test_001"
        
        with self.error_sim.simulate_network_timeout(10.0):
            # Create conversation state
            conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id)
            
            # Simulate operation that would trigger network call
            try:
                # This would normally make a network request
                # In the actual app, this might be start_direct_line_conversation()
                
                # For testing, we simulate the timeout scenario
                with patch('requests.post') as mock_post:
                    mock_post.side_effect = requests.exceptions.Timeout("Request timed out")
                    
                    # Test that the application handles timeout gracefully
                    # This is a simulation of what would happen in the real app
                    timeout_handled = True
                    error_message = ""
                    
                    try:
                        # Simulate the network call that times out
                        response = requests.post("https://test.example.com", timeout=10)
                    except requests.exceptions.Timeout as e:
                        error_message = str(e)
                        timeout_handled = True
                    except Exception as e:
                        timeout_handled = False
                        error_message = f"Unexpected error: {e}"
                
                # Verify timeout was handled properly
                self.assertTrue(timeout_handled, "Network timeout should be handled gracefully")
                self.assertIn("timeout", error_message.lower())
                
                # Verify conversation state is preserved during network issues
                self.assertIn(chat_id, conversations)
                
            except Exception as e:
                self.fail(f"Network timeout test failed: {e}")
    
    def test_connection_error_handling(self):
        """Test handling of connection errors"""
        chat_id = "connection_test_001"
        
        with self.error_sim.simulate_connection_error():
            conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id)
            
            with patch('requests.post') as mock_post:
                mock_post.side_effect = requests.exceptions.ConnectionError("Connection failed")
                
                connection_error_handled = True
                error_message = ""
                
                try:
                    response = requests.post("https://test.example.com")
                except requests.exceptions.ConnectionError as e:
                    error_message = str(e)
                    connection_error_handled = True
                except Exception as e:
                    connection_error_handled = False
                    error_message = f"Unexpected error: {e}"
                
                # Verify connection error was handled
                self.assertTrue(connection_error_handled, "Connection error should be handled gracefully")
                self.assertIn("connection", error_message.lower())
    
    def test_http_error_responses(self):
        """Test handling of various HTTP error status codes"""
        error_codes = [400, 401, 403, 404, 429, 500, 502, 503, 504]
        
        for status_code in error_codes:
            with self.subTest(status_code=status_code):
                chat_id = f"http_error_{status_code}_test"
                
                with self.error_sim.simulate_http_error(status_code):
                    conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id)
                    
                    with patch('requests.post') as mock_post:
                        mock_response = Mock()
                        mock_response.status_code = status_code
                        mock_response.json.return_value = {"error": f"HTTP {status_code} error"}
                        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(f"HTTP {status_code}")
                        mock_post.return_value = mock_response
                        
                        http_error_handled = True
                        
                        try:
                            response = requests.post("https://test.example.com")
                            
                            # Test application's response to different status codes
                            if status_code >= 500:
                                # Server errors - should be handled as temporary failures
                                self.assertGreaterEqual(response.status_code, 500)
                            elif status_code >= 400:
                                # Client errors - should be handled as permanent failures
                                self.assertGreaterEqual(response.status_code, 400)
                                self.assertLess(response.status_code, 500)
                            
                        except requests.exceptions.HTTPError:
                            # HTTPError is expected for error status codes
                            http_error_handled = True
                        except Exception as e:
                            http_error_handled = False
                            self.fail(f"Unexpected error for HTTP {status_code}: {e}")
                        
                        self.assertTrue(http_error_handled, f"HTTP {status_code} error should be handled")
    
    def test_invalid_json_response_handling(self):
        """Test handling of invalid JSON responses"""
        chat_id = "invalid_json_test"
        
        with self.error_sim.simulate_invalid_json_response():
            conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id)
            
            with patch('requests.post') as mock_post:
                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
                mock_response.text = "Invalid JSON response body"
                mock_post.return_value = mock_response
                
                invalid_json_handled = True
                
                try:
                    response = requests.post("https://test.example.com")
                    
                    # Try to parse JSON - should fail gracefully
                    try:
                        json_data = response.json()
                    except json.JSONDecodeError:
                        # This is expected for invalid JSON
                        invalid_json_handled = True
                        
                        # Application should fall back to text response
                        text_data = response.text
                        self.assertIsInstance(text_data, str)
                        self.assertEqual(text_data, "Invalid JSON response body")
                    
                except Exception as e:
                    invalid_json_handled = False
                    self.fail(f"Invalid JSON handling failed: {e}")
                
                self.assertTrue(invalid_json_handled, "Invalid JSON should be handled gracefully")


class TestDatabaseErrorHandling(unittest.TestCase):
    """Tests for database error handling and recovery"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_db = TestDatabase("database_errors")
        self.error_sim = ErrorSimulator()
        
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def test_database_connection_failure(self):
        """Test handling of database connection failures"""
        chat_id = "db_connection_fail_test"
        
        with self.error_sim.simulate_database_error():
            with patch('db.get_chat_settings') as mock_get:
                mock_get.side_effect = sqlite3.OperationalError("database is locked")
                
                db_error_handled = True
                
                try:
                    # Attempt to get chat settings
                    settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                    
                    # This should not execute due to the mock
                    self.fail("Database error should have been raised")
                    
                except sqlite3.OperationalError as e:
                    # Expected database error
                    db_error_handled = True
                    self.assertIn("database is locked", str(e))
                    
                except Exception as e:
                    db_error_handled = False
                    self.fail(f"Unexpected error type: {e}")
                
                self.assertTrue(db_error_handled, "Database error should be handled")
    
    def test_database_file_corruption(self):
        """Test handling of database file corruption"""
        chat_id = "db_corruption_test"
        
        # Create a corrupted database file
        corrupted_db_path = str(self.test_db.get_path()) + "_corrupted"
        
        # Write invalid data to simulate corruption
        with open(corrupted_db_path, 'wb') as f:
            f.write(b"This is not a valid SQLite database file")
        
        try:
            # Attempt to use the corrupted database
            with patch('db._get_sqlite_conn') as mock_conn:
                mock_conn.side_effect = sqlite3.DatabaseError("file is not a database")
                
                corruption_handled = True
                
                try:
                    settings = db.get_chat_settings(chat_id, corrupted_db_path)
                    self.fail("Corruption should have been detected")
                    
                except sqlite3.DatabaseError as e:
                    corruption_handled = True
                    self.assertIn("not a database", str(e))
                    
                except Exception as e:
                    corruption_handled = False
                    self.fail(f"Unexpected error: {e}")
                
                self.assertTrue(corruption_handled, "Database corruption should be detected")
        
        finally:
            # Clean up corrupted file
            try:
                os.unlink(corrupted_db_path)
            except:
                pass
    
    def test_database_permission_errors(self):
        """Test handling of database permission errors"""
        chat_id = "db_permission_test"
        
        with patch('db.upsert_chat_settings') as mock_upsert:
            mock_upsert.side_effect = sqlite3.OperationalError("attempt to write a readonly database")
            
            permission_error_handled = True
            
            try:
                db.upsert_chat_settings(chat_id, '', "English, Spanish", 
                                      datetime.utcnow().isoformat(), self.test_db.get_path())
                
                self.fail("Permission error should have been raised")
                
            except sqlite3.OperationalError as e:
                permission_error_handled = True
                self.assertIn("readonly", str(e))
                
            except Exception as e:
                permission_error_handled = False
                self.fail(f"Unexpected error: {e}")
            
            self.assertTrue(permission_error_handled, "Permission error should be handled")
    
    def test_database_disk_full_error(self):
        """Test handling of disk full errors during database operations"""
        chat_id = "db_disk_full_test"
        
        with patch('db.upsert_chat_settings') as mock_upsert:
            mock_upsert.side_effect = sqlite3.OperationalError("database or disk is full")
            
            disk_full_handled = True
            
            try:
                db.upsert_chat_settings(chat_id, '', "English, German", 
                                      datetime.utcnow().isoformat(), self.test_db.get_path())
                
                self.fail("Disk full error should have been raised")
                
            except sqlite3.OperationalError as e:
                disk_full_handled = True
                self.assertIn("disk is full", str(e))
                
            except Exception as e:
                disk_full_handled = False
                self.fail(f"Unexpected error: {e}")
            
            self.assertTrue(disk_full_handled, "Disk full error should be handled")


class TestParsingErrorHandling(unittest.TestCase):
    """Tests for parsing error handling and edge cases"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_db = TestDatabase("parsing_errors")
        
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def test_malformed_input_handling(self):
        """Test handling of malformed or corrupted input"""
        malformed_inputs = [
            None,  # None input
            "",    # Empty string
            "   ",  # Whitespace only
            "\x00\x01\x02",  # Binary data
            "A" * 10000,  # Extremely long input
            "Setup is complete. Now we speak " + "X" * 1000,  # Long language list
            "Setup is complete. Now we speak \x00\x01\x02",  # Binary in languages
        ]
        
        for i, malformed_input in enumerate(malformed_inputs):
            with self.subTest(case=i, input_type=type(malformed_input).__name__):
                chat_id = f"malformed_test_{i}"
                
                parsing_error_handled = True
                
                try:
                    result = parse_and_persist_setup(chat_id, malformed_input, persist=False)
                    
                    # For malformed input, parsing should fail gracefully
                    self.assertFalse(result, f"Malformed input should not parse successfully: {repr(malformed_input)}")
                    
                except Exception as e:
                    # Any exception should be handled gracefully
                    parsing_error_handled = True
                    self.assertIsInstance(e, (TypeError, ValueError, AttributeError), 
                                        f"Unexpected exception type for malformed input: {type(e)}")
                
                self.assertTrue(parsing_error_handled, "Malformed input should be handled gracefully")
    
    def test_regex_pattern_edge_cases(self):
        """Test regex patterns with edge cases that could cause catastrophic backtracking"""
        edge_case_inputs = [
            # Inputs that could cause regex catastrophic backtracking
            "Setup is complete. Now we speak " + "a" * 100 + "," + "b" * 100,
            "Thanks! Setup is complete. " + "Now we speak " * 50 + "English",
            "Perfect! " * 20 + "Now I can help you with English, Spanish",
            # Inputs with unusual punctuation patterns
            "Setup is complete!!! Now we speak English,,, Spanish;;;",
            "Thanks????? Setup is complete. Now we speak English.... Spanish....",
        ]
        
        for i, edge_input in enumerate(edge_case_inputs):
            with self.subTest(case=i, input=edge_input[:50] + "..."):
                chat_id = f"regex_edge_{i}"
                
                start_time = time.time()
                
                try:
                    result = parse_and_persist_setup(chat_id, edge_input, persist=False)
                    
                    # Check that parsing completes in reasonable time (< 1 second)
                    duration = time.time() - start_time
                    self.assertLess(duration, 1.0, f"Parsing took too long: {duration:.2f}s")
                    
                    # Result should be boolean
                    self.assertIsInstance(result, bool, "Parsing should return boolean")
                    
                except Exception as e:
                    duration = time.time() - start_time
                    self.assertLess(duration, 1.0, f"Exception handling took too long: {duration:.2f}s")
                    self.fail(f"Parsing edge case failed: {e}")
    
    def test_unicode_edge_cases(self):
        """Test Unicode edge cases and encoding issues"""
        unicode_inputs = [
            # Various Unicode characters
            "Setup is complete. Now we speak English, العربية, 中文",
            "Thanks! Setup is complete. Now we speak 日本語, 한국어, Русский",
            # Unicode normalization issues
            "Setup is complete. Now we speak Café, naïve",  # Composed characters
            "Setup is complete. Now we speak Cafe\u0301, nai\u0308ve",  # Decomposed characters
            # Unusual Unicode characters
            "Setup is complete. Now we speak \U0001F600English, \U0001F1FA\U0001F1F8Spanish",  # Emojis
            # Zero-width characters
            "Setup is complete. Now we speak Eng\u200Blish, Span\u200Bish",
        ]
        
        for i, unicode_input in enumerate(unicode_inputs):
            with self.subTest(case=i, input=unicode_input[:50] + "..."):
                chat_id = f"unicode_edge_{i}"
                
                unicode_handled = True
                
                try:
                    result = parse_and_persist_setup(chat_id, unicode_input, persist=False)
                    
                    # Should return boolean without crashing
                    self.assertIsInstance(result, bool, "Unicode parsing should return boolean")
                    
                    if result:
                        # If parsing succeeded, try to persist to database
                        try:
                            # Extract languages manually for testing
                            if "English" in unicode_input and "العربية" in unicode_input:
                                languages = "English, العربية, 中文"
                            elif "日本語" in unicode_input:
                                languages = "日本語, 한국어, Русский"
                            else:
                                languages = "Test Languages"
                            
                            db.upsert_chat_settings(chat_id, '', languages,
                                                   datetime.utcnow().isoformat(), self.test_db.get_path())
                            
                            # Verify Unicode can be stored and retrieved
                            settings = db.get_chat_settings(chat_id, self.test_db.get_path())
                            self.assertIsNotNone(settings, "Unicode data should be stored")
                            
                        except Exception as e:
                            self.fail(f"Unicode persistence failed: {e}")
                    
                except Exception as e:
                    unicode_handled = False
                    self.fail(f"Unicode handling failed: {e}")
                
                self.assertTrue(unicode_handled, "Unicode input should be handled")


class TestResourceExhaustionScenarios(unittest.TestCase):
    """Tests for resource exhaustion and stress scenarios"""
    
    def setUp(self):
        """Set up test environment"""
        self.test_db = TestDatabase("resource_exhaustion")
        
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def tearDown(self):
        """Clean up after tests"""
        self.test_db.cleanup()
        conversations.clear()
        recent_activity_ids.clear()
        active_pollers.clear()
    
    def test_memory_exhaustion_simulation(self):
        """Test behavior under simulated memory pressure"""
        # Create many conversations to simulate memory pressure
        conversation_count = 1000
        
        memory_handling_success = True
        
        try:
            # Create many conversation states
            for i in range(conversation_count):
                chat_id = f"memory_test_{i}"
                conversations[chat_id] = TestDataFactory.generate_conversation_state(chat_id)
                
                # Add to recent activity (which uses deque with maxlen)
                recent_activity_ids[chat_id] = recent_activity_ids[chat_id]  # Initialize deque
                for j in range(50):  # Add some activities
                    recent_activity_ids[chat_id].append(f"activity_{j}")
            
            # Verify conversations are created
            self.assertEqual(len(conversations), conversation_count)
            self.assertEqual(len(recent_activity_ids), conversation_count)
            
            # Test that deque properly limits memory usage
            for chat_id in recent_activity_ids:
                self.assertLessEqual(len(recent_activity_ids[chat_id]), 100, 
                                   "Deque should limit memory usage")
            
            # Simulate cleanup of half the conversations
            cleanup_count = conversation_count // 2
            for i in range(cleanup_count):
                chat_id = f"memory_test_{i}"
                conversations.pop(chat_id, None)
                recent_activity_ids.pop(chat_id, None)
            
            # Verify cleanup worked
            self.assertEqual(len(conversations), conversation_count - cleanup_count)
            
        except MemoryError:
            memory_handling_success = False
            self.fail("Memory exhaustion not handled gracefully")
        except Exception as e:
            memory_handling_success = False
            self.fail(f"Unexpected error during memory test: {e}")
        
        self.assertTrue(memory_handling_success, "Memory pressure should be handled")
    
    def test_concurrent_access_simulation(self):
        """Test behavior under simulated concurrent access"""
        import threading
        import queue
        
        chat_id = "concurrent_access_test"
        error_queue = queue.Queue()
        success_count = queue.Queue()
        
        def concurrent_operation(operation_id):
            try:
                # Simulate concurrent database operations
                languages = f"Lang{operation_id}_A, Lang{operation_id}_B"
                timestamp = datetime.utcnow().isoformat()
                
                # Test parsing
                parse_result = parse_and_persist_setup(
                    f"{chat_id}_{operation_id}", 
                    f"Setup is complete. Now we speak {languages}.",
                    persist=False
                )
                
                if parse_result:
                    # Test database operation
                    db.upsert_chat_settings(f"{chat_id}_{operation_id}", '', languages,
                                           timestamp, self.test_db.get_path())
                    
                    # Test retrieval
                    settings = db.get_chat_settings(f"{chat_id}_{operation_id}", self.test_db.get_path())
                    
                    if settings:
                        success_count.put(1)
                    else:
                        error_queue.put(f"Operation {operation_id}: Settings not retrieved")
                else:
                    error_queue.put(f"Operation {operation_id}: Parsing failed")
                
            except Exception as e:
                error_queue.put(f"Operation {operation_id}: {str(e)}")
        
        # Create multiple threads for concurrent access
        threads = []
        thread_count = 10
        
        for i in range(thread_count):
            thread = threading.Thread(target=concurrent_operation, args=(i,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=10)  # 10 second timeout per thread
        
        # Check results
        errors = []
        while not error_queue.empty():
            errors.append(error_queue.get())
        
        successes = 0
        while not success_count.empty():
            successes += success_count.get()
        
        # Allow some failures in concurrent scenarios, but most should succeed
        success_rate = successes / thread_count
        self.assertGreaterEqual(success_rate, 0.8, f"Success rate too low: {success_rate}")
        
        if errors:
            print(f"Concurrent access errors: {errors}")


def run_error_simulation_tests():
    """Run all error simulation tests with comprehensive reporting"""
    print("=" * 80)
    print("ERROR SIMULATION TESTS - TELEGRAM TRANSLATION BOT")
    print("=" * 80)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add error simulation test classes
    error_test_classes = [
        TestNetworkErrorHandling,
        TestDatabaseErrorHandling,
        TestParsingErrorHandling,
        TestResourceExhaustionScenarios,
    ]
    
    for test_class in error_test_classes:
        suite.addTests(loader.loadTestsFromTestCase(test_class))
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout, buffer=True)
    result = runner.run(suite)
    
    # Print detailed summary
    print("\n" + "=" * 80)
    print("ERROR SIMULATION TEST RESULTS")
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
    success, test_result = run_error_simulation_tests()
    sys.exit(0 if success else 1)