import os
import sys
import os
import time
import json
import logging
import re
import requests
import threading
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import db
from collections import deque, defaultdict
from datetime import datetime
from logging.handlers import RotatingFileHandler

# Import enhanced features
from enhanced_features import (
    OperationMode, MessageType, ResponseType, ConversationState,
    MessageClassifier, ContextRestorer, StateManager, EnhancedLanguageParser,
    migrate_legacy_conversation
)

# Загружаем переменные из файла .env
load_dotenv()

# --- НАСТРОЙКИ: загружаются из файла .env ---
# 1. Токен вашего Telegram бота от @BotFather
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")

# 2. Секрет вашего бота из Copilot Studio (Settings -> Channels -> Direct Line)
DIRECT_LINE_SECRET = os.getenv("DIRECT_LINE_SECRET")

# 3. URL для получения токена Direct Line.
DIRECT_LINE_ENDPOINT = "https://directline.botframework.com/v3/directline/conversations"

# Note: build Telegram API URL at send time so updated tokens are always used
# ---------------------------------------------
# Local debug fallback: when DEBUG_LOCAL=1, messages will be printed to console
DEBUG_LOCAL = os.getenv('DEBUG_LOCAL', '0') == '1'
DEBUG_VERBOSE = os.getenv('DEBUG_VERBOSE', '0') == '1'
# When enabled (set TELEGRAM_LOG_RESPONSES=1 in /etc/tbuddy/env), log full
# Telegram HTTP request payload and response (status + body) at DEBUG level.
# Use this temporarily for diagnostics; don't enable permanently in prod.
TELEGRAM_LOG_RESPONSES = os.getenv('TELEGRAM_LOG_RESPONSES', '0') == '1'

# Инициализация веб-сервера Flask
app = Flask(__name__)

# --- Настройка логирования ---
LOG_FILE = os.getenv('LOG_FILE', 'run.log')  # По умолчанию пишет в run.log
LOG_LEVEL_STR = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)

# Убираем стандартные обработчики Flask
app.logger.handlers.clear()

# Настраиваем форматтер
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s [in %(pathname)s:%(lineno)d]')

# Обработчик для вывода в консоль (stdout)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
app.logger.addHandler(stream_handler)

# Обработчик для записи в ротируемый файл, если LOG_FILE указан
if LOG_FILE:
    try:
        # 10 MB на файл, храним 5 старых файлов
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setFormatter(formatter)
        app.logger.addHandler(file_handler)
    except Exception as e:
        app.logger.error(f"Не удалось настроить логирование в файл {LOG_FILE}: {e}")

app.logger.setLevel(LOG_LEVEL)
# --- Конец настройки логирования ---

# Словарь для хранения активных диалогов.
# В реальном приложении лучше использовать базу данных (например, Redis или SQLite).
# Ключ: ID чата в Telegram, Значение: ID диалога в Copilot Studio и токен.
conversations = {}
# Initialize enhanced state manager
state_manager = StateManager(conversations)
# Global dictionary to track active long polling tasks
active_pollers = {}
# store last user message per chat as a simple fallback
last_user_message = {}

# Recent activity ids per chat to avoid duplicate forwards (keeps last 100 IDs)
recent_activity_ids = defaultdict(lambda: deque(maxlen=100))

# Simple SQLite DB to persist chat settings when Copilot confirms setup
DB_PATH = os.path.join(os.path.dirname(__file__), 'chat_settings.db')

# DB abstraction: use db.py for all ChatSettings access
# NOTE: db.py currently uses SQLite and will raise NotImplementedError
# if DATABASE_URL is set. This centralizes DB access for easier future migration.
import db

