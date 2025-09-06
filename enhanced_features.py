"""Enhanced Features for Language Setup and Translation Flow Fix

This module implements the enhanced state management, message classification,
and context restoration logic according to the design document.
"""

import re
import time
import logging
from typing import Dict, Tuple, Optional, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

# Setup logger for this module
logger = logging.getLogger(__name__)

class OperationMode(Enum):
    """Operation modes for the bot"""
    INITIAL_SETUP = "initial_setup"
    RESET = "reset"
    TRANSLATION = "translation"
    CONTEXT_RESTORATION = "context_restoration"

class MessageType(Enum):
    """Types of incoming messages"""
    START_COMMAND = "start_command"
    RESET_COMMAND = "reset_command"
    REGULAR_TEXT = "regular_text"
    OTHER_COMMAND = "other_command"

class ResponseType(Enum):
    """Types of Copilot Studio responses"""
    SETUP_PROMPT = "setup_prompt"
    SETUP_CONFIRMATION = "setup_confirmation"
    TRANSLATION_OUTPUT = "translation_output"
    CONTEXT_ACKNOWLEDGMENT = "context_acknowledgment"
    UNKNOWN = "unknown"

@dataclass
class ConversationState:
    """Enhanced conversation state tracking"""
    id: str
    token: str
    watermark: Optional[str]
    mode: OperationMode
    setup_complete: bool
    last_interaction: float
    context_restored: bool
    awaiting_setup_confirmation: bool
    is_polling: bool = False
    user_from_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'id': self.id,
            'token': self.token,
            'watermark': self.watermark,
            'mode': self.mode.value,
            'setup_complete': self.setup_complete,
            'last_interaction': self.last_interaction,
            'context_restored': self.context_restored,
            'awaiting_setup_confirmation': self.awaiting_setup_confirmation,
            'is_polling': self.is_polling,
            'user_from_id': self.user_from_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationState':
        """Create from dictionary"""
        return cls(
            id=data['id'],
            token=data['token'],
            watermark=data.get('watermark'),
            mode=OperationMode(data.get('mode', OperationMode.TRANSLATION.value)),
            setup_complete=data.get('setup_complete', False),
            last_interaction=data.get('last_interaction', time.time()),
            context_restored=data.get('context_restored', False),
            awaiting_setup_confirmation=data.get('awaiting_setup_confirmation', False),
            is_polling=data.get('is_polling', False),
            user_from_id=data.get('user_from_id')
        )

