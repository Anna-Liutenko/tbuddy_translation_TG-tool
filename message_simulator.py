"""
Message Simulation Framework for Telegram Translation Bot

This module provides comprehensive message simulation capabilities for testing
the Telegram translation bot functionality without requiring actual Telegram
infrastructure or live API calls.
"""

import json
import time
import random
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from unittest.mock import Mock, patch
import requests

from test_config import TestDataFactory, TestValidator


class TelegramMessageSimulator:
    """Simulates Telegram webhook messages for testing"""
    
    def __init__(self):
        """Initialize the message simulator"""
        self.logger = logging.getLogger('message_simulator')
        self.message_counter = 1000
    
    def generate_message(self, chat_id: str, text: str, message_type: str = "private") -> Dict[str, Any]:
        """Generate a complete Telegram webhook message payload"""
        self.message_counter += 1
        
        # Generate user ID from chat_id or random
        user_id = self._extract_user_id(chat_id)
        
        message = {
            "update_id": random.randint(100000, 999999),
            "message": {
                "message_id": self.message_counter,
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": f"TestUser{user_id % 1000}",
                    "last_name": "Simulator",
                    "username": f"testuser_{user_id}",
                    "language_code": "en"
                },
                "chat": {
                    "id": int(chat_id) if str(chat_id).isdigit() else user_id,
                    "type": message_type
                },
                "date": int(time.time()),
                "text": text
            }
        }
        
        # Add type-specific fields
        if message_type == "private":
            message["message"]["chat"].update({
                "first_name": f"TestUser{user_id % 1000}",
                "last_name": "Simulator",
                "username": f"testuser_{user_id}"
            })
        elif message_type == "group":
            message["message"]["chat"].update({
                "title": f"Test Group {chat_id}",
                "all_members_are_administrators": True
            })
        elif message_type == "supergroup":
            message["message"]["chat"].update({
                "title": f"Test Supergroup {chat_id}",
                "username": f"testgroup_{chat_id}"
            })
        
        return message
    
    def generate_command_message(self, chat_id: str, command: str, args: str = "") -> Dict[str, Any]:
        """Generate a Telegram command message"""
        text = f"/{command}"
        if args:
            text += f" {args}"
        
        message = self.generate_message(chat_id, text)
        
        # Add entities for command
        message["message"]["entities"] = [{
            "offset": 0,
            "length": len(command) + 1,
            "type": "bot_command"
        }]
        
        return message
    
    def generate_callback_query(self, chat_id: str, data: str, message_text: str = "Test message") -> Dict[str, Any]:
        """Generate a callback query (inline button press)"""
        user_id = self._extract_user_id(chat_id)
        
        return {
            "update_id": random.randint(100000, 999999),
            "callback_query": {
                "id": f"callback_{random.randint(1000, 9999)}",
                "from": {
                    "id": user_id,
                    "is_bot": False,
                    "first_name": f"TestUser{user_id % 1000}",
                    "username": f"testuser_{user_id}"
                },
                "message": {
                    "message_id": self.message_counter,
                    "date": int(time.time()),
                    "chat": {
                        "id": int(chat_id) if str(chat_id).isdigit() else user_id,
                        "type": "private"
                    },
                    "text": message_text
                },
                "data": data
            }
        }
    
    def _extract_user_id(self, chat_id: str) -> int:
        """Extract or generate user ID from chat_id"""
        if str(chat_id).isdigit():
            return int(chat_id)
        
        # Generate consistent ID based on chat_id string
        hash_value = hash(chat_id)
        return abs(hash_value) % 1000000 + 100000  # 6-digit user ID