def parse_and_persist_setup(chat_id, text, persist=True, is_from_copilot=True):
    """Enhanced setup parsing using the new EnhancedLanguageParser.
    
    This version uses the enhanced parsing logic to better detect setup completion
    messages from Copilot Studio and extract language information.
    
    Args:
        chat_id: The chat ID
        text: The text to parse
        persist: Whether to persist to database
        is_from_copilot: Whether this message is confirmed to be from Copilot Studio
    """
    try:
        if not isinstance(text, str) or not is_from_copilot:
            app.logger.debug("Skipping parse_and_persist_setup for non-Copilot message: %s", text[:50])
            return False

        # Use enhanced language parser
        is_setup_complete, language_names = EnhancedLanguageParser.parse_setup_confirmation(text)
        
        if not is_setup_complete:
            app.logger.debug("No setup completion patterns found in: %s", text[:100])
            return False
        
        if not language_names:
            app.logger.warning("Setup completion detected but no language names found: %s", text)
            # Use existing settings if available or default completion
            try:
                existing_settings = db.get_chat_settings(chat_id)
                if existing_settings and existing_settings.get('language_names'):
                    language_names = existing_settings['language_names']
                else:
                    language_names = "Configuration Completed"
            except Exception:
                language_names = "Configuration Completed"
        
        if persist:
            app.logger.info("SUCCESS: Parsed and persisting language names for chat %s: [%s]", chat_id, language_names)
            db.upsert_chat_settings(chat_id, '', language_names, datetime.utcnow().isoformat())
            
            # Update conversation state using state manager
            state_manager.mark_setup_complete(chat_id)
        
        return True
    except Exception as e:
        app.logger.error("Error in enhanced parse_and_persist_setup for chat %s: %s", chat_id, e, exc_info=True)
        return False


def handle_initial_setup(chat_id, user_from_id):
    """Handle /start command - initial setup mode"""
    app.logger.info("Handling initial setup for chat %s", chat_id)
    
    # Stop any active polling
    active_pollers[chat_id] = False
    
    # Clear all state
    state_manager.clear_conversation_state(chat_id)
    last_user_message.pop(chat_id, None)
    if chat_id in recent_activity_ids:
        del recent_activity_ids[chat_id]
    
    # Start new conversation in setup mode
    conv_id, token = start_direct_line_conversation()
    if conv_id and token:
        state = state_manager.create_conversation_state(
            chat_id, conv_id, token, 
            mode=OperationMode.INITIAL_SETUP,
            user_from_id=user_from_id
        )
        state_manager.update_conversation_state(chat_id, awaiting_setup_confirmation=True)
        return conv_id, token
    
    return None, None


def handle_reset_setup(chat_id, user_from_id):
    """Handle /reset command - reset mode"""
    app.logger.info("Handling reset setup for chat %s", chat_id)
    
    # Stop any active polling
    active_pollers[chat_id] = False
    
    # Clear database settings
    try:
        db.delete_chat_settings(chat_id)
        app.logger.info("Deleted DB settings for chat %s", chat_id)
    except Exception as e:
        app.logger.error("Error deleting DB settings for chat %s: %s", chat_id, e, exc_info=True)
    
    # Clear conversation state
    state_manager.clear_conversation_state(chat_id)
    last_user_message.pop(chat_id, None)
    if chat_id in recent_activity_ids:
        del recent_activity_ids[chat_id]
    
    # Start new conversation in setup mode
    conv_id, token = start_direct_line_conversation()
    if conv_id and token:
        state = state_manager.create_conversation_state(
            chat_id, conv_id, token,
            mode=OperationMode.INITIAL_SETUP,
            user_from_id=user_from_id
        )
        state_manager.update_conversation_state(chat_id, awaiting_setup_confirmation=True)
        
        return conv_id, token
    
    return None, None


def handle_translation_request(chat_id, user_from_id, message):
    """Handle regular translation message"""
    app.logger.info("Handling translation request for chat %s: %s", chat_id, message[:50])
    
    # Check if we need context restoration
    restoration_needed, saved_languages = ContextRestorer.is_restoration_needed(chat_id, conversations, db)
    
    if restoration_needed and saved_languages:
        app.logger.info("Context restoration needed for chat %s with languages: %s", chat_id, saved_languages)
        
        # Create new conversation if needed
        conv_id, token = get_or_create_conversation(chat_id, user_from_id)
        if not conv_id or not token:
            return None, None
        
        # Send simplified context restoration message
        restore_message = ContextRestorer.create_restore_message(saved_languages)
        restore_activity_id = send_message_to_copilot(conv_id, token, restore_message, from_id=user_from_id)
        if restore_activity_id:
            recent_activity_ids[chat_id].append(restore_activity_id)
        
        # Wait for response and process setup confirmation
        time.sleep(2.0)
        
        # Check for setup confirmation from the "My languages are:" message
        responses, new_watermark = get_copilot_response(conv_id, token, None, user_from_id)
        if new_watermark:
            state_manager.update_conversation_state(chat_id, watermark=new_watermark)
        
        context_restored = False
        if responses:
            for response in responses:
                response_text = response.get('text', '').strip()
                if response_text:
                    response_type = MessageClassifier.classify_copilot_response(response_text)
                    if response_type == ResponseType.SETUP_CONFIRMATION:
                        # Parse and save the setup confirmation
                        if parse_and_persist_setup(chat_id, response_text, persist=True, is_from_copilot=True):
                            state_manager.mark_context_restored(chat_id)
                            context_restored = True
                            app.logger.info("Context successfully restored for chat %s", chat_id)
                            break
        
        if not context_restored:
            # Fallback: mark as restored since we have existing settings
            state_manager.mark_context_restored(chat_id)
            app.logger.info("Context restoration fallback for chat %s", chat_id)
    
    # Get conversation details
    state = state_manager.get_conversation_state(chat_id)
    if not state:
        # Create new conversation
        conv_id, token = get_or_create_conversation(chat_id, user_from_id)
        if not conv_id or not token:
            return None, None
        state = state_manager.get_conversation_state(chat_id)
    
    return state.id, state.token


