import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import db
from collections import deque, defaultdict
from datetime import datetime
import re
import json
import logging
from logging.handlers import RotatingFileHandler
import sys

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
# store last user message per chat as a simple fallback
last_user_message = {}

# Recent activity ids per chat to avoid duplicate forwards (keeps last 100 IDs)
recent_activity_ids = defaultdict(lambda: deque(maxlen=100))

# Simple SQLite DB to persist chat settings when Copilot confirms setup
DB_PATH = os.path.join(os.path.dirname(__file__), 'chat_settings.db')

# DB abstraction: use db.py for all ChatSettings access
# NOTE: db.py currently uses SQLite and will raise NotImplementedError
# if DATABASE_URL is set. This centralizes DB access for easier future migration.


def parse_and_persist_setup(chat_id, text):
    """Try to extract language names from Copilot's setup confirmation and persist them.

    Returns True if something was parsed and persisted, False otherwise.
    """
    try:
        if not isinstance(text, str):
            return False

        # Guard against parsing translation blocks
        if '\n' in text or text.count(':') >= 2:
            if re.search(r'^[a-z]{2,3}:', text, re.MULTILINE):
                app.logger.info("Skipping parse for chat %s: looks like a translation block.", chat_id)
                return False

        lowered = text.lower()
        # Ignore messages that clearly indicate failure or are not setup-related.
        negative_markers = [
            'no languages mentioned', 'no languages are mentioned', 'no language was specified',
            'i can only translate', 'sorry', 'unfortunately', 'error'
        ]
        if any(marker in lowered for marker in negative_markers):
            app.logger.info("Ignoring negative/non-setup text for chat %s: %s", chat_id, text[:120])
            return False

        # More robust language extraction
        s = text
        # Remove instructional prefixes
        s = re.sub(r'^(write|specify|enter|please write|please specify)\s*\d*\s*languages?:\s*', '', s, flags=re.IGNORECASE).strip()
        # Remove confirmation prefixes
        s = re.sub(r'^(setup is complete\.|thanks!|great!)\s*', '', s, flags=re.IGNORECASE).strip()
        s = re.sub(r'^now we speak\s*', '', s, flags=re.IGNORECASE).strip()
        # Remove instructional suffixes
        s = re.sub(r'\.\s*send your message.*$', '', s, flags=re.IGNORECASE).strip()

        if not s:
            return False

        # Split by common delimiters
        parts = re.split(r'[,;]| and | or ', s)
        names = [p.strip().strip('.,:; ') for p in parts if p and p.strip() and len(p.strip()) > 1]

        if len(names) < 2:
            app.logger.info("Did not find at least 2 valid language names in text for chat %s: %s", chat_id, text[:120])
            return False

        lang_names = ', '.join(names)
        app.logger.info("SUCCESS: Parsed and persisting language names for chat %s: [%s]", chat_id, lang_names)
        db.upsert_chat_settings(chat_id, '', lang_names, datetime.utcnow().isoformat())
        return True
    except Exception as e:
        app.logger.error("Error in parse_and_persist_setup for chat %s: %s", chat_id, e, exc_info=True)
        return False


def is_language_question(text):
    """Return True if the bot text looks like a question asking the user to provide languages."""
    try:
        if not text or not isinstance(text, str):
            return False
        lw = text.lower()
        # must mention 'language' or 'languages'
        if 'language' not in lw and 'languages' not in lw:
            return False
        triggers = ['what', "what's", 'which', 'prefer', 'write', 'specify', 'please', 'put']
        if any(t in lw for t in triggers):
            return True
        # explicit prompt forms
        if 'write 2' in lw or '2 or 3' in lw or 'write 3' in lw:
            return True
        return False
    except Exception:
        return False


def should_skip_forwarding(text):
    """Return True if the given Copilot text should NOT be forwarded to the Telegram user.

    This is a crucial function to prevent the bot from asking redundant questions
    or sending confusing, intermediate messages from the Copilot backend.
    """
    try:
        if not text or not isinstance(text, str):
            return False
        
        lw = text.lower()

        # Condition 1: Skip explicit questions about languages.
        # This is the most important rule to prevent the "double question" loop.
        if is_language_question(text):
            app.logger.info("SKIP: Text is a language question: '%s'", text)
            return True

        # Condition 2: Skip short, instructional phrases that are part of the setup flow.
        # These are often redundant or confusing when the user has already provided input.
        instructional_phrases = [
            'write 2 or 3 languages', 'write 2 languages', 'specify the languages',
            'please provide the languages', 'send your message and i\'ll translate it'
        ]
        if any(phrase in lw for phrase in instructional_phrases):
            app.logger.info("SKIP: Text contains a setup instruction: '%s'", text)
            return True
            
        # Condition 3: Skip the specific, confusing confirmation message that was causing issues.
        if 'setup is complete' in lw and 'now we speak' in lw:
            app.logger.info("SKIP: Text is the confusing 'setup is complete' message: '%s'", text)
            return True

        app.logger.debug("FORWARD: Text does not meet skip conditions: '%s'", text)
        return False
    except Exception as e:
        app.logger.error("Error in should_skip_forwarding: %s", e, exc_info=True)
        return False

