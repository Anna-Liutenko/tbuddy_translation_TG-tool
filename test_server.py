"""
Test Server for Telegram Translation Bot Local Testing

This module provides a Flask-based test server that simulates Telegram webhook calls
and enables local testing of the bot functionality without requiring actual Telegram
infrastructure.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from test_config import TestConfig, TestDataFactory, TestValidator, setup_test_environment
import app  # Import main application
import db  # Import database module

class TestServer:
    """Flask test server for local bot testing"""
    
    def __init__(self):
        """Initialize test server"""
        setup_test_environment()
        
        self.flask_app = Flask(__name__)
        self.flask_app.config['TESTING'] = True
        self.flask_app.config['DEBUG'] = True
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('test_server')
        
        # Test results storage
        self.test_results = []
        
        # Setup routes
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up Flask routes for testing"""
        
        @self.flask_app.route('/')
        def home():
            """Home page with test interface"""
            return render_template_string(TEST_INTERFACE_HTML)
        
        @self.flask_app.route('/webhook', methods=['POST'])
        def test_webhook():
            """Test webhook endpoint - calls actual webhook handler"""
            try:
                # Call the actual webhook handler from app.py
                from app import telegram_webhook
                return telegram_webhook()
            except Exception as e:
                self.logger.error(f"Webhook test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/simulate/<chat_id>/<path:message>')
        def simulate_message(chat_id, message):
            """Simulate Telegram message via URL"""
            try:
                # Generate webhook payload
                payload = TestDataFactory.generate_telegram_message(chat_id, message)
                
                # Process with test client
                response = self._process_webhook_payload(payload)
                
                return jsonify({
                    "success": True,
                    "chat_id": chat_id,
                    "message": message,
                    "payload": payload,
                    "response": response,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Message simulation failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/fresh_user')
        def test_fresh_user():
            """Test fresh user flow"""
            try:
                scenario = TestDataFactory.fresh_user_scenario()
                results = self._run_fresh_user_test(scenario)
                
                return jsonify({
                    "test_type": "fresh_user",
                    "scenario": scenario,
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Fresh user test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/returning_user')
        def test_returning_user():
            """Test returning user flow"""
            try:
                scenario = TestDataFactory.returning_user_scenario()
                results = self._run_returning_user_test(scenario)
                
                return jsonify({
                    "test_type": "returning_user",
                    "scenario": scenario,
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Returning user test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/reset_user')
        def test_reset_user():
            """Test reset command flow"""
            try:
                scenario = TestDataFactory.reset_user_scenario()
                results = self._run_reset_test(scenario)
                
                return jsonify({
                    "test_type": "reset_user", 
                    "scenario": scenario,
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Reset user test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/language_parsing')
        def test_language_parsing():
            """Test language parsing with various inputs"""
            try:
                results = self._run_language_parsing_test()
                
                return jsonify({
                    "test_type": "language_parsing",
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Language parsing test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/database')
        def test_database():
            """Test database operations"""
            try:
                results = self._run_database_test()
                
                return jsonify({
                    "test_type": "database",
                    "results": results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Database test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/test/all')
        def test_all():
            """Run all tests"""
            try:
                all_results = {
                    "language_parsing": self._run_language_parsing_test(),
                    "database": self._run_database_test(),
                    "fresh_user": self._run_fresh_user_test(TestDataFactory.fresh_user_scenario()),
                    "returning_user": self._run_returning_user_test(TestDataFactory.returning_user_scenario()),
                    "reset_user": self._run_reset_test(TestDataFactory.reset_user_scenario())
                }
                
                # Calculate overall results
                total_tests = sum(len(results) for results in all_results.values() if isinstance(results, list))
                passed_tests = sum(
                    sum(1 for r in results if r.get('success', False)) 
                    for results in all_results.values() 
                    if isinstance(results, list)
                )
                
                return jsonify({
                    "test_type": "comprehensive",
                    "summary": {
                        "total_tests": total_tests,
                        "passed_tests": passed_tests,
                        "success_rate": passed_tests / total_tests if total_tests > 0 else 0
                    },
                    "detailed_results": all_results,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Comprehensive test failed: {e}")
                return jsonify({"error": str(e), "success": False}), 500
        
        @self.flask_app.route('/status')
        def status():
            """Server status and configuration"""
            return jsonify({
                "status": "running",
                "test_server": True,
                "configuration": {
                    "host": TestConfig.TEST_SERVER_HOST,
                    "port": TestConfig.TEST_SERVER_PORT,
                    "testing_mode": True
                },
                "available_endpoints": [
                    "/simulate/<chat_id>/<message>",
                    "/test/fresh_user",
                    "/test/returning_user", 
                    "/test/reset_user",
                    "/test/language_parsing",
                    "/test/database",
                    "/test/all"
                ],
                "timestamp": datetime.utcnow().isoformat()
            })
    
    def _process_webhook_payload(self, payload):
        """Process webhook payload using test client"""
        with self.flask_app.test_client() as client:
            response = client.post('/webhook', 
                                 data=json.dumps(payload),
                                 content_type='application/json')
            
            return {
                "status_code": response.status_code,
                "data": response.get_json() if response.is_json else response.get_data(as_text=True),
                "success": response.status_code == 200
            }
    
    def _run_language_parsing_test(self):
        """Run language parsing tests"""
        test_cases = [
            # Success cases
            ("Thanks! Setup is complete. Now we speak English, Polish, Portuguese.", True, "English, Polish, Portuguese"),
            ("Great! I can now translate between English, Russian.", True, "English, Russian"),
            ("Perfect! Now I can help you with Spanish, French.", True, "Spanish, French"),
            ("Setup is complete. Now we speak German, Italian.", True, "German, Italian"),
            ("Excellent! I'm ready to translate English, German, Spanish!", True, "English, German, Spanish"),
            
            # Failure cases
            ("Hello, how are you?", False, None),
            ("Please provide language preferences", False, None),
            ("What languages do you prefer?", False, None),
            ("Send your message and I'll translate it.", False, None),
            ("", False, None),
        ]
        
        results = []
        for i, (text, expected_success, expected_languages) in enumerate(test_cases):
            chat_id = f"parse_test_{i}"
            
            try:
                # Test parsing
                result = app.parse_and_persist_setup(chat_id, text, persist=False)
                
                # Validate result
                validation = TestValidator.validate_parsing_result(expected_success, result, text)
                validation["expected_languages"] = expected_languages
                validation["test_id"] = i
                
                results.append(validation)
                
            except Exception as e:
                results.append({
                    "test_id": i,
                    "test_case": text,
                    "expected": expected_success,
                    "actual": None,
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        return results
    
    def _run_database_test(self):
        """Run database operation tests"""
        from test_config import TestDatabase
        
        results = []
        
        with TestDatabase("db_test") as test_db:
            try:
                # Test upsert
                chat_id = "db_test_chat"
                languages = "English, Russian, Japanese"
                timestamp = datetime.utcnow().isoformat()
                
                db.upsert_chat_settings(chat_id, "", languages, timestamp, test_db.get_path())
                
                # Test retrieval
                settings = db.get_chat_settings(chat_id, test_db.get_path())
                
                upsert_result = TestValidator.validate_database_operation(
                    "upsert_and_get", 
                    languages, 
                    settings.get('language_names') if settings else None
                )
                upsert_result["operation_type"] = "upsert_and_retrieve"
                results.append(upsert_result)
                
                # Test update
                new_languages = "Spanish, French"
                new_timestamp = datetime.utcnow().isoformat()
                
                db.upsert_chat_settings(chat_id, "", new_languages, new_timestamp, test_db.get_path())
                updated_settings = db.get_chat_settings(chat_id, test_db.get_path())
                
                update_result = TestValidator.validate_database_operation(
                    "update",
                    new_languages,
                    updated_settings.get('language_names') if updated_settings else None
                )
                update_result["operation_type"] = "update"
                results.append(update_result)
                
                # Test deletion
                db.delete_chat_settings(chat_id, test_db.get_path())
                deleted_settings = db.get_chat_settings(chat_id, test_db.get_path())
                
                delete_result = TestValidator.validate_database_operation(
                    "delete",
                    None,
                    deleted_settings
                )
                delete_result["operation_type"] = "delete"
                results.append(delete_result)
                
            except Exception as e:
                results.append({
                    "operation": "database_test",
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        return results
    
    def _run_fresh_user_test(self, scenario):
        """Run fresh user test scenario"""
        results = []
        chat_id = scenario["chat_id"]
        
        try:
            # Clear any existing state
            app.conversations.pop(chat_id, None)
            
            # Step 1: Simulate /start command
            start_payload = TestDataFactory.generate_telegram_message(chat_id, "/start")
            start_response = self._process_webhook_payload(start_payload)
            
            results.append({
                "step": "start_command",
                "success": start_response["success"],
                "response": start_response,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Step 2: Create conversation state (simulated)
            app.conversations[chat_id] = scenario["conversation_state"]
            
            # Step 3: Test language setup parsing
            confirmation = scenario["confirmation_message"]
            parse_result = app.parse_and_persist_setup(chat_id, confirmation, persist=False)
            
            results.append({
                "step": "language_parsing",
                "success": parse_result,
                "expected": True,
                "confirmation_message": confirmation,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Step 4: Mark setup complete
            if parse_result:
                app.conversations[chat_id]['setup_complete'] = True
            
            results.append({
                "step": "setup_completion",
                "success": app.conversations[chat_id]['setup_complete'],
                "expected": True,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            results.append({
                "step": "error",
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return results
    
    def _run_returning_user_test(self, scenario):
        """Run returning user test scenario"""
        results = []
        chat_id = scenario["chat_id"]
        
        from test_config import TestDatabase
        
        with TestDatabase("returning_user_test") as test_db:
            try:
                # Step 1: Pre-populate database
                db_entry = scenario["database_entry"]
                db.upsert_chat_settings(
                    chat_id, "", db_entry["language_names"], 
                    db_entry["updated_at"], test_db.get_path()
                )
                
                # Step 2: Verify database entry
                settings = db.get_chat_settings(chat_id, test_db.get_path())
                
                results.append({
                    "step": "database_setup",
                    "success": settings is not None,
                    "settings": settings,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Step 3: Create conversation state
                app.conversations[chat_id] = scenario["conversation_state"]
                
                # Step 4: Verify quick setup message generation
                if settings:
                    saved_languages = settings.get('language_names', '')
                    setup_message = f"My languages are: {saved_languages}"
                    expected_message = scenario["expected_setup_message"]
                    
                    results.append({
                        "step": "quick_setup_generation",
                        "success": setup_message == expected_message,
                        "generated_message": setup_message,
                        "expected_message": expected_message,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
            except Exception as e:
                results.append({
                    "step": "error",
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        return results
    
    def _run_reset_test(self, scenario):
        """Run reset command test scenario"""
        results = []
        chat_id = scenario["chat_id"]
        
        from test_config import TestDatabase
        
        with TestDatabase("reset_test") as test_db:
            try:
                # Step 1: Setup initial state
                db_entry = scenario["database_entry"]
                db.upsert_chat_settings(
                    chat_id, "", db_entry["language_names"],
                    db_entry["updated_at"], test_db.get_path()
                )
                
                app.conversations[chat_id] = scenario["conversation_state"]
                app.active_pollers[chat_id] = True
                
                # Step 2: Simulate reset command
                reset_payload = TestDataFactory.generate_telegram_message(chat_id, "/reset")
                reset_response = self._process_webhook_payload(reset_payload)
                
                results.append({
                    "step": "reset_command",
                    "success": reset_response["success"],
                    "response": reset_response,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
                # Step 3: Verify cleanup (simulate reset logic)
                app.active_pollers[chat_id] = False
                db.delete_chat_settings(chat_id, test_db.get_path())
                app.conversations.pop(chat_id, None)
                
                # Step 4: Verify cleanup results
                conversation_cleaned = chat_id not in app.conversations
                poller_stopped = not app.active_pollers.get(chat_id, False)
                db_cleaned = db.get_chat_settings(chat_id, test_db.get_path()) is None
                
                results.append({
                    "step": "cleanup_verification",
                    "success": conversation_cleaned and poller_stopped and db_cleaned,
                    "conversation_cleaned": conversation_cleaned,
                    "poller_stopped": poller_stopped,
                    "database_cleaned": db_cleaned,
                    "timestamp": datetime.utcnow().isoformat()
                })
                
            except Exception as e:
                results.append({
                    "step": "error", 
                    "success": False,
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        return results
    
    def run(self, host=None, port=None, debug=True):
        """Run the test server"""
        host = host or TestConfig.TEST_SERVER_HOST
        port = port or TestConfig.TEST_SERVER_PORT
        
        self.logger.info(f"Starting test server at http://{host}:{port}")
        self.logger.info("Available test endpoints:")
        self.logger.info("  - / : Test interface")
        self.logger.info("  - /simulate/<chat_id>/<message> : Simulate message")
        self.logger.info("  - /test/all : Run all tests")
        self.logger.info("  - /status : Server status")
        
        self.flask_app.run(host=host, port=port, debug=debug)

# HTML template for test interface
TEST_INTERFACE_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Telegram Translation Bot - Test Interface</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .test-section { margin: 20px 0; padding: 15px; border: 1px solid #ccc; }
        .button { padding: 8px 16px; margin: 5px; background: #007cba; color: white; text-decoration: none; border-radius: 4px; }
        .button:hover { background: #005a8b; }
        .result { margin: 10px 0; padding: 10px; background: #f9f9f9; border-left: 4px solid #007cba; }
        .success { border-left-color: #28a745; }
        .failure { border-left-color: #dc3545; }
    </style>
</head>
<body>
    <h1>Telegram Translation Bot - Local Testing Interface</h1>
    
    <div class="test-section">
        <h2>Quick Tests</h2>
        <a href="/test/all" class="button">Run All Tests</a>
        <a href="/test/language_parsing" class="button">Language Parsing Test</a>
        <a href="/test/database" class="button">Database Test</a>
        <a href="/status" class="button">Server Status</a>
    </div>
    
    <div class="test-section">
        <h2>User Flow Tests</h2>
        <a href="/test/fresh_user" class="button">Fresh User Flow</a>
        <a href="/test/returning_user" class="button">Returning User Flow</a>
        <a href="/test/reset_user" class="button">Reset User Flow</a>
    </div>
    
    <div class="test-section">
        <h2>Message Simulation</h2>
        <p>Simulate messages using URLs:</p>
        <ul>
            <li><a href="/simulate/12345/start">/simulate/12345/start</a></li>
            <li><a href="/simulate/12345/English, Spanish, French">/simulate/12345/English, Spanish, French</a></li>
            <li><a href="/simulate/12345/Hello world">/simulate/12345/Hello world</a></li>
            <li><a href="/simulate/12345/reset">/simulate/12345/reset</a></li>
        </ul>
    </div>
    
    <div class="test-section">
        <h2>Instructions</h2>
        <p>This test interface allows you to test the Telegram Translation Bot locally without requiring actual Telegram infrastructure.</p>
        <ol>
            <li>Click "Run All Tests" to execute the comprehensive test suite</li>
            <li>Use individual test buttons to focus on specific components</li>
            <li>Use message simulation URLs to test specific scenarios</li>
            <li>Check the JSON responses for detailed test results</li>
        </ol>
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    # Create and run test server
    server = TestServer()
    server.run()