class BotResponseValidator:
    """Validates bot responses and behavior"""
    
    def __init__(self):
        """Initialize response validator"""
        self.logger = logging.getLogger('response_validator')
    
    def validate_webhook_response(self, response: Any) -> Dict[str, Any]:
        """Validate webhook HTTP response"""
        validation = {
            "timestamp": datetime.utcnow().isoformat(),
            "response_type": type(response).__name__,
            "valid": False,
            "details": {}
        }
        
        try:
            # Check if response has expected attributes
            if hasattr(response, 'status_code'):
                validation["details"]["status_code"] = response.status_code
                validation["valid"] = response.status_code == 200
            
            if hasattr(response, 'json'):
                try:
                    json_data = response.json() if callable(response.json) else response.json
                    validation["details"]["has_json"] = True
                    validation["details"]["json_data"] = json_data
                except:
                    validation["details"]["has_json"] = False
            
            if hasattr(response, 'text'):
                validation["details"]["response_text"] = response.text[:200]  # Truncate for logging
            
        except Exception as e:
            validation["error"] = str(e)
            validation["valid"] = False
        
        return validation
    
    def validate_conversation_state(self, chat_id: str, expected_state: Dict[str, Any]) -> Dict[str, Any]:
        """Validate conversation state matches expectations"""
        from app import conversations
        
        validation = {
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id,
            "valid": False,
            "differences": []
        }
        
        try:
            actual_state = conversations.get(chat_id, {})
            
            for key, expected_value in expected_state.items():
                actual_value = actual_state.get(key)
                
                if actual_value != expected_value:
                    validation["differences"].append({
                        "key": key,
                        "expected": expected_value,
                        "actual": actual_value
                    })
            
            validation["valid"] = len(validation["differences"]) == 0
            validation["actual_state"] = actual_state
            
        except Exception as e:
            validation["error"] = str(e)
            validation["valid"] = False
        
        return validation
    
    def validate_database_state(self, chat_id: str, expected_settings: Dict[str, Any], db_file: str = None) -> Dict[str, Any]:
        """Validate database state matches expectations"""
        import db
        
        validation = {
            "timestamp": datetime.utcnow().isoformat(),
            "chat_id": chat_id,
            "valid": False,
            "details": {}
        }
        
        try:
            actual_settings = db.get_chat_settings(chat_id, db_file)
            
            if expected_settings is None:
                validation["valid"] = actual_settings is None
                validation["details"]["expected_none"] = True
                validation["details"]["actual_none"] = actual_settings is None
            else:
                validation["valid"] = actual_settings is not None
                
                if actual_settings:
                    for key, expected_value in expected_settings.items():
                        actual_value = actual_settings.get(key)
                        validation["details"][f"match_{key}"] = actual_value == expected_value
                        if actual_value != expected_value:
                            validation["valid"] = False
            
            validation["actual_settings"] = actual_settings
            
        except Exception as e:
            validation["error"] = str(e)
            validation["valid"] = False
        
        return validation