db.init_db()

def long_poll_for_activity(conv_id, token, user_from_id, start_watermark, chat_id, total_timeout=120.0, interval=1.0):
    """Background poller to catch delayed bot replies arriving after the immediate poll window.

    This will poll activities until a bot response is found or total_timeout expires.
    It updates the conversations[chat_id]['watermark'] when it finds new watermark.
    """
    import time
    try:
        t0 = time.time()
        nw = start_watermark
        while time.time() - t0 < total_timeout:
            activities, new_nw = get_copilot_response(conv_id, token, nw, user_from_id=user_from_id)
            if activities:
                # update watermark
                try:
                    conversations[chat_id]['watermark'] = new_nw
                except Exception:
                    pass
                # forward each activity if not seen before
                # Avoid forwarding raw setup confirmations from Copilot; send one canonical
                # confirmation message when parsing/persisting succeeds.
                sent_setup_confirmation = False
                for act in activities:
                    act_id = act.get('id')
                    text = act.get('text')
                    if not act_id or not text:
                        continue
                    if act_id in recent_activity_ids[chat_id]:
                        continue
                    recent_activity_ids[chat_id].append(act_id)
                    # If this Copilot activity is a language-question or short guidance,
                    # skip it entirely (don't try to parse or forward) to avoid duplicates.
                    try:
                        if should_skip_forwarding(text):
                            app.logger.info("Skipping Copilot guidance/question (pre-parse) for chat %s: %s", chat_id, text[:140])
                            continue
                    except Exception:
                        pass

                    parsed = False
                    try:
                        parsed = parse_and_persist_setup(chat_id, text)
                    except Exception:
                        parsed = False
                    if parsed:
                        try:
                            if not sent_setup_confirmation:
                                # remove any lingering reply keyboard first
                                try:
                                    send_reply_keyboard_remove(chat_id)
                                except Exception:
                                    pass
                                send_telegram_message(chat_id, "Language settings saved. You can now send messages for translation.")
                                sent_setup_confirmation = True
                        except Exception:
                            pass
                        continue
                    # Avoid forwarding Copilot prompts that are asking the user to provide languages
                    try:
                        if should_skip_forwarding(text):
                            app.logger.info("Skipping forwarding Copilot language-question/notice for chat %s: %s", chat_id, text[:140])
                            continue
                    except Exception:
                        pass
                    try:
                        send_telegram_message(chat_id, text)
                    except Exception:
                        pass
                app.logger.info("Long-poller forwarded %d activities for chat=%s", len(activities), chat_id)
                break
            nw = new_nw
            time.sleep(interval)
    except Exception as e:
        app.logger.error("Long poller exception for chat=%s: %s", chat_id, e)
    finally:
        # clear polling flag
        try:
            conversations[chat_id]['polling'] = False
        except Exception:
            pass


def get_main_menu_markup():
    """Return an InlineKeyboardMarkup dict with a single compact 'Меню' button.

    Inline buttons are smaller and attached to the message (not full-screen),
    which matches the desired "small button on the side" UX.
    The button uses callback_data 'menu' which we handle in the webhook.
    """
    # keep definition for backward compatibility but keep UI-minimal — callers should
    # avoid attaching this markup; we will not send it by default anymore.
    return {'inline_keyboard': [[{'text': 'Меню', 'callback_data': 'menu'}]]}

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
        return token, conv_id
    else:
        # avoid logging potentially large bodies without truncation
        body = (response.text or '')[:200]
        app.logger.error("Error starting Direct Line conversation: %s %s", response.status_code, body)
        return None, None