class MessageClassifier:
    """Classifies incoming messages and Copilot responses"""
    
    @staticmethod
    def classify_incoming_message(text: str) -> MessageType:
        """Classify incoming message type"""
        if not text or not isinstance(text, str):
            return MessageType.REGULAR_TEXT
            
        text = text.strip()
        
        if text == '/start':
            return MessageType.START_COMMAND
        elif text == '/reset':
            return MessageType.RESET_COMMAND
        elif text.startswith('/'):
            return MessageType.OTHER_COMMAND
        else:
            return MessageType.REGULAR_TEXT
    
    @staticmethod
    def classify_copilot_response(text: str) -> ResponseType:
        """Classify response from Copilot Studio"""
        if not text or not isinstance(text, str):
            return ResponseType.UNKNOWN
            
        text = text.strip()
        lowered = text.lower()
        
        # Setup prompts - patterns from Copilot asking for language preferences
        setup_prompt_patterns = [
            "what's languages you prefer",
            "what languages would you like",
            "which languages do you want",
            "please choose your languages",
            "tell me your preferred languages"
        ]
        
        if any(pattern in lowered for pattern in setup_prompt_patterns):
            return ResponseType.SETUP_PROMPT
        
        # Setup confirmations - patterns indicating setup completion
        setup_confirmation_patterns = [
            'setup is complete',
            'setup complete', 
            'thanks! setup is complete',
            'great! i can now translate',
            'perfect! now i can help you with',
            'excellent! i\'m ready to translate',
            'configuration successful',
            'ready for.*translation',
            'send your message and i\'ll translate',
            'send your message and i will translate'
        ]
        
        # Check for setup confirmation with regex patterns
        for pattern in setup_confirmation_patterns:
            if re.search(pattern, lowered):
                return ResponseType.SETUP_CONFIRMATION
        
        # More specific contextual patterns for setup confirmation
        contextual_patterns = [
            r'now we speak\s+[a-z]+',  # "now we speak" followed by languages
            r'thanks.*setup.*complete.*now.*speak',  # Full confirmation message
            r'setup.*complete.*speak.*translate'
        ]
        
        for pattern in contextual_patterns:
            if re.search(pattern, lowered):
                return ResponseType.SETUP_CONFIRMATION
        
        # Translation outputs - check for language code patterns
        # Look for patterns like "en: Hello\nes: Hola" or "{en}: Hello\n{es}: Hola"
        translation_patterns = [
            r'^[a-z]{2}:\s*\S',  # Language code at start of line
            r'^\{[a-z]{2}\}:\s*\S',  # Language code in braces at start
            r'\n[a-z]{2}:\s*\S',  # Language code after newline
            r'\n\{[a-z]{2}\}:\s*\S'  # Language code in braces after newline
        ]
        
        for pattern in translation_patterns:
            if re.search(pattern, text, re.MULTILINE):
                return ResponseType.TRANSLATION_OUTPUT
        
        return ResponseType.UNKNOWN

class ContextRestorer:
    """Handles context restoration for existing users"""
    
    @staticmethod
    def create_restore_message(saved_languages: str) -> str:
        """Create context restoration message - simplified for bot-side handling"""
        # Since we can't modify Copilot Studio YAML, we'll use a simple approach
        # The bot will send the saved languages as a setup message
        if saved_languages and saved_languages != "Configuration Completed":
            return f"My languages are: {saved_languages}"
        else:
            return "start"  # Fallback to normal setup
    
    @staticmethod
    def create_reset_message() -> str:
        """Create reset message - just start fresh setup"""
        return "start"
    
    @staticmethod
    def is_restoration_needed(chat_id: str, conversations: Dict, db_module) -> Tuple[bool, Optional[str]]:
        """Check if context restoration is needed and return saved languages"""
        try:
            # Check if conversation exists and is properly set up
            if chat_id in conversations:
                conv_state = conversations[chat_id]
                if isinstance(conv_state, dict):
                    if conv_state.get('setup_complete') and conv_state.get('context_restored'):
                        return False, None
                elif hasattr(conv_state, 'setup_complete') and hasattr(conv_state, 'context_restored'):
                    if conv_state.setup_complete and conv_state.context_restored:
                        return False, None
            
            # Check database for existing settings
            existing_settings = db_module.get_chat_settings(chat_id)
            if existing_settings and existing_settings.get('language_names'):
                saved_languages = existing_settings.get('language_names', '')
                logger.info(f"Found existing settings for chat {chat_id}: {saved_languages}")
                return True, saved_languages
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking restoration need for chat {chat_id}: {e}")
            return False, None

