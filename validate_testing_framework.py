#!/usr/bin/env python3
"""
Quick Validation Script for Telegram Translation Bot Testing Implementation

This script performs a quick validation of the testing framework implementation
and provides immediate feedback on the completeness and functionality.
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def validate_file_structure():
    """Validate that all required test files are present"""
    print("🔍 Validating file structure...")
    
    required_files = [
        ".env.testing",
        "test_config.py",
        "test_server.py", 
        "message_simulator.py",
        "test_utilities.py",
        "comprehensive_test_runner.py",
        "tests/comprehensive_unit_tests.py",
        "tests/integration_tests.py",
        "tests/error_simulation_tests.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = project_root / file_path
        if not full_path.exists():
            missing_files.append(file_path)
        else:
            print(f"  ✅ {file_path}")
    
    if missing_files:
        print(f"  ❌ Missing files: {missing_files}")
        return False
    
    print("  ✅ All required files present")
    return True

def validate_imports():
    """Validate that all modules can be imported without errors"""
    print("\n🔍 Validating module imports...")
    
    modules_to_test = [
        "test_config",
        "message_simulator", 
        "test_utilities"
    ]
    
    import_errors = []
    
    for module_name in modules_to_test:
        try:
            __import__(module_name)
            print(f"  ✅ {module_name}")
        except Exception as e:
            print(f"  ❌ {module_name}: {e}")
            import_errors.append((module_name, str(e)))
    
    if import_errors:
        print(f"  ❌ Import errors found: {len(import_errors)}")
        return False
    
    print("  ✅ All modules import successfully")
    return True

def validate_test_configuration():
    """Validate test configuration and environment setup"""
    print("\n🔍 Validating test configuration...")
    
    try:
        from test_config import TestConfig, TestDatabase, TestDataFactory
        
        # Test database creation
        test_db = TestDatabase("validation_test")
        db_path = test_db.get_path()
        
        if not os.path.exists(db_path):
            print(f"  ❌ Test database not created: {db_path}")
            return False
        
        print(f"  ✅ Test database creation: {db_path}")
        
        # Test data factory
        scenario = TestDataFactory.fresh_user_scenario()
        if not isinstance(scenario, dict) or "chat_id" not in scenario:
            print(f"  ❌ Test data factory not working properly")
            return False
        
        print(f"  ✅ Test data factory working")
        
        # Cleanup
        test_db.cleanup()
        
        print("  ✅ Test configuration valid")
        return True
        
    except Exception as e:
        print(f"  ❌ Test configuration error: {e}")
        return False

def validate_core_functionality():
    """Validate core bot functionality for testing"""
    print("\n🔍 Validating core functionality...")
    
    try:
        # Import main app components
        from app import parse_and_persist_setup, conversations
        import db
        
        # Test language parsing
        test_chat_id = "validation_test_001"
        test_confirmation = "Thanks! Setup is complete. Now we speak English, Spanish, French."
        
        result = parse_and_persist_setup(test_chat_id, test_confirmation, persist=False)
        if not result:
            print(f"  ❌ Language parsing not working")
            return False
        
        print(f"  ✅ Language parsing working")
        
        # Test database operations (using temporary database)
        from test_config import TestDatabase
        test_db = TestDatabase("validation_db_test")
        
        try:
            # Test upsert
            db.upsert_chat_settings(test_chat_id, "", "English, Spanish, French", 
                                   "2025-01-01T00:00:00", test_db.get_path())
            
            # Test retrieval
            settings = db.get_chat_settings(test_chat_id, test_db.get_path())
            if not settings or settings.get('language_names') != "English, Spanish, French":
                print(f"  ❌ Database operations not working")
                return False
            
            print(f"  ✅ Database operations working")
            
        finally:
            test_db.cleanup()
        
        print("  ✅ Core functionality valid")
        return True
        
    except Exception as e:
        print(f"  ❌ Core functionality error: {e}")
        return False

def run_quick_test_sample():
    """Run a quick sample of tests to verify the framework works"""
    print("\n🔍 Running quick test sample...")
    
    try:
        from test_config import TestDatabase, TestDataFactory
        from app import parse_and_persist_setup
        import db
        
        # Create test database
        test_db = TestDatabase("quick_test")
        
        try:
            # Test 1: Fresh user scenario
            scenario = TestDataFactory.fresh_user_scenario()
            chat_id = scenario["chat_id"]
            confirmation = scenario["confirmation_message"]
            
            # Test parsing
            parse_result = parse_and_persist_setup(chat_id, confirmation, persist=False)
            if not parse_result:
                print(f"  ❌ Fresh user scenario parsing failed")
                return False
            
            # Test database persistence
            db.upsert_chat_settings(chat_id, "", scenario["expected_languages"],
                                   "2025-01-01T00:00:00", test_db.get_path())
            
            settings = db.get_chat_settings(chat_id, test_db.get_path())
            if not settings:
                print(f"  ❌ Database persistence failed")
                return False
            
            print(f"  ✅ Fresh user scenario test passed")
            
            # Test 2: Returning user scenario  
            returning_scenario = TestDataFactory.returning_user_scenario()
            returning_chat_id = returning_scenario["chat_id"]
            existing_langs = returning_scenario["existing_languages"]
            
            # Pre-populate database
            db.upsert_chat_settings(returning_chat_id, "", ", ".join(existing_langs),
                                   "2025-01-01T00:00:00", test_db.get_path())
            
            # Verify retrieval
            returning_settings = db.get_chat_settings(returning_chat_id, test_db.get_path())
            if not returning_settings:
                print(f"  ❌ Returning user scenario failed")
                return False
            
            print(f"  ✅ Returning user scenario test passed")
            
            # Test 3: Reset scenario
            reset_scenario = TestDataFactory.reset_user_scenario()
            reset_chat_id = reset_scenario["chat_id"]
            
            # Setup initial state
            db.upsert_chat_settings(reset_chat_id, "", "English, German",
                                   "2025-01-01T00:00:00", test_db.get_path())
            
            # Simulate reset
            db.delete_chat_settings(reset_chat_id, test_db.get_path())
            
            # Verify deletion
            reset_settings = db.get_chat_settings(reset_chat_id, test_db.get_path())
            if reset_settings is not None:
                print(f"  ❌ Reset scenario failed")
                return False
            
            print(f"  ✅ Reset scenario test passed")
            
        finally:
            test_db.cleanup()
        
        print("  ✅ Quick test sample completed successfully")
        return True
        
    except Exception as e:
        print(f"  ❌ Quick test sample failed: {e}")
        return False

def validate_test_server():
    """Validate that the test server can be created"""
    print("\n🔍 Validating test server...")
    
    try:
        from test_server import TestServer
        
        # Create test server instance (but don't run it)
        server = TestServer()
        
        if not hasattr(server, 'flask_app'):
            print(f"  ❌ Test server not properly initialized")
            return False
        
        print(f"  ✅ Test server can be created")
        return True
        
    except Exception as e:
        print(f"  ❌ Test server validation failed: {e}")
        return False

def main():
    """Run comprehensive validation"""
    print("=" * 80)
    print("TELEGRAM TRANSLATION BOT - TESTING FRAMEWORK VALIDATION")
    print("=" * 80)
    
    # Configure logging
    logging.basicConfig(level=logging.WARNING)  # Reduce noise during validation
    
    validation_steps = [
        ("File Structure", validate_file_structure),
        ("Module Imports", validate_imports),
        ("Test Configuration", validate_test_configuration),
        ("Core Functionality", validate_core_functionality),
        ("Test Server", validate_test_server),
        ("Quick Test Sample", run_quick_test_sample),
    ]
    
    passed_steps = 0
    total_steps = len(validation_steps)
    
    for step_name, step_function in validation_steps:
        print(f"\n📋 {step_name}")
        try:
            if step_function():
                passed_steps += 1
                print(f"✅ {step_name} - PASSED")
            else:
                print(f"❌ {step_name} - FAILED")
        except Exception as e:
            print(f"❌ {step_name} - ERROR: {e}")
    
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)
    print(f"Steps Passed: {passed_steps}/{total_steps}")
    print(f"Success Rate: {passed_steps/total_steps:.1%}")
    
    if passed_steps == total_steps:
        print("🎉 ALL VALIDATIONS PASSED - Testing framework is ready!")
        print("\n✨ Next Steps:")
        print("   1. Run comprehensive tests: python comprehensive_test_runner.py")
        print("   2. Start test server: python test_server.py")
        print("   3. Run specific test suites: python -m pytest tests/")
        print("   4. Generate test reports: python comprehensive_test_runner.py --verbose")
        return True
    else:
        print("⚠️  Some validations failed - please review the issues above")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)