def get_or_create_conversation(chat_id, user_from_id):
    """Get existing conversation or create new one"""
    state = state_manager.get_conversation_state(chat_id)
    
    if state and state.id and state.token:
        app.logger.info("Using existing conversation for chat %s", chat_id)
        return state.id, state.token
    
    # Create new conversation
    app.logger.info("Creating new conversation for chat %s", chat_id)
    conv_id, token = start_direct_line_conversation()
    
    if conv_id and token:
        state_manager.create_conversation_state(
            chat_id, conv_id, token,
            mode=OperationMode.TRANSLATION,
            user_from_id=user_from_id
        )
        return conv_id, token
    
    return None, None


def process_copilot_response(chat_id, activity, user_from_id):
    """Process individual Copilot response with enhanced classification"""
    bot_text = activity.get('text', '').strip()
    if not bot_text:
        return
    
    # Classify the response
    response_type = MessageClassifier.classify_copilot_response(bot_text)
    app.logger.info("Classified response for chat %s as: %s", chat_id, response_type.value)
    
    # Handle based on response type
    if response_type == ResponseType.SETUP_PROMPT:
        # Forward setup prompt to user
        app.logger.info("Forwarding setup prompt to chat %s: '%s'", chat_id, bot_text)
        send_telegram_message(chat_id, bot_text)
        
    elif response_type == ResponseType.SETUP_CONFIRMATION:
        # Process setup completion
        if parse_and_persist_setup(chat_id, bot_text, persist=True, is_from_copilot=True):
            app.logger.info("Setup confirmation processed for chat %s", chat_id)
            state_manager.mark_setup_complete(chat_id)
        
        # Forward confirmation to user
        send_telegram_message(chat_id, bot_text)
        
    elif response_type == ResponseType.TRANSLATION_OUTPUT:
        # Forward translation to user
        app.logger.info("Forwarding translation to chat %s: '%s'", chat_id, bot_text)
        send_telegram_message(chat_id, bot_text)
        
    else:
        # Unknown response type - forward to user (this includes any other responses)
        app.logger.info("Forwarding response to chat %s: '%s'", chat_id, bot_text)
        send_telegram_message(chat_id, bot_text)
    
db.init_db()

def long_poll_for_activity(conv_id, token, user_from_id, start_watermark, chat_id, total_timeout=120.0, interval=1.0):
    """Background poller to catch delayed bot replies arriving after the immediate poll window.

    This will poll activities until a bot response is found or total_timeout expires.
    It updates the conversation watermark when it finds new watermark.
    """
    import time
    try:
        # Mark this poller as active
        active_pollers[chat_id] = True
        
        t0 = time.time()
        nw = start_watermark
        while time.time() - t0 < total_timeout:
            # Check if we should stop polling
            if not active_pollers.get(chat_id, False):
                app.logger.info("Long poller stopping for chat=%s (cancelled)", chat_id)
                break
                
            activities, new_nw = get_copilot_response(conv_id, token, nw, user_from_id=user_from_id)
            if activities:
                # update watermark
                try:
                    state_manager.update_conversation_state(chat_id, watermark=new_nw)
                except Exception:
                    pass
                    
                # forward each activity if not seen before
                for act in activities:
                    act_id = act.get('id')
                    if not act_id:
                        continue
                    if act_id in recent_activity_ids[chat_id]:
                        continue
                    recent_activity_ids[chat_id].append(act_id)

                    # Use enhanced response processing
                    process_copilot_response(chat_id, act, user_from_id)

                app.logger.info("Long-poller обработал %d активностей для чата=%s", len(activities), chat_id)
                break
            nw = new_nw
            time.sleep(interval)
    except Exception as e:
        app.logger.error("Long poller exception for chat=%s: %s", chat_id, e)
    finally:
        # clear polling flags
        active_pollers.pop(chat_id, None)
        try:
            state_manager.update_conversation_state(chat_id, is_polling=False)
        except Exception:
            pass