class ConversationFlowSimulator:
    """Simulates complete conversation flows for testing"""
    
    def __init__(self):
        """Initialize conversation flow simulator"""
        self.logger = logging.getLogger('conversation_simulator')
        self.message_sim = TelegramMessageSimulator()
        self.validator = BotResponseValidator()
    
    def simulate_fresh_user_flow(self, chat_id: str = None) -> Dict[str, Any]:
        """Simulate complete fresh user setup flow"""
        if not chat_id:
            chat_id = TestDataFactory.generate_chat_id("fresh_user")
        
        flow_results = {
            "flow_type": "fresh_user",
            "chat_id": chat_id,
            "steps": [],
            "overall_success": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Step 1: /start command
            start_msg = self.message_sim.generate_command_message(chat_id, "start")
            step1_result = self._simulate_webhook_call(start_msg)
            flow_results["steps"].append({
                "step": 1,
                "action": "start_command",
                "payload": start_msg,
                "result": step1_result
            })
            
            # Step 2: User provides language preferences
            languages = ["English", "Spanish", "French"]
            language_input = ", ".join(languages)
            lang_msg = self.message_sim.generate_message(chat_id, language_input)
            step2_result = self._simulate_webhook_call(lang_msg)
            flow_results["steps"].append({
                "step": 2,
                "action": "language_input",
                "languages": languages,
                "payload": lang_msg,
                "result": step2_result
            })
            
            # Step 3: Bot confirms setup (simulated)
            confirmation = f"Thanks! Setup is complete. Now we speak {language_input}."
            confirmation_result = self._simulate_setup_confirmation(chat_id, confirmation)
            flow_results["steps"].append({
                "step": 3,
                "action": "setup_confirmation",
                "confirmation": confirmation,
                "result": confirmation_result
            })
            
            # Evaluate overall success
            all_steps_successful = all(
                step["result"].get("success", False) for step in flow_results["steps"]
            )
            flow_results["overall_success"] = all_steps_successful
            
        except Exception as e:
            flow_results["error"] = str(e)
            self.logger.error(f"Fresh user flow simulation failed: {e}")
        
        return flow_results
    
    def simulate_returning_user_flow(self, chat_id: str = None, existing_languages: List[str] = None) -> Dict[str, Any]:
        """Simulate returning user flow with existing settings"""
        if not chat_id:
            chat_id = TestDataFactory.generate_chat_id("returning_user")
        
        if not existing_languages:
            existing_languages = ["English", "German", "Italian"]
        
        flow_results = {
            "flow_type": "returning_user",
            "chat_id": chat_id,
            "existing_languages": existing_languages,
            "steps": [],
            "overall_success": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Step 1: Pre-populate database (simulated)
            from test_config import TestDatabase
            
            with TestDatabase(f"returning_user_{chat_id}") as test_db:
                import db
                
                db.upsert_chat_settings(
                    chat_id, "", ", ".join(existing_languages),
                    datetime.utcnow().isoformat(), test_db.get_path()
                )
                
                step1_result = {"success": True, "database_populated": True}
                flow_results["steps"].append({
                    "step": 1,
                    "action": "database_setup",
                    "result": step1_result
                })
                
                # Step 2: User sends regular message
                regular_msg = self.message_sim.generate_message(chat_id, "Hello, please translate this")
                step2_result = self._simulate_webhook_call(regular_msg)
                flow_results["steps"].append({
                    "step": 2,
                    "action": "regular_message",
                    "payload": regular_msg,
                    "result": step2_result
                })
                
                # Step 3: Verify quick setup (simulated)
                settings = db.get_chat_settings(chat_id, test_db.get_path())
                quick_setup_success = settings is not None and settings.get('language_names') == ", ".join(existing_languages)
                
                flow_results["steps"].append({
                    "step": 3,
                    "action": "quick_setup_verification",
                    "result": {"success": quick_setup_success, "settings": settings}
                })
                
                # Evaluate overall success
                all_steps_successful = all(
                    step["result"].get("success", False) for step in flow_results["steps"]
                )
                flow_results["overall_success"] = all_steps_successful
        
        except Exception as e:
            flow_results["error"] = str(e)
            self.logger.error(f"Returning user flow simulation failed: {e}")
        
        return flow_results
    
    def simulate_reset_flow(self, chat_id: str = None) -> Dict[str, Any]:
        """Simulate reset command flow"""
        if not chat_id:
            chat_id = TestDataFactory.generate_chat_id("reset_user")
        
        flow_results = {
            "flow_type": "reset_user",
            "chat_id": chat_id,
            "steps": [],
            "overall_success": False,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Step 1: Setup initial state (simulated)
            from test_config import TestDatabase
            import db
            from app import conversations, active_pollers
            
            with TestDatabase(f"reset_user_{chat_id}") as test_db:
                # Create initial state
                initial_languages = ["English", "Portuguese"]
                db.upsert_chat_settings(
                    chat_id, "", ", ".join(initial_languages),
                    datetime.utcnow().isoformat(), test_db.get_path()
                )
                
                conversations[chat_id] = {
                    'id': f'conv_{chat_id}',
                    'token': 'test_token',
                    'setup_complete': True
                }
                active_pollers[chat_id] = True
                
                step1_result = {"success": True, "initial_state_created": True}
                flow_results["steps"].append({
                    "step": 1,
                    "action": "initial_state_setup",
                    "result": step1_result
                })
                
                # Step 2: /reset command
                reset_msg = self.message_sim.generate_command_message(chat_id, "reset")
                step2_result = self._simulate_webhook_call(reset_msg)
                flow_results["steps"].append({
                    "step": 2,
                    "action": "reset_command",
                    "payload": reset_msg,
                    "result": step2_result
                })
                
                # Step 3: Verify cleanup (simulated)
                # Simulate the cleanup that should happen
                conversations.pop(chat_id, None)
                active_pollers[chat_id] = False
                db.delete_chat_settings(chat_id, test_db.get_path())
                
                # Verify cleanup
                conversation_cleaned = chat_id not in conversations
                poller_stopped = not active_pollers.get(chat_id, False)
                db_cleaned = db.get_chat_settings(chat_id, test_db.get_path()) is None
                
                cleanup_success = conversation_cleaned and poller_stopped and db_cleaned
                
                flow_results["steps"].append({
                    "step": 3,
                    "action": "cleanup_verification",
                    "result": {
                        "success": cleanup_success,
                        "conversation_cleaned": conversation_cleaned,
                        "poller_stopped": poller_stopped,
                        "database_cleaned": db_cleaned
                    }
                })
                
                # Evaluate overall success
                all_steps_successful = all(
                    step["result"].get("success", False) for step in flow_results["steps"]
                )
                flow_results["overall_success"] = all_steps_successful
        
        except Exception as e:
            flow_results["error"] = str(e)
            self.logger.error(f"Reset flow simulation failed: {e}")
        
        return flow_results
    
    def _simulate_webhook_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Simulate a webhook call with the given payload"""
        try:
            # Mock the Flask request object
            with patch('flask.request') as mock_request:
                mock_request.get_json.return_value = payload
                mock_request.json = payload
                
                # Import and call the webhook handler
                from app import telegram_webhook
                
                try:
                    response = telegram_webhook()
                    return {
                        "success": True,
                        "response": response,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                except Exception as e:
                    return {
                        "success": False,
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    }
        
        except Exception as e:
            return {
                "success": False,
                "error": f"Webhook simulation failed: {e}",
                "timestamp": datetime.utcnow().isoformat()
            }
    
    def _simulate_setup_confirmation(self, chat_id: str, confirmation_text: str) -> Dict[str, Any]:
        """Simulate setup confirmation processing"""
        try:
            from app import parse_and_persist_setup
            
            result = parse_and_persist_setup(chat_id, confirmation_text, persist=False)
            
            return {
                "success": result,
                "confirmation_text": confirmation_text,
                "parsed": result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


class MessageTemplateLibrary:
    """Library of message templates for testing various scenarios"""
    
    LANGUAGE_SETUP_CONFIRMATIONS = [
        "Thanks! Setup is complete. Now we speak {languages}.",
        "Great! I can now translate between {languages}.",
        "Perfect! Now I can help you with {languages}.",
        "Setup is complete. Now we speak {languages}.",
        "Excellent! I'm ready to translate {languages}!",
        "Setup complete! Ready for {languages} translation.\nSend your message and I'll translate it.",
        "Configuration successful! Languages: {languages}.\nHow can I help you today?",
    ]
    
    LANGUAGE_SETUP_FAILURES = [
        "I don't understand your request.",
        "Please provide your language preferences.",
        "What languages would you like to use?",
        "Setup is incomplete. Please try again.",
        "No languages are mentioned in your request.",
        "I need at least 2 languages to help with translation.",
        "",  # Empty response
        "Error: Unable to process language setup.",
    ]
    
    USER_MESSAGES = [
        "Hello, how are you?",
        "Please translate this text",
        "Привет, как дела?",  # Russian
        "Hola, ¿cómo estás?",  # Spanish
        "Bonjour, comment ça va?",  # French
        "Guten Tag, wie geht es dir?",  # German
        "こんにちは、元気ですか？",  # Japanese
        "你好吗？",  # Chinese
        "The quick brown fox jumps over the lazy dog.",
        "This is a longer message that contains multiple sentences. It should test how the bot handles longer text. The translation should preserve the meaning while adapting to the target language.",
    ]
    
    COMMANDS = [
        "/start",
        "/help",
        "/reset",
        "/settings",
        "/languages",
    ]
    
    @classmethod
    def get_confirmation_variations(cls, languages: List[str]) -> List[str]:
        """Get variations of confirmation messages with given languages"""
        language_string = ", ".join(languages)
        return [template.format(languages=language_string) for template in cls.LANGUAGE_SETUP_CONFIRMATIONS]
    
    @classmethod
    def get_failure_messages(cls) -> List[str]:
        """Get list of messages that should not be parsed as confirmations"""
        return cls.LANGUAGE_SETUP_FAILURES.copy()
    
    @classmethod
    def get_user_messages(cls) -> List[str]:
        """Get list of typical user messages"""
        return cls.USER_MESSAGES.copy()
    
    @classmethod
    def get_commands(cls) -> List[str]:
        """Get list of bot commands"""
        return cls.COMMANDS.copy()


class ErrorSimulator:
    """Simulates various error conditions for testing"""
    
    def __init__(self):
        """Initialize error simulator"""
        self.logger = logging.getLogger('error_simulator')
    
    def simulate_network_timeout(self, timeout_duration: float = 10.0):
        """Simulate network timeout"""
        def timeout_side_effect(*args, **kwargs):
            raise requests.exceptions.Timeout(f"Request timed out after {timeout_duration} seconds")
        
        return patch('requests.post', side_effect=timeout_side_effect)
    
    def simulate_connection_error(self):
        """Simulate network connection error"""
        def connection_error_side_effect(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Connection failed")
        
        return patch('requests.post', side_effect=connection_error_side_effect)
    
    def simulate_http_error(self, status_code: int = 500):
        """Simulate HTTP error response"""
        mock_response = Mock()
        mock_response.status_code = status_code
        mock_response.json.return_value = {"error": f"HTTP {status_code} error"}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(f"HTTP {status_code}")
        
        def http_error_side_effect(*args, **kwargs):
            return mock_response
        
        return patch('requests.post', side_effect=http_error_side_effect)
    
    def simulate_invalid_json_response(self):
        """Simulate invalid JSON in API response"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        mock_response.text = "Invalid JSON response"
        
        def invalid_json_side_effect(*args, **kwargs):
            return mock_response
        
        return patch('requests.post', side_effect=invalid_json_side_effect)
    
    def simulate_database_error(self):
        """Simulate database connection/operation error"""
        def db_error_side_effect(*args, **kwargs):
            raise Exception("Database connection failed")
        
        return patch('db.get_chat_settings', side_effect=db_error_side_effect)


# Test utility functions
def create_test_scenarios(count: int = 5) -> List[Dict[str, Any]]:
    """Create a set of test scenarios for comprehensive testing"""
    scenarios = []
    
    for i in range(count):
        scenario_type = random.choice(["fresh_user", "returning_user", "reset_user"])
        
        if scenario_type == "fresh_user":
            scenario = TestDataFactory.fresh_user_scenario()
        elif scenario_type == "returning_user":
            scenario = TestDataFactory.returning_user_scenario()
        else:  # reset_user
            scenario = TestDataFactory.reset_user_scenario()
        
        scenarios.append(scenario)
    
    return scenarios


def run_message_simulation_tests() -> Dict[str, Any]:
    """Run comprehensive message simulation tests"""
    simulator = ConversationFlowSimulator()
    
    results = {
        "test_suite": "message_simulation",
        "start_time": datetime.utcnow().isoformat(),
        "tests": [],
        "summary": {}
    }
    
    # Test fresh user flows
    for i in range(3):
        fresh_result = simulator.simulate_fresh_user_flow()
        results["tests"].append(fresh_result)
    
    # Test returning user flows
    for i in range(3):
        returning_result = simulator.simulate_returning_user_flow()
        results["tests"].append(returning_result)
    
    # Test reset flows
    for i in range(2):
        reset_result = simulator.simulate_reset_flow()
        results["tests"].append(reset_result)
    
    # Calculate summary
    total_tests = len(results["tests"])
    successful_tests = sum(1 for test in results["tests"] if test.get("overall_success", False))
    
    results["summary"] = {
        "total_tests": total_tests,
        "successful_tests": successful_tests,
        "success_rate": successful_tests / total_tests if total_tests > 0 else 0,
        "end_time": datetime.utcnow().isoformat()
    }
    
    return results


if __name__ == '__main__':
    # Run message simulation tests if executed directly
    logging.basicConfig(level=logging.INFO)
    results = run_message_simulation_tests()
    print(json.dumps(results, indent=2))