class StateManager:
    """Enhanced state management for conversations"""
    
    def __init__(self, conversations: Dict):
        self.conversations = conversations
    
    def create_conversation_state(
        self, 
        chat_id: str, 
        conv_id: str, 
        token: str, 
        mode: OperationMode = OperationMode.TRANSLATION,
        user_from_id: Optional[str] = None
    ) -> ConversationState:
        """Create new conversation state"""
        state = ConversationState(
            id=conv_id,
            token=token,
            watermark=None,
            mode=mode,
            setup_complete=False,
            last_interaction=time.time(),
            context_restored=False,
            awaiting_setup_confirmation=False,
            is_polling=False,
            user_from_id=user_from_id
        )
        
        self.conversations[chat_id] = state
        return state
    
    def get_conversation_state(self, chat_id: str) -> Optional[ConversationState]:
        """Get conversation state, handling both new and legacy formats"""
        if chat_id not in self.conversations:
            return None
        
        conv_data = self.conversations[chat_id]
        
        # Handle legacy dictionary format
        if isinstance(conv_data, dict):
            try:
                return ConversationState.from_dict(conv_data)
            except Exception as e:
                logger.warning(f"Failed to convert legacy conversation data for chat {chat_id}: {e}")
                return None
        
        # Handle new ConversationState object
        if isinstance(conv_data, ConversationState):
            return conv_data
        
        logger.warning(f"Unknown conversation data format for chat {chat_id}: {type(conv_data)}")
        return None
    
    def update_conversation_state(self, chat_id: str, **kwargs) -> bool:
        """Update conversation state with new values"""
        try:
            state = self.get_conversation_state(chat_id)
            if not state:
                return False
            
            # Update fields
            for key, value in kwargs.items():
                if hasattr(state, key):
                    setattr(state, key, value)
            
            # Update last interaction time
            state.last_interaction = time.time()
            
            # Store back to conversations dict
            self.conversations[chat_id] = state
            return True
            
        except Exception as e:
            logger.error(f"Error updating conversation state for chat {chat_id}: {e}")
            return False
    
    def clear_conversation_state(self, chat_id: str):
        """Clear conversation state"""
        self.conversations.pop(chat_id, None)
    
    def set_mode(self, chat_id: str, mode: OperationMode) -> bool:
        """Set operation mode for conversation"""
        return self.update_conversation_state(chat_id, mode=mode)
    
    def mark_setup_complete(self, chat_id: str) -> bool:
        """Mark setup as complete"""
        return self.update_conversation_state(
            chat_id, 
            setup_complete=True, 
            mode=OperationMode.TRANSLATION,
            awaiting_setup_confirmation=False
        )
    
    def mark_context_restored(self, chat_id: str) -> bool:
        """Mark context as restored"""
        return self.update_conversation_state(
            chat_id,
            context_restored=True,
            setup_complete=True,
            mode=OperationMode.TRANSLATION
        )

