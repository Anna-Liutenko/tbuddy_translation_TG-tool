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

def parse_and_persist_setup(chat_id, text, persist=True):
    """Try to extract language names from Copilot's setup confirmation and persist them.

    This version uses a more precise regex to capture only the language names.
    Returns True if something was parsed, False otherwise.
    """
    try:
        if not isinstance(text, str):
            return False

        # More robust check for final confirmation message
        lowered = text.lower()
        
        # Check for the exact confirmation message format from Copilot Studio
        # Look for various confirmation patterns
        confirmation_patterns = [
            'setup is complete',
            'setup complete',
            'now we speak',
            'thanks! setup is complete',
            'great! i can now translate',
            'perfect! now i can help you with',
            'excellent! i\'m ready to translate',
            'ready for',
            'configuration successful'
        ]
        
        is_setup_complete = any(pattern in lowered for pattern in confirmation_patterns)
        
        if not is_setup_complete:
            return False

        # Extract languages using multiple patterns
        lang_string = None
        
        # Pattern 1: "Now we speak English, Russian, Japanese"
        match = re.search(r'now we speak\s+([^.\n!?]+)', text, re.IGNORECASE)
        if match:
            lang_string = match.group(1).strip()
        
        # Pattern 2: "translate between English, Russian, Japanese"
        if not lang_string:
            match = re.search(r'translate\s+(?:between\s+)?([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 3: "help you with English, French"
        if not lang_string:
            match = re.search(r'help you with\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 4: "ready to translate English, German, Spanish"
        if not lang_string:
            match = re.search(r'ready to translate\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 5: "Ready for English, Spanish, Portuguese translation"
        if not lang_string:
            match = re.search(r'ready for\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)\s+translation', text, re.IGNORECASE)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 6: "Setup complete! Ready for [languages]"
        if not lang_string:
            match = re.search(r'setup complete.*?ready for\s+([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)*)', text, re.IGNORECASE | re.DOTALL)
            if match:
                lang_string = match.group(1).strip()
        
        # Pattern 7: Look for language list after confirmation words (more flexible)
        if not lang_string:
            # Look for pattern after confirmation keywords
            confirmation_match = re.search(r'(setup is complete|setup complete|thanks!|great!|perfect!|excellent!|ready for).*?([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)', text, re.IGNORECASE | re.DOTALL)
            if confirmation_match:
                lang_string = confirmation_match.group(2).strip()
        
        # Pattern 8: Look for any sequence of capitalized words separated by commas
        if not lang_string:
            lang_match = re.search(r'\b([A-Z][a-z]+(?:,\s*[A-Z][a-z]+)+)\b', text)
            if lang_match:
                potential_langs = lang_match.group(1)
                # Verify these look like language names (not random capitalized words)
                words = [w.strip() for w in potential_langs.split(',')]
                if not any(word.lower() in ['send', 'your', 'message', 'text', 'thanks', 'great', 'now', 'can', 'help', 'ready'] 
                          for word in words):
                    lang_string = potential_langs
        
        if not lang_string:
            app.logger.warning("Could not extract language names from setup confirmation: %s", text)
            return False
        
        # Clean up the string
        lang_string = re.sub(r'[.!?].*$', '', lang_string).strip()  # Remove trailing punctuation and text
        lang_string = lang_string.strip('.,:; ')
        
        if not lang_string:
            return False

        # For cases like "No languages are mentioned..." - don't save
        if 'no languages' in lang_string.lower():
            app.logger.warning("Copilot reported no languages for chat %s: %s", chat_id, lang_string)
            return False

        # Split by common delimiters
        parts = re.split(r'[,;]|\s+and\s+', lang_string)
        names = [p.strip().strip('.,:; ') for p in parts if p and p.strip() and len(p.strip()) > 1]

        if not names:
            app.logger.warning("Could not extract language names from: %s", lang_string)
            return False

        # Filter out common non-language words
        language_names = []
        excluded_words = {'send', 'your', 'message', 'text', 'now', 'can', 'help', 'ready', 'translate', 'between', 'with'}
        for name in names:
            clean_name = name.strip()
            if len(clean_name) > 1 and clean_name.lower() not in excluded_words:
                language_names.append(clean_name)
        
        if not language_names:
            app.logger.warning("No valid language names found after filtering: %s", names)
            return False

        lang_names = ', '.join(language_names)
        
        if persist:
            app.logger.info("SUCCESS: Parsed and persisting language names for chat %s: [%s]", chat_id, lang_names)
            db.upsert_chat_settings(chat_id, '', lang_names, datetime.utcnow().isoformat())
            # Mark setup as complete in conversation state
            if chat_id in conversations:
                conversations[chat_id]['setup_complete'] = True
        
        return True # Return True if parsing was successful
    except Exception as e:
        app.logger.error("Error in parse_and_persist_setup for chat %s: %s", chat_id, e, exc_info=True)
        return False
    
db.init_db()

def long_poll_for_activity(conv_id, token, user_from_id, start_watermark, chat_id, total_timeout=120.0, interval=1.0):
    """Background poller to catch delayed bot replies arriving after the immediate poll window.

    This will poll activities until a bot response is found or total_timeout expires.
    It updates the conversations[chat_id]['watermark'] when it finds new watermark.
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
                    conversations[chat_id]['watermark'] = new_nw
                except Exception:
                    pass
                # forward each activity if not seen before
                for act in activities:
                    act_id = act.get('id')
                    text = act.get('text', '').strip()
                    if not act_id or not text:
                        continue
                    if act_id in recent_activity_ids[chat_id]:
                        continue
                    recent_activity_ids[chat_id].append(act_id)

                    # Пытаемся извлечь и сохранить настройки, если это сообщение-подтверждение.
                    if parse_and_persist_setup(chat_id, text, persist=True):
                        app.logger.info("Распознано и сохранено подтверждение настройки (long-poll) для чата %s.", chat_id)

                    # Всегда пересылаем оригинальное сообщение от бота пользователю.
                    app.logger.info("Пересылка сообщения бота в чат (long-poll) %s: '%s'", chat_id, text)
                    send_telegram_message(chat_id, text)

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
            if chat_id in conversations:
                conversations[chat_id]['is_polling'] = False
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
            app.logger.warning("Ошибка отправки сообщения: %s %s", response.status_code, (response.text or '')[:200])
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

    # For group chats, only respond to messages that start with bot commands or mention the bot
    if chat_type in ['group', 'supergroup']:
        # Get bot info to check for mentions
        bot_username = None  # We could get this from getMe API call if needed
        
        # Only process if it's a command or if the bot is mentioned
        if not (text.startswith('/') or (bot_username and f'@{bot_username}' in text)):
            # In groups, ignore regular messages unless they're commands
            app.logger.info("Ignoring non-command message in group chat %s", chat_id)
            return jsonify(success=True)
        
        # Remove bot mention if present
        if bot_username and f'@{bot_username}' in text:
            text = text.replace(f'@{bot_username}', '').strip()

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

    # 2. Обработка команды /reset
    if text == '/reset':
        app.logger.info("Processing /reset for chat %s. Clearing all state.", chat_id)
        
        # Stop any active long polling for this chat
        active_pollers[chat_id] = False
        
        try:
            db.delete_chat_settings(chat_id)
            app.logger.info("Deleted DB settings for chat %s", chat_id)
        except Exception as e:
            app.logger.error("Error deleting DB settings for chat %s: %s", chat_id, e, exc_info=True)
        
        # Очищаем состояние в памяти
        conversations.pop(chat_id, None)
        last_user_message.pop(chat_id, None)
        if chat_id in recent_activity_ids:
            del recent_activity_ids[chat_id]
        app.logger.info("Cleared in-memory state for chat %s", chat_id)
        
        # Запускаем логику настройки, как при /start
        text = 'start'

    # 3. Обработка команды /start
    if text == '/start':
        text = 'start' # Убедимся, что текст именно 'start'
        if chat_id in conversations:
            app.logger.info("Clearing stale in-memory conversation for chat %s due to /start", chat_id)
            # Stop any active long polling for this chat
            active_pollers[chat_id] = False
            conversations.pop(chat_id, None)

    # 4. Получаем или создаем диалог с Copilot Studio
    need_new_conversation = False
    if chat_id not in conversations:
        need_new_conversation = True
        app.logger.info("No active conversation for chat %s. Starting a new one.", chat_id)
    else:
        # Check if existing conversation is still valid by trying to use it
        # If the token expired, we'll create a new one when send fails
        app.logger.info("Using existing conversation for chat %s", chat_id)
    
    if need_new_conversation:
        # Stop any leftover long polling for this chat
        active_pollers[chat_id] = False
        
        conv_id, token = start_direct_line_conversation()
        if conv_id and token:
            conversations[chat_id] = {
                'id': conv_id,
                'token': token,
                'watermark': None,
                'last_interaction': time.time(),
                'is_polling': False,
                'setup_complete': False  # Track setup completion state
            }
            app.logger.info("Started new DirectLine conversation for chat %s: %s", chat_id, conv_id)
            
            # Check if user has existing language settings
            try:
                existing_settings = db.get_chat_settings(chat_id)
                if existing_settings and existing_settings.get('language_names') and text != 'start':
                    app.logger.info("Found existing language settings for chat %s: %s. Sending quick setup.", 
                                  chat_id, existing_settings.get('language_names'))
                    # Send a simplified setup message to initialize the conversation
                    saved_languages = existing_settings.get('language_names', '')
                    if saved_languages:
                        setup_message = f"My languages are: {saved_languages}"
                        app.logger.info("Sending quick setup to new conversation for chat %s: %s", chat_id, setup_message)
                        setup_activity_id = send_message_to_copilot(conv_id, token, setup_message, from_id=user_from_id)
                        if setup_activity_id:
                            recent_activity_ids[chat_id].append(setup_activity_id)
                        # Mark setup as complete since we have existing settings
                        conversations[chat_id]['setup_complete'] = True
                        # Give time for Copilot to process setup
                        time.sleep(1.5)
            except Exception as e:
                app.logger.error("Error checking existing settings for chat %s: %s", chat_id, e, exc_info=True)
        else:
            app.logger.error("Failed to start DirectLine conversation for chat %s.", chat_id)
            error_msg = "Извините, я не смог подключиться к сервису перевода. Пожалуйста, попробуйте еще раз позже."
            if chat_type in ['group', 'supergroup']:
                error_msg = "Sorry, I couldn't connect to the translation service. Please try again later."
            send_telegram_message(chat_id, error_msg)
            return jsonify(success=False)
    
    # 5. Отправляем сообщение в Copilot и получаем ответ
    conv_id = conversations[chat_id]['id']
    token = conversations[chat_id]['token']
    last_watermark = conversations[chat_id]['watermark']
    conversations[chat_id]['last_interaction'] = time.time()

    activity_id = send_message_to_copilot(conv_id, token, text, from_id=user_from_id)
    if activity_id:
        recent_activity_ids[chat_id].append(activity_id)
    else:
        app.logger.warning("Не удалось отправить сообщение для чата %s. Предполагаем, что токен истек, начинаем новый разговор.", chat_id)
        # Clear the conversation and try to create a new one
        conversations.pop(chat_id, None)
        # Attempt to retry with a new conversation
        app.logger.info("Attempting to create new conversation after token failure for chat %s", chat_id)
        
        conv_id, token = start_direct_line_conversation()
        if conv_id and token:
            conversations[chat_id] = {
                'id': conv_id,
                'token': token,
                'watermark': None,
                'last_interaction': time.time(),
                'is_polling': False,
                'setup_complete': False
            }
            
            # For existing users, send quick setup again
            try:
                existing_settings = db.get_chat_settings(chat_id)
                if existing_settings and existing_settings.get('language_names'):
                    saved_languages = existing_settings.get('language_names', '')
                    if saved_languages:
                        setup_message = f"My languages are: {saved_languages}"
                        setup_activity_id = send_message_to_copilot(conv_id, token, setup_message, from_id=user_from_id)
                        if setup_activity_id:
                            recent_activity_ids[chat_id].append(setup_activity_id)
                        conversations[chat_id]['setup_complete'] = True
                        time.sleep(1.0)
            except Exception as e:
                app.logger.error("Error in retry setup for chat %s: %s", chat_id, e)
            
            # Retry sending the original message
            activity_id = send_message_to_copilot(conv_id, token, text, from_id=user_from_id)
            if activity_id:
                recent_activity_ids[chat_id].append(activity_id)
            else:
                error_msg = "Произошла ошибка соединения. Пожалуйста, отправьте свое сообщение еще раз."
                if chat_type in ['group', 'supergroup']:
                    error_msg = "Connection error occurred. Please resend your message."
                send_telegram_message(chat_id, error_msg)
                return jsonify(success=True)
        else:
            error_msg = "Произошла ошибка соединения. Пожалуйста, отправьте свое сообщение еще раз."
            if chat_type in ['group', 'supergroup']:
                error_msg = "Connection error occurred. Please resend your message."
            send_telegram_message(chat_id, error_msg)
            return jsonify(success=True)

    # 6. Ожидаем и обрабатываем ответ от Copilot
    time.sleep(1.2)
    
    bot_responses, new_watermark = get_copilot_response(conv_id, token, last_watermark, user_from_id)
    if new_watermark:
        conversations[chat_id]['watermark'] = new_watermark

    if not bot_responses:
        app.logger.info("Нет немедленного ответа от бота для чата %s. Запускаем долгий опрос.", chat_id)
        if not conversations[chat_id].get('is_polling'):
            conversations[chat_id]['is_polling'] = True
            poller_thread = threading.Thread(
                target=long_poll_for_activity,
                args=(conv_id, token, user_from_id, new_watermark or last_watermark, chat_id)
            )
            poller_thread.daemon = True
            poller_thread.start()
    else:
        app.logger.info("Получено %d немедленных ответов от бота для чата %s.", len(bot_responses), chat_id)
        for activity in bot_responses:
            activity_id = activity.get('id')
            if activity_id in recent_activity_ids[chat_id]:
                app.logger.warning("Пропуск дубликата ID активности %s для чата %s", activity_id, chat_id)
                continue
            
            recent_activity_ids[chat_id].append(activity_id)
            bot_text = activity.get('text', '').strip()
            if not bot_text:
                continue

            # Пытаемся извлечь и сохранить настройки, если это сообщение-подтверждение.
            if parse_and_persist_setup(chat_id, bot_text, persist=True):
                app.logger.info("Распознано и сохранено подтверждение настройки (из немедленного ответа) для чата %s.", chat_id)

            # Всегда пересылаем оригинальное сообщение от бота пользователю.
            app.logger.info("Пересылка сообщения бота в чат %s: '%s'", chat_id, bot_text)
            send_telegram_message(chat_id, bot_text)

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
