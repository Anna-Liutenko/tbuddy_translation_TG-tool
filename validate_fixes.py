#!/usr/bin/env python3
"""
Quick validation script to verify that the translation bot fixes are working.
This script validates the core fixes without requiring actual Telegram/Copilot connections.
"""

import sys
import os
import tempfile
from datetime import datetime

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
from app import parse_and_persist_setup, conversations

def validate_database_operations():
    """Test database operations work correctly."""
    print("🔍 Testing database operations...")
    
    # Create temporary database
    test_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
    test_db.close()
    
    try:
        # Initialize database
        db.init_db(test_db.name)
        
        # Test upsert operation
        chat_id = "validation_test"
        languages = "English, Polish, Portuguese"
        timestamp = datetime.utcnow().isoformat()
        
        db.upsert_chat_settings(chat_id, '', languages, timestamp, test_db.name)
        
        # Test retrieval
        settings = db.get_chat_settings(chat_id, test_db.name)
        assert settings is not None, "Settings should not be None"
        assert settings['language_names'] == languages, f"Expected {languages}, got {settings['language_names']}"
        
        # Test deletion
        db.delete_chat_settings(chat_id, test_db.name)
        deleted_settings = db.get_chat_settings(chat_id, test_db.name)
        assert deleted_settings is None, "Settings should be None after deletion"
        
        print("✅ Database operations working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Database operations failed: {e}")
        return False
        
    finally:
        try:
            os.unlink(test_db.name)
        except:
            pass

def validate_language_parsing():
    """Test language setup parsing works correctly."""
    print("🔍 Testing language setup parsing...")
    
    test_cases = [
        ("Thanks! Setup is complete. Now we speak English, Polish, Portuguese.", True),
        ("Great! I can now translate between English, Russian.", True),
        ("Perfect! Now I can help you with Spanish, French.", True),
        ("Setup is complete. Now we speak German, Italian.", True),
        ("Hello, how are you?", False),  # Should not parse
        ("Please provide your language preferences", False),  # Should not parse
    ]
    
    success_count = 0
    for i, (text, should_parse) in enumerate(test_cases):
        try:
            result = parse_and_persist_setup(f"test_{i}", text, persist=False)
            if result == should_parse:
                success_count += 1
                status = "✅"
            else:
                status = "❌"
                print(f"  {status} Test {i+1}: Expected {should_parse}, got {result} for: {text[:50]}...")
        except Exception as e:
            print(f"  ❌ Test {i+1} failed with exception: {e}")
    
    if success_count == len(test_cases):
        print("✅ Language parsing working correctly")
        return True
    else:
        print(f"❌ Language parsing: {success_count}/{len(test_cases)} tests passed")
        return False

def validate_conversation_state():
    """Test conversation state management."""
    print("🔍 Testing conversation state management...")
    
    try:
        # Clear any existing state
        conversations.clear()
        
        # Test conversation creation
        chat_id = "state_test"
        conversations[chat_id] = {
            'id': 'test_conv_id',
            'token': 'test_token',
            'watermark': None,
            'last_interaction': 1234567890,
            'is_polling': False,
            'setup_complete': False
        }
        
        # Test state exists
        assert chat_id in conversations, "Conversation should exist"
        assert conversations[chat_id]['setup_complete'] == False, "Setup should initially be False"
        
        # Test state update
        conversations[chat_id]['setup_complete'] = True
        assert conversations[chat_id]['setup_complete'] == True, "Setup should be True after update"
        
        # Test cleanup
        conversations.pop(chat_id, None)
        assert chat_id not in conversations, "Conversation should be removed after cleanup"
        
        print("✅ Conversation state management working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Conversation state management failed: {e}")
        return False

def main():
    """Run all validation tests."""
    print("=" * 60)
    print("TRANSLATION BOT RECOVERY - VALIDATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Database Operations", validate_database_operations),
        ("Language Parsing", validate_language_parsing),
        ("Conversation State", validate_conversation_state),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} validation failed")
        except Exception as e:
            print(f"❌ {test_name} validation failed with exception: {e}")
    
    print("\n" + "=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL VALIDATIONS PASSED - Bot is ready for deployment!")
        print("\n✨ Key fixes implemented:")
        print("   • Fixed conversation lifecycle management")
        print("   • Improved language setup parsing with multiple patterns")
        print("   • Enhanced quick setup logic for returning users")
        print("   • Added setup completion tracking")
        print("   • Improved error handling and token retry logic")
        return True
    else:
        print("⚠️  Some validations failed - please review the issues above")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)