def start_direct_line_conversation():
    """Начинает новый диалог с ботом Copilot Studio и возвращает токен и ID диалога."""
    headers = {
        'Authorization': f'Bearer {DIRECT_LINE_SECRET}',
    }
    # Создаём новый разговор (conversation) и получаем conversationId (+ возможно token)
    response = requests.post(DIRECT_LINE_ENDPOINT, headers=headers, timeout=10)
    app.logger.info("DirectLine create convo status=%s", response.status_code)
    if response.status_code in (200, 201):
        try:
            data = response.json()
        except Exception:
            data = None
        app.logger.info("DirectLine create keys=%s", list(data.keys()) if isinstance(data, dict) else None)
        # Defensive extraction: docs may return token and conversationId at top-level
        token = data.get('token') or data.get('conversationToken') or None
        conv_id = data.get('conversationId') or data.get('conversation', {}).get('id') or None
        # Avoid printing the full Direct Line response (it may include a token).
        # Log only non-sensitive metadata; if verbose debugging is enabled, log a redacted copy.
        try:
            app.logger.info("Started Direct Line conversation convo=%s keys=%s", conv_id, list(data.keys()) if isinstance(data, dict) else None)
            if DEBUG_VERBOSE and isinstance(data, dict):
                redacted = dict(data)
                if 'token' in redacted:
                    redacted['token'] = '<REDACTED>'
                app.logger.debug("DL create response (redacted): %s", redacted)
        except Exception:
            pass
        # If API did not return a conversation token, fall back to using the secret for server-side calls
        if not token:
            token = DIRECT_LINE_SECRET
            app.logger.warning("No conversation token returned by DL; falling back to DIRECT_LINE_SECRET for auth (server-side).")
        if not conv_id:
            app.logger.warning("conversationId missing in Direct Line response")
            return None, None
        # Return (token, conversationId) - note order expected by callers
        return conv_id, token
    else:
        # avoid logging potentially large bodies without truncation
        body = (response.text or '')[:200]
        app.logger.error("Error starting Direct Line conversation: %s %s", response.status_code, body)
        return None, None