class EnhancedLanguageParser:
    """Enhanced language parsing with better pattern recognition"""
    
    @staticmethod
    def parse_setup_confirmation(text: str) -> Tuple[bool, Optional[str]]:
        """Parse setup confirmation and extract language names"""
        if not isinstance(text, str):
            return False, None

        # Check for setup completion patterns first
        lowered = text.lower()
        
        # Primary confirmation patterns
        confirmation_patterns = [
            'setup is complete',
            'setup complete', 
            'thanks! setup is complete',
            'great! i can now translate',
            'perfect! now i can help you with',
            'excellent! i\'m ready to translate',
            'configuration successful'
        ]
        
        # Check contextual patterns with regex
        contextual_patterns = [
            r'now we speak\s+[a-z]+',
            r'ready for\s+[a-z]+.*translation',
            r'send your message and i\'ll translate',
            r'send your message and i will translate',
            r'thanks.*setup.*complete.*now.*speak.*send.*message'
        ]
        
        is_setup_complete = any(pattern in lowered for pattern in confirmation_patterns)
        
        if not is_setup_complete:
            for pattern in contextual_patterns:
                if re.search(pattern, lowered, re.DOTALL):
                    is_setup_complete = True
                    break
        
        if not is_setup_complete:
            return False, None

        # Extract languages using multiple patterns
        lang_string = None
        
        # Pattern 1: "Now we speak English, Russian, Japanese"
        match = re.search(r'now we speak\s+([^.\n!?]+)', text, re.IGNORECASE)
        if match:
            lang_string = match.group(1).strip()
        
        # Pattern 2: "Thanks! Setup is complete. Now we speak {languages}."
        if not lang_string:
            match = re.search(r'thanks.*setup.*complete.*now we speak\s+([^.\n!?]+)', text, re.IGNORECASE | re.DOTALL)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 3: "translate between English, Russian, Japanese"
        if not lang_string:
            match = re.search(r'translate\s+(?:between\s+)?([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 4: "help you with English, French"
        if not lang_string:
            match = re.search(r'help you with\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 5: "ready to translate English, German, Spanish"
        if not lang_string:
            match = re.search(r'ready to translate\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 6: "Ready for English, Spanish, Portuguese translation"
        if not lang_string:
            match = re.search(r'ready for\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)\s+translation', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 7: Look for language list after confirmation words
        if not lang_string:
            confirmation_match = re.search(r'(setup is complete|setup complete|thanks!|great!|perfect!|excellent!|ready for).*?([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)', text, re.IGNORECASE | re.DOTALL)
            if confirmation_match:
                lang_string = confirmation_match.group(2).strip()
        
        # Pattern 8: "Setup complete. Ready to translate between English and Spanish"
        if not lang_string:
            match = re.search(r'setup complete.*?ready to translate.*?between\s+([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)', text, re.IGNORECASE | re.DOTALL)
            if match:
                lang_string = f"{match.group(1)}, {match.group(2)}"
        
        # Pattern 9: General "between X and Y" pattern
        if not lang_string:
            match = re.search(r'between\s+([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)', text, re.IGNORECASE)
            if match:
                lang_string = f"{match.group(1)}, {match.group(2)}"
        
        # Clean up and validate language string
        if lang_string:
            # Remove trailing punctuation and text
            lang_string = re.sub(r'[.!?].*$', '', lang_string).strip()
            lang_string = lang_string.strip('.,:; ')
            
            if not lang_string or 'no languages' in lang_string.lower():
                return is_setup_complete, None
            
            # Split and filter language names
            parts = re.split(r'[,;]|\s+and\s+', lang_string)
            names = [p.strip().strip('.,:; ') for p in parts if p and p.strip() and len(p.strip()) > 1]
            
            # Filter out common non-language words that might appear in the context
            excluded_words = {'send', 'your', 'message', 'text', 'can', 'help', 'translate', 'between', 'with', 'for'}
            language_names = []
            for name in names:
                clean_name = name.strip()
                # Only exclude if the entire word is in excluded_words (case insensitive)
                if len(clean_name) > 1 and clean_name.lower() not in excluded_words:
                    # Additional check: if it looks like a language name (starts with capital)
                    if clean_name and clean_name[0].isupper():
                        language_names.append(clean_name)
            
            if language_names:
                return is_setup_complete, ', '.join(language_names)
        
        # If setup is complete but no specific languages found, return default
        if is_setup_complete:
            return True, "Configuration Completed"
        
        return False, None

def migrate_legacy_conversation(chat_id: str, legacy_data: Dict) -> ConversationState:
    """Migrate legacy conversation data to new format"""
    try:
        return ConversationState(
            id=legacy_data.get('id', ''),
            token=legacy_data.get('token', ''),
            watermark=legacy_data.get('watermark'),
            mode=OperationMode.TRANSLATION,  # Default mode
            setup_complete=legacy_data.get('setup_complete', False),
            last_interaction=legacy_data.get('last_interaction', time.time()),
            context_restored=False,  # Legacy data doesn't have this
            awaiting_setup_confirmation=False,  # Legacy data doesn't have this
            is_polling=legacy_data.get('is_polling', False),
            user_from_id=None  # Legacy data doesn't have this
        )
    except Exception as e:
        logger.error(f"Error migrating legacy conversation for chat {chat_id}: {e}")
        # Return minimal state
        return ConversationState(
            id='',
            token='',
            watermark=None,
            mode=OperationMode.TRANSLATION,
            setup_complete=False,
            last_interaction=time.time(),
            context_restored=False,
            awaiting_setup_confirmation=False
        )