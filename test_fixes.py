#!/usr/bin/env python3
"""
Test script to validate the fixes made to the translation bot.
This script tests the parsing logic and database functionality.
"""

import sys
import os
import importlib

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the modules
import app
import db

def test_parse_and_persist_setup():
    """Test the improved parse_and_persist_setup function."""
    print("Testing parse_and_persist_setup function...")
    
    test_cases = [
        # Expected to parse successfully
        ("Thanks! Setup is complete. Now we speak English, Russian, Japanese.", True),
        ("Setup is complete. Now we speak German, French.", True),
        ("Thanks! Setup is complete. Now we speak Korean, Chinese, Spanish.\nSend your message and I'll translate it.", True),
        
        # Expected to fail parsing
        ("What's languages you prefer? Write 2 or 3 languages.", False),
        ("Hello, how are you?", False),
        ("Send your message and I'll translate it.", False),
    ]
    
    all_passed = True
    
    for i, (text, expected) in enumerate(test_cases, 1):
        try:
            result = app.parse_and_persist_setup(f"test_chat_{i}", text, persist=False)
            if result == expected:
                print(f"✓ Test {i}: PASSED - '{text[:50]}...' -> {result}")
            else:
                print(f"✗ Test {i}: FAILED - '{text[:50]}...' -> {result} (expected {expected})")
                all_passed = False
        except Exception as e:
            print(f"✗ Test {i}: ERROR - {e}")
            all_passed = False
    
    return all_passed

def test_database_functionality():
    """Test database operations."""
    print("\nTesting database functionality...")
    
    try:
        # Initialize DB
        db.init_db()
        print("✓ Database initialized successfully")
        
        # Test upsert
        test_chat_id = "test_999"
        db.upsert_chat_settings(test_chat_id, "en,ru", "English, Russian", "2025-01-01T00:00:00")
        print("✓ Upsert operation successful")
        
        # Test get
        settings = db.get_chat_settings(test_chat_id)
        if settings and settings.get('language_names') == "English, Russian":
            print("✓ Get operation successful")
        else:
            print(f"✗ Get operation failed: {settings}")
            return False
        
        # Test delete
        db.delete_chat_settings(test_chat_id)
        settings = db.get_chat_settings(test_chat_id)
        if settings is None:
            print("✓ Delete operation successful")
        else:
            print(f"✗ Delete operation failed: {settings}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False

def main():
    """Run all tests."""
    print("=" * 60)
    print("Running Translation Bot Fix Validation Tests")
    print("=" * 60)
    
    parsing_tests_passed = test_parse_and_persist_setup()
    db_tests_passed = test_database_functionality()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS:")
    print(f"Parse/Persist Tests: {'PASSED' if parsing_tests_passed else 'FAILED'}")
    print(f"Database Tests: {'PASSED' if db_tests_passed else 'FAILED'}")
    
    if parsing_tests_passed and db_tests_passed:
        print("\n✓ ALL TESTS PASSED - The fixes are working correctly!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED - Review the issues above")
        return 1

if __name__ == "__main__":
    sys.exit(main())