def send_message_to_copilot(conversation_id, token, text, from_id="user"):
    """Отправляет сообщение пользователя в Copilot Studio и возвращает ID активности."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    # Ensure unique from_id for each Telegram user to avoid conversation mixing
    unique_from_id = f"telegram_user_{from_id}"
    payload = {
        "type": "message",
        "from": {"id": unique_from_id, "name": f"TelegramUser{from_id}"},
        "text": text
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        app.logger.info("DirectLine send activity status=%s convo=%s from_id=%s", response.status_code, conversation_id, unique_from_id)
        if response.status_code in (200, 201):
            try:
                j = response.json()
                activity_id = j.get('id')
                if not activity_id:
                    app.logger.warning("DL send response did not contain an activity ID.")
                    return None
                app.logger.debug("DL send successful, activity_id=%s", activity_id)
                return activity_id
            except (json.JSONDecodeError, AttributeError) as e:
                app.logger.error("DL send failed to parse JSON response: %s", e)
                return None
        else:
            app.logger.warning("Message sending error: %s %s", response.status_code, (response.text or '')[:200])
            return None
    except requests.exceptions.RequestException as e:
        app.logger.error("Failed to send message to DirectLine: %s", e)
        return None

def get_copilot_response(conversation_id, token, last_watermark, user_from_id="user"):
    """Return list of bot activities (dicts) not from user and updated watermark."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    if last_watermark:
        url += f"?watermark={last_watermark}"

    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url, headers=headers, timeout=10)
    app.logger.info("DirectLine get activities status=%s convo=%s watermark=%s", response.status_code, conversation_id, last_watermark)
    if response.status_code == 200:
        try:
            data = response.json()
        except Exception:
            data = {}
        activities = data.get('activities', []) if isinstance(data, dict) else []
        
        # Create the expected user ID format
        expected_user_id = f"telegram_user_{user_from_id}"
        
        # Filter activities to only include actual messages from the bot with text content.
        # This avoids processing typing indicators or other non-message events.
        # TEMPORARY DEBUG: Log all activities to see what we're missing
        for act in activities:
            app.logger.info("DEBUG ACTIVITY: type=%s, from_id=%s, text=%s, has_text=%s", 
                          act.get('type'), act.get('from', {}).get('id'), 
                          repr(act.get('text', '')[:100]), bool(act.get('text', '').strip()))
        
        bot_activities = [
            act for act in activities 
            if act.get('type') == 'message' and 
               act.get('from', {}).get('id') != expected_user_id and 
               act.get('text', '').strip()
        ]
        new_watermark = data.get('watermark', last_watermark)
        try:
            # Log a short, non-sensitive summary so operators can see activity volume.
            app.logger.info("DL activities count=%d bot_activities=%d convo=%s user_id=%s", len(activities), len(bot_activities), conversation_id, expected_user_id)
            # Log a small redacted sample when verbose debugging is explicitly enabled.
            if DEBUG_VERBOSE and isinstance(activities, list):
                def _redact_activity(a):
                    if not isinstance(a, dict):
                        return '<non-dict-activity>'
                    ra = {}
                    for k, v in a.items():
                        # redact potentially large or sensitive fields
                        if k in ('channelData', 'attachments', 'entities'):
                            ra[k] = '<REDACTED>'
                        elif k in ('streamUrl', 'token'):
                            ra[k] = '<REDACTED>'
                        elif k == 'text':
                            try:
                                if isinstance(v, str) and len(v) > 200:
                                    ra[k] = v[:200] + '...'
                                else:
                                    ra[k] = v
                            except Exception:
                                ra[k] = '<unreadable-text>'
                        else:
                            ra[k] = v
                    return ra

                redacted_sample = [_redact_activity(a) for a in activities[:3]]
                try:
                    app.logger.debug("DL activities (redacted sample): %s", json.dumps(redacted_sample, ensure_ascii=False, indent=2))
                except Exception:
                    app.logger.debug("DL activities (redacted sample): %s", str(redacted_sample))
        except Exception:
            pass
        return bot_activities, new_watermark
    else:
        body = (response.text or '')[:200]
        app.logger.error("Error fetching Direct Line activities: %s %s", response.status_code, body)
        return [], last_watermark

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Основной обработчик входящих сообщений от Telegram."""
    data = request.get_json()
    if DEBUG_VERBOSE:
        app.logger.debug("Received Telegram webhook: %s", json.dumps(data, indent=2))

    # 1. Извлекаем информацию только из текстовых сообщений
    if 'message' not in data or 'text' not in data['message']:
        app.logger.info("Webhook received a non-text message update. Ignoring.")
        return jsonify(success=True)

    message = data['message']
    chat_id = message['chat']['id']
    user_from_id = message['from']['id']
    chat_type = message['chat'].get('type', 'private')
    text = message.get('text', '').strip()

    if not text:
        return jsonify(success=True)

    # Group chat processing control - configurable behavior
    if chat_type in ['group', 'supergroup']:
        enable_group_processing = os.getenv('ENABLE_GROUP_CHAT_PROCESSING', 'true').lower() == 'true'
        
        if not enable_group_processing:
            # Legacy behavior: Only process commands in groups when disabled
            if not text.startswith('/'):
                app.logger.info("Group chat processing disabled, ignoring non-command message in chat %s", chat_id)
                return jsonify(success=True)
        
        # Optional: Future enhancement for @mention support
        # bot_username = None  # Could get this from getMe API call if needed
        # if bot_username and f'@{bot_username}' in text:
        #     text = text.replace(f'@{bot_username}', '').strip()
        
        app.logger.info("Processing message in group chat %s (type: %s, processing_enabled: %s)", 
                       chat_id, chat_type, enable_group_processing)

    # Fire-and-forget: send 'typing' action to Telegram ~1s after we receive the user's message.
    def _send_typing_after_delay(cid, delay_sec=1.0):
        try:
            time.sleep(delay_sec)
            send_telegram_typing_action(cid)
        except Exception as e:
            app.logger.debug("Typing-thread exception for chat %s: %s", cid, e)

    t = threading.Thread(target=_send_typing_after_delay, args=(chat_id, 1.0))
    t.daemon = True
    t.start()

    app.logger.info("Processing text '%s' for chat_id %s (type: %s, user: %s)", text, chat_id, chat_type, user_from_id)
    last_user_message[chat_id] = text

    # Enhanced message classification
    message_type = MessageClassifier.classify_incoming_message(text)
    app.logger.info("Classified message for chat %s as: %s", chat_id, message_type.value)

    # Handle different message types
    conv_id = None
    token = None
    
    if message_type == MessageType.START_COMMAND:
        conv_id, token = handle_initial_setup(chat_id, user_from_id)
        if conv_id and token:
            # Send 'start' message to trigger setup
            activity_id = send_message_to_copilot(conv_id, token, 'start', from_id=user_from_id)
            if activity_id:
                recent_activity_ids[chat_id].append(activity_id)
        
    elif message_type == MessageType.RESET_COMMAND:
        conv_id, token = handle_reset_setup(chat_id, user_from_id)
        if conv_id and token:
            # Send 'start' message to trigger fresh setup
            activity_id = send_message_to_copilot(conv_id, token, 'start', from_id=user_from_id)
            if activity_id:
                recent_activity_ids[chat_id].append(activity_id)
        
    elif message_type == MessageType.REGULAR_TEXT:
        conv_id, token = handle_translation_request(chat_id, user_from_id, text)
        if conv_id and token:
            # Send the actual message for translation
            activity_id = send_message_to_copilot(conv_id, token, text, from_id=user_from_id)
            if activity_id:
                recent_activity_ids[chat_id].append(activity_id)
    
    else:  # OTHER_COMMAND
        # For other commands, treat as regular text
        conv_id, token = handle_translation_request(chat_id, user_from_id, text)
        if conv_id and token:
            activity_id = send_message_to_copilot(conv_id, token, text, from_id=user_from_id)
            if activity_id:
                recent_activity_ids[chat_id].append(activity_id)

    # Handle connection failures
    if not conv_id or not token:
        error_msg = "Sorry, I couldn't connect to the translation service. Please try again later."
        if chat_type in ['group', 'supergroup']:
            error_msg = "Sorry, I couldn't connect to the translation service. Please try again later."
        else:
            error_msg = "Извините, я не смог подключиться к сервису перевода. Пожалуйста, попробуйте еще раз позже."
        send_telegram_message(chat_id, error_msg)
        return jsonify(success=False)

    # Update conversation state
    state_manager.update_conversation_state(chat_id, last_interaction=time.time())

    # 6. Ожидаем и обрабатываем ответ от Copilot
    time.sleep(1.2)
    
    # Get current conversation state for watermark
    current_state = state_manager.get_conversation_state(chat_id)
    last_watermark = current_state.watermark if current_state else None
    
    bot_responses, new_watermark = get_copilot_response(conv_id, token, last_watermark, user_from_id)
    if new_watermark:
        state_manager.update_conversation_state(chat_id, watermark=new_watermark)

    if not bot_responses:
        app.logger.info("No immediate response from bot for chat %s. Starting long polling.", chat_id)
        current_state = state_manager.get_conversation_state(chat_id)
        if not current_state or not current_state.is_polling:
            state_manager.update_conversation_state(chat_id, is_polling=True)
            poller_thread = threading.Thread(
                target=long_poll_for_activity,
                args=(conv_id, token, user_from_id, new_watermark or last_watermark, chat_id)
            )
            poller_thread.daemon = True
            poller_thread.start()
    else:
        app.logger.info("Received %d immediate responses from bot for chat %s.", len(bot_responses), chat_id)
        for activity in bot_responses:
            activity_id = activity.get('id')
            if activity_id in recent_activity_ids[chat_id]:
                app.logger.warning("Пропуск дубликата ID активности %s для чата %s", activity_id, chat_id)
                continue
            
            recent_activity_ids[chat_id].append(activity_id)
            
            # Use enhanced response processing
            process_copilot_response(chat_id, activity, user_from_id)

    return jsonify(success=True)
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(status="ok", message="alive")


@app.route('/status/github', methods=['GET'])
def github_status():
    """Get comprehensive GitHub repository status via API endpoint."""
    try:
        # Import here to avoid circular imports
        from status_reporter import StatusReporter
        
        # Get optional parameters
        repo_path = request.args.get('path', '.')
        include_github = request.args.get('github', 'true').lower() == 'true'
        format_type = request.args.get('format', 'json').lower()
        
        # Get GitHub token from request header or environment
        github_token = request.headers.get('X-GitHub-Token') or os.getenv('GITHUB_TOKEN')
        
        # Initialize status reporter
        reporter = StatusReporter(repo_path, github_token)
        
        # Generate comprehensive report
        app.logger.info(f"GitHub status check requested for path: {repo_path}")
        result = reporter.generate_comprehensive_report(include_github=include_github)
        
        if not result.success:
            return jsonify({
                'success': False,
                'error': result.error_message,
                'timestamp': datetime.utcnow().isoformat()
            }), 400
        
        # Return different formats based on request
        if format_type == 'summary':
            return jsonify({
                'success': True,
                'summary': reporter.format_status_summary(result),
                'timestamp': datetime.utcnow().isoformat()
            })
        elif format_type == 'table':
            return jsonify({
                'success': True,
                'table': reporter.generate_table_format(result),
                'timestamp': datetime.utcnow().isoformat()
            })
        elif format_type == 'actions':
            actions = reporter.get_action_plan(result)
            return jsonify({
                'success': True,
                'actions': actions,
                'timestamp': datetime.utcnow().isoformat()
            })
        else:  # Default JSON format
            response_data = result.to_dict()
            response_data['timestamp'] = datetime.utcnow().isoformat()
            return jsonify(response_data)
            
    except Exception as e:
        app.logger.error(f"Error in GitHub status endpoint: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500


@app.route('/dump-settings', methods=['GET'])
def dump_settings():
    """Return all rows from ChatSettings for quick inspection."""
    try:
        rows = db.dump_all()
        return jsonify(count=len(rows), rows=rows)
    except Exception as e:
        return jsonify(error=str(e)), 500

def send_telegram_message(chat_id, text, reply_markup: dict = None):
    """Отправляет текстовое сообщение в указанный чат Telegram.

    Optional `reply_markup` is a dict matching Telegram's ReplyKeyboardMarkup
    or InlineKeyboardMarkup structures and will be JSON-encoded when present.
    """
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    if reply_markup is not None:
        try:
            # If caller provided an inline keyboard, first send a ReplyKeyboardRemove
            # to ensure any previously shown full-screen reply keyboard is hidden.
            if isinstance(reply_markup, dict) and 'inline_keyboard' in reply_markup:
                try:
                    remove_payload = {'chat_id': chat_id, 'reply_markup': json.dumps({'remove_keyboard': True})}
                    # best-effort call to remove old reply keyboard
                    remove_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
                    requests.post(remove_url, json=remove_payload, timeout=3)
                except Exception:
                    pass
            payload['reply_markup'] = json.dumps(reply_markup, ensure_ascii=False)
        except Exception:
            # fallback: ignore invalid reply_markup
            app.logger.debug('Invalid reply_markup provided, ignoring')
    # If DEBUG_LOCAL is enabled, don't call Telegram — just print to console for debugging
    if DEBUG_LOCAL:
        app.logger.info("DEBUG_LOCAL enabled — would send to chat %s: %s", chat_id, text)
        # do not print secrets to stdout; keep local fallback in logs only
        app.logger.debug("[LOCAL FALLBACK] chat=%s text=%s", chat_id, text)
        return True

    # Build URL at call time to pick up current TELEGRAM_API_TOKEN
    bot_send_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
    try:
        response = requests.post(bot_send_url, json=payload, timeout=8)
    except Exception as e:
        app.logger.error("Failed to POST to Telegram API for chat=%s: %s", chat_id, e)
        return False

    # Log result; Telegram returns JSON with ok:true/false and description when failed
    try:
        resp_text = response.text
    except Exception:
        resp_text = '<unreadable response>'

    # Detailed diagnostic logging (controlled by env var)
    try:
        if TELEGRAM_LOG_RESPONSES:
            try:
                # Log request payload (safe to include chat_id and truncated text)
                app.logger.debug("Telegram HTTP request for chat=%s payload=%s", chat_id, json.dumps({k: payload[k] for k in ('chat_id','text','reply_markup') if k in payload}, ensure_ascii=False)[:2000])
            except Exception:
                app.logger.debug("Telegram HTTP request (unserializable payload) chat=%s", chat_id)
            app.logger.debug("Telegram HTTP response for chat=%s status=%s body=%s", chat_id, response.status_code, (resp_text or '')[:20000])
    except Exception:
        pass

    if response.status_code == 200:
        try:
            j = response.json()
            if j.get('ok'):
                app.logger.info("Telegram send succeeded chat=%s", chat_id)
                return True
            else:
                app.logger.warning("Telegram API returned ok=false for chat=%s: %s", chat_id, j)
                return False
        except Exception:
            app.logger.info("Telegram send HTTP 200 but failed to parse JSON for chat=%s: %s", chat_id, resp_text)
            return False
    else:
        app.logger.error("Telegram send failed chat=%s status=%s body=%s", chat_id, response.status_code, resp_text[:1000])
        return False


def send_telegram_typing_action(chat_id):
    """Send a `typing` action to Telegram for the given chat_id.

    Best-effort: logs failures and returns boolean.
    """
    if DEBUG_LOCAL:
        app.logger.info("DEBUG_LOCAL enabled — would send 'typing' action to chat %s", chat_id)
        return True

    bot_send_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendChatAction"
    payload = {'chat_id': chat_id, 'action': 'typing'}
    try:
        response = requests.post(bot_send_url, json=payload, timeout=3)
    except Exception as e:
        app.logger.debug("Exception while sending 'typing' action for chat=%s: %s", chat_id, e)
        return False

    try:
        if response.status_code == 200:
            j = response.json()
            if j.get('ok'):
                app.logger.debug("Sent 'typing' action to chat %s", chat_id)
                return True
            else:
                app.logger.debug("Telegram returned ok=false for 'typing' action chat %s: %s", chat_id, j)
                return False
        else:
            app.logger.debug("Non-200 response when sending 'typing' for chat %s: %s %s", chat_id, response.status_code, (response.text or '')[:200])
            return False
    except Exception as e:
        app.logger.debug("Failed to parse Telegram response for 'typing' action chat %s: %s", chat_id, e)
        return False


def send_reply_keyboard_remove(chat_id):
    """Send a ReplyKeyboardRemove to hide any full-screen reply keyboard in Telegram client."""
    rm = {'remove_keyboard': True}
    payload = {'chat_id': chat_id, 'reply_markup': json.dumps(rm)}
    try:
        bot_send_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
        response = requests.post(bot_send_url, json=payload, timeout=5)
    except Exception as e:
        app.logger.debug("Failed to send ReplyKeyboardRemove for chat=%s: %s", chat_id, e)
        return False
    # Extra diagnostic logging when enabled
    try:
        if TELEGRAM_LOG_RESPONSES:
            try:
                app.logger.debug("ReplyKeyboardRemove request payload for chat=%s payload=%s", chat_id, json.dumps(payload, ensure_ascii=False)[:2000])
            except Exception:
                app.logger.debug("ReplyKeyboardRemove request (unserializable) for chat=%s", chat_id)
            try:
                app.logger.debug("ReplyKeyboardRemove response for chat=%s status=%s body=%s", chat_id, response.status_code, response.text[:20000])
            except Exception:
                pass
    except Exception:
        pass
    try:
        j = response.json()
        ok = j.get('ok', False)
    except Exception:
        ok = response.status_code == 200
    if ok:
        app.logger.debug("ReplyKeyboardRemove sent for chat=%s", chat_id)
    else:
        app.logger.debug("ReplyKeyboardRemove failed for chat=%s status=%s body=%s", chat_id, response.status_code, response.text[:200])
    return ok

if __name__ == '__main__':
    # Небольшая проверка переменных окружения — полезно ловить ошибки на старте
    if not TELEGRAM_API_TOKEN:
        app.logger.warning("TELEGRAM_API_TOKEN is not set. Telegram messages will fail.")
    if not DIRECT_LINE_SECRET:
        app.logger.warning("DIRECT_LINE_SECRET is not set. Direct Line calls will fail.")

    # Запуск в production: рекомендуем использовать Waitress на  Windows (простая и надёжная)
    # Установите dependency: pip install waitress
    port = int(os.getenv('PORT', '8080'))
    use_waitress = os.getenv('USE_WAITRESS', '1') == '1'
    if use_waitress:
        try:
            from waitress import serve
            app.logger.info("Starting with Waitress on 0.0.0.0:%s", port)
            # Register bot commands so Telegram clients show slash suggestions (like BotFather)
            try:
                if TELEGRAM_API_TOKEN:
                    cmds_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/setMyCommands"
                    # provide the most common commands the bot supports
                    commands = [
                        {"command": "start", "description": "Start or reconfigure language settings"},
                        {"command": "reset", "description": "Reset language settings"}
                    ]
                    requests.post(cmds_url, json={"commands": commands}, timeout=3)
            except Exception:
                pass
            serve(app, host='0.0.0.0', port=port)
        except Exception as e:
            app.logger.exception("Waitress failed to start, falling back to Flask dev server.")
            app.run(host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port)