def send_message_to_copilot(conversation_id, token, text, from_id="user"):
    """Отправляет сообщение пользователя в Copilot Studio."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        "type": "message",
    # Use a per-telegram-user from.id so BotFramework can distinguish users
    "from": {"id": str(from_id)},
        "text": text
    }
    response = requests.post(url, headers=headers, json=payload, timeout=10)
    # Direct Line may return 200 or 201 on activity post
    app.logger.info("DirectLine send activity status=%s convo=%s", response.status_code, conversation_id)
    if response.status_code in (200, 201):
        try:
            j = response.json()
            app.logger.debug("DL send keys=%s", list(j.keys()) if isinstance(j, dict) else None)
        except Exception:
            app.logger.debug("DL send: no json body")
    else:
        app.logger.warning("Ошибка отправки сообщения: %s %s", response.status_code, (response.text or '')[:200])

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
        # Filter activities that are not from the Telegram user and have text
        bot_activities = [act for act in activities if act.get('from', {}).get('id') != str(user_from_id) and act.get('text')]
        new_watermark = data.get('watermark', last_watermark)
        try:
            # Log a short, non-sensitive summary so operators can see activity volume.
            app.logger.info("DL activities count=%d convo=%s", len(activities), conversation_id)
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
    """Эта функция вызывается, когда Telegram присылает новое сообщение.

    Обрабатываем входящую активность в фоне (thread) и возвращаем 200 сразу.
    Это уменьшает вероятность 502/504 от reverse-proxy или провайдера из-за долгой обработки.
    """
    update = request.get_json(silent=True)

    def process_update(update_obj):
        try:
            if not update_obj:
                app.logger.warning("Empty update_obj in background worker")
                return

            # Handle inline button callbacks (callback_query) such as the compact 'Меню' button
            if 'callback_query' in update_obj:
                cq = update_obj['callback_query']
                data = cq.get('data')
                cq_id = cq.get('id')
                # Determine chat id: prefer the message.chat.id if present, else fall back to from.id
                chat_id = None
                try:
                    if cq.get('message') and cq['message'].get('chat'):
                        chat_id = cq['message']['chat']['id']
                except Exception:
                    chat_id = None
                if not chat_id:
                    chat_id = cq.get('from', {}).get('id')

                # Acknowledge the callback quickly so the client stops showing the loading state
                try:
                    answer_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/answerCallbackQuery"
                    requests.post(answer_url, json={'callback_query_id': cq_id, 'text': 'Opening menu...', 'show_alert': False}, timeout=3)
                except Exception:
                    pass

                if data == 'menu' and chat_id:
                    try:
                        help_text = (
                            "Меню:\n"
                            "/reset — Сбросить настройки языка\n"
                            "Отправьте 2 или 3 языка (например: русский, английский) чтобы начать перевод."
                        )
                        send_telegram_message(chat_id, help_text)
                    except Exception:
                        pass
                return

            if "message" in update_obj and "text" in update_obj["message"]:
                chat_id = update_obj["message"]["chat"]["id"]
                user_message = update_obj["message"]["text"]

                # Handle the /reset command (accept '/reset' and '/reset@botname')
                if re.match(r'^/reset(\@\S+)?\s*$', user_message.strip(), flags=re.IGNORECASE):
                    try:
                        app.logger.info(f"COMMAND /reset received for chat_id: {chat_id}. Deleting settings.")
                        # Delete from DB
                        db.delete_chat_settings(chat_id)
                        # Delete in-memory conversation state to force a new Direct Line session
                        if chat_id in conversations:
                            del conversations[chat_id]
                        app.logger.info(f"SUCCESS: Reset chat settings and conversation for chat_id: {chat_id}")
                        # Send a clean, direct prompt for languages.
                        send_telegram_message(chat_id, "Language settings have been reset. Please specify 2 or 3 languages to begin (e.g., English, Russian, Polish).")
                    except Exception as e:
                        app.logger.error(f"Error during /reset for chat_id {chat_id}: {e}", exc_info=True)
                        send_telegram_message(chat_id, "Sorry, there was an error trying to reset the settings.")
                    return # Stop processing this message further

                # persist last user message for fallback parsing later
                try:
                    last_user_message[chat_id] = user_message
                except Exception:
                    pass
                app.logger.info(f"[worker] Received message from {chat_id}: {user_message}")

                # Проверяем, есть ли уже активный диалог для этого чата
                if chat_id not in conversations:
                    token, conv_id = start_direct_line_conversation()
                    # Require both a usable auth token and a conversation id. If either is missing,
                    # do not create a conversations entry to avoid downstream errors when sending
                    # or polling activities.
                    if not token or not conv_id:
                        app.logger.error("Could not start Direct Line conversation for chat %s - token=%s conv_id=%s", chat_id, bool(token), bool(conv_id))
                        return
                    # create a per-chat from_id so DL user activities are tied to this Telegram chat
                    from_id = f"telegram_{chat_id}"
                    conversations[chat_id] = {"conv_id": conv_id, "token": token, "watermark": None, "from_id": from_id}

                session = conversations[chat_id]

                # 1. Отправляем сообщение пользователя в Copilot
                import time
                start_ts = time.time()

                # 1. Отправляем сообщение пользователя в Copilot
                send_message_to_copilot(session['conv_id'], session['token'], user_message, from_id=session.get('from_id', str(chat_id)))

                # 2. Let the user know we're processing (typing...) — non-blocking
                try:
                    typing_url = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendChatAction"
                    requests.post(typing_url, data={'chat_id': chat_id, 'action': 'typing'}, timeout=2)
                except Exception:
                    pass

                # 3. Poll activities with a short timeout loop to reduce latency.
                # Try frequently for up to POLL_TIMEOUT seconds before giving up.
                POLL_TIMEOUT = 12.0
                POLL_INTERVAL = 0.5
                elapsed = 0.0
                bot_response = None
                new_watermark = session.get('watermark')
                # We may receive multiple activities (guidance + confirmation). Process each safely.
                setup_confirmed_sent = False
                while elapsed < POLL_TIMEOUT:
                    activities, nw = get_copilot_response(session['conv_id'], session['token'], new_watermark, user_from_id=session.get('from_id', str(chat_id)))
                    if activities:
                        try:
                            for act in activities:
                                # Normalize activity
                                act_id = act.get('id')
                                text = act.get('text') if isinstance(act.get('text'), str) else None
                                if not act_id or not text:
                                    continue

                                # Deduplicate
                                if act_id in recent_activity_ids[chat_id]:
                                    continue
                                recent_activity_ids[chat_id].append(act_id)

                                # Skip known noisy/setup guidance messages
                                try:
                                    if should_skip_forwarding(text):
                                        app.logger.info("Skipping Copilot guidance/question (pre-parse) for chat %s: %s", chat_id, text[:140])
                                        continue
                                except Exception:
                                    pass

                                # Try to parse and persist setup confirmation
                                parsed = False
                                try:
                                    parsed = parse_and_persist_setup(chat_id, text)
                                except Exception:
                                    parsed = False

                                if parsed:
                                    # Send a single canonical confirmation message
                                    try:
                                        if not setup_confirmed_sent:
                                            try:
                                                send_reply_keyboard_remove(chat_id)
                                            except Exception:
                                                pass
                                            send_telegram_message(chat_id, "Language settings saved. You can now send messages for translation.")
                                            setup_confirmed_sent = True
                                    except Exception:
                                        pass
                                    # Do not forward the original Copilot confirmation
                                    continue

                                # Forward regular bot text to the Telegram user
                                try:
                                    app.logger.info("Forwarding regular message to chat %s", chat_id)
                                    send_telegram_message(chat_id, text)
                                    bot_response = True
                                except Exception:
                                    pass
                        except Exception as e:
                            app.logger.error("Error while processing activities for chat %s: %s", chat_id, e, exc_info=True)

                        # Advance watermark to the newest seen
                        new_watermark = nw

                    # Wait a short interval and continue polling until timeout to catch late activities
                    time.sleep(POLL_INTERVAL)
                    elapsed = time.time() - start_ts

                # update stored watermark even if no response
                conversations[chat_id]['watermark'] = new_watermark

                duration = time.time() - start_ts
                app.logger.info(f"Processed message for chat={chat_id} duration={duration:.2f}s found_response={bool(bot_response)}")

                # 4. Ответ(ы) уже были отправлены в Telegram выше when iterating activities.
                # Avoid sending a boolean or duplicate message here (was sending 'True').
                if not bot_response:
                    # optional: send a short fallback so user isn't left waiting silently
                    try:
                        send_telegram_message(chat_id, "I'm processing your request and will reply shortly...")
                    except Exception:
                        pass
                    # start a background long-poller to catch delayed bot replies (if not already polling)
                    try:
                        if not conversations[chat_id].get('polling'):
                            conversations[chat_id]['polling'] = True
                            import threading as _threading
                            lp = _threading.Thread(target=long_poll_for_activity, args=(session['conv_id'], session['token'], session.get('from_id', str(chat_id)), new_watermark, chat_id))
                            lp.daemon = True
                            lp.start()
                    except Exception:
                        pass
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            app.logger.error("Exception in background worker: %s\n%s", e, tb)

    # Запускаем обработку в фоновом потоке и возвращаем 200 немедленно
    try:
        import threading
        worker = threading.Thread(target=process_update, args=(update,))
        worker.daemon = True
        worker.start()
    except Exception as e:
        app.logger.error("Failed to start background worker: %s", e)

    # Возвращаем ответ Telegram сразу, чтобы избежать таймаутов и 502/504
    return jsonify(status="ok")


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify(status="ok", message="alive")


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

    # Запуск в production: рекомендуем использовать Waitress на Windows (простая и надёжная)
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
