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

# Загружаем переменные из файла .env
load_dotenv()

# --- НАСТРОЙКИ: загружаются из файла .env ---
# 1. Токен вашего Telegram бота от @BotFather
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")

# 2. Секрет вашего бота из Copilot Studio (Settings -> Channels -> Direct Line)
DIRECT_LINE_SECRET = os.getenv("DIRECT_LINE_SECRET")

# 3. URL для получения токена Direct Line.
DIRECT_LINE_ENDPOINT = "https://directline.botframework.com/v3/directline/conversations"

# URL для отправки сообщений в Telegram
TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_API_TOKEN}/sendMessage"
# ---------------------------------------------
# Local debug fallback: when DEBUG_LOCAL=1, messages will be printed to console
DEBUG_LOCAL = os.getenv('DEBUG_LOCAL', '0') == '1'
DEBUG_VERBOSE = os.getenv('DEBUG_VERBOSE', '0') == '1'

# Инициализация веб-сервера Flask
app = Flask(__name__)
# Ensure app logger prints INFO/DEBUG to console
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

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

        # Guard: if text looks like a translation block (e.g. "ru: Доброе утро!\nja: ...")
        # avoid parsing these as language names. Common signs: multiple lines and
        # lines starting with short language codes followed by ':' or multiple ':' occurrences.
        try:
            if '\n' in text or text.count(':') >= 1:
                lines = [l.strip() for l in text.splitlines() if l.strip()]
                short_code_line = False
                for ln in lines:
                    # matches patterns like 'ru: ...' or 'en: Hello' or 'ja: おはよう'
                    if re.match(r'^[A-Za-z]{2,3}\s*:', ln):
                        short_code_line = True
                        break
                if short_code_line and len(lines) >= 1:
                    app.logger.info("Skipping parse: looks like translation block for chat %s: %s", chat_id, text[:120])
                    return False
        except Exception:
            # if detection fails, continue to normal parsing
            pass

        lowered = text.lower()
        # Ignore clear negative/fallback messages that indicate parsing failed
        negative_markers = [
            'no languages', 'no language', 'no languages are', 'no languages mentioned',
            'no languages are mentioned', 'nothing', 'none'
        ]
        for nm in negative_markers:
            if nm in lowered:
                app.logger.info("Ignoring negative setup text for chat %s: %s", chat_id, text)
                return False

        def extract_language_names_from_text(t):
            """Try to extract a list of language names from a free text string.

            Returns a list of cleaned names (may be empty).
            """
            if not t or not isinstance(t, str):
                return []
            s = t.strip()
            # Remove common trailing sentences
            for sep in ['Send your message and', 'Send your message', '\n']:
                if sep in s:
                    s = s.split(sep, 1)[0]
            s = s.strip().strip('.,;: ')
            if not s:
                return []

            # Prefer comma or 'and' separated lists
            if ',' in s or '\band\b' in s:
                parts = re.split(r',|\band\b', s)
            else:
                # fallback: split by slash or semicolon
                if '/' in s:
                    parts = s.split('/')
                elif ';' in s:
                    parts = s.split(';')
                else:
                    # last resort: split by spaces but only accept if looks like a short list
                    tokens = s.split()
                    # if there are multiple tokens and not a long sentence, treat each token as a language
                    if 1 < len(tokens) <= 6:
                        parts = tokens
                    else:
                        return []

            cleaned = [p.strip().strip('.,;: ') for p in parts if p and p.strip()]
            valid = []
            for n in cleaned:
                ln = n.lower()
                if any(x in ln for x in ['no ', 'none', 'nothing', 'not']):
                    continue
                # require at least one alphabetic character (Latin or Cyrillic)
                if re.search(r'[A-Za-zА-Яа-я]', n):
                    valid.append(n)
            return valid

        # 1) Try to parse the canonical confirmation text: look for markers
        after = None
        if 'now we speak' in lowered:
            # case-insensitive split
            parts = re.split(r'now we speak', text, flags=re.IGNORECASE)
            after = parts[1] if len(parts) > 1 else None
        elif 'setup is complete' in lowered:
            parts = re.split(r'setup is complete', text, flags=re.IGNORECASE)
            after = parts[1] if len(parts) > 1 else None

        names = []
        if after:
            names = extract_language_names_from_text(after)

        # 2) If no names found in canonical confirmation, try to extract directly from the provided text
        if not names:
            names = extract_language_names_from_text(text)

        # Require at least two languages to avoid false positives (copilot prompt asks 2-3 languages)
        if not names or len(names) < 2:
            app.logger.info("No valid language names parsed from text for chat %s: %s", chat_id, text)
            return False

        lang_names = ', '.join(names)
        app.logger.info("Persisting parsed language names for chat %s: %s", chat_id, lang_names)
        # store language_codes as empty string for now to preserve original schema
        try:
            db.upsert_chat_settings(chat_id, '', lang_names, datetime.utcnow().isoformat())
        except Exception as _e:
            app.logger.error("Failed to persist chat settings for %s: %s", chat_id, _e)
        return True
    except Exception as e:
        app.logger.error("Error parsing/persisting setup for chat %s: %s", chat_id, e)
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
                for act in activities:
                    act_id = act.get('id')
                    text = act.get('text')
                    if not act_id or not text:
                        continue
                    if act_id in recent_activity_ids[chat_id]:
                        continue
                    recent_activity_ids[chat_id].append(act_id)
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
        print("Успешно начали диалог с Direct Line.")
        print("DL create response:", data)
        # If API did not return a conversation token, fall back to using the secret for server-side calls
        if not token:
            token = DIRECT_LINE_SECRET
            print("No conversation token returned by DL; falling back to DIRECT_LINE_SECRET for auth (server-side).")
        if not conv_id:
            print("Warning: conversationId missing in Direct Line response")
            return None, None
        # Return (token, conversationId) - note order expected by callers
        return token, conv_id
    else:
        print(f"Ошибка при старте диалога: {response.status_code} {response.text}")
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
            print("DL activities response (count):", len(activities))
            # Print a small sample by default
            print("DL activities sample:", activities[:3])
            # When verbose enabled, print full activities JSON (no secrets)
            if DEBUG_VERBOSE:
                try:
                    print('DL activities full JSON:\n', json.dumps(activities, ensure_ascii=False, indent=2))
                except Exception:
                    print('DL activities full (raw):', activities)
        except Exception:
            pass
        return bot_activities, new_watermark
    else:
        print(f"Ошибка получения ответа: {response.status_code} {response.text}")
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

            if "message" in update_obj and "text" in update_obj["message"]:
                chat_id = update_obj["message"]["chat"]["id"]
                user_message = update_obj["message"]["text"]
                # persist last user message for fallback parsing later
                try:
                    last_user_message[chat_id] = user_message
                except Exception:
                    pass
                app.logger.info(f"[worker] Received message from {chat_id}: {user_message}")

                # Проверяем, есть ли уже активный диалог для этого чата
                if chat_id not in conversations:
                    token, conv_id = start_direct_line_conversation()
                    if not token:
                        app.logger.error("Could not start Direct Line conversation for chat %s", chat_id)
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
                while elapsed < POLL_TIMEOUT:
                    activities, nw = get_copilot_response(session['conv_id'], session['token'], new_watermark, user_from_id=session.get('from_id', str(chat_id)))
                    if activities:
                        for act in activities:
                            act_id = act.get('id')
                            text = act.get('text')
                            if not act_id or not text:
                                continue
                            if act_id in recent_activity_ids[chat_id]:
                                continue
                            recent_activity_ids[chat_id].append(act_id)
                            # Try central helper to parse Copilot setup confirmation and persist settings
                            try:
                                # Only attempt to parse/persist when Copilot itself sends a confirmation message
                                parse_and_persist_setup(chat_id, text)
                            except Exception:
                                pass
                            send_telegram_message(chat_id, text)
                        new_watermark = nw
                        bot_response = True
                        break
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

def send_telegram_message(chat_id, text):
    """Отправляет текстовое сообщение в указанный чат Telegram."""
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    # If DEBUG_LOCAL is enabled, don't call Telegram — just print to console for debugging
    if DEBUG_LOCAL:
        app.logger.info("DEBUG_LOCAL enabled — would send to chat %s: %s", chat_id, text)
        # also print so it's visible in console output
        print(f"[LOCAL FALLBACK] chat={chat_id} text={text}")
        return True

    try:
        response = requests.post(TELEGRAM_URL, json=payload, timeout=5)
    except Exception as e:
        app.logger.error("Exception when sending to Telegram for chat %s: %s", chat_id, e)
        print(f"[LOCAL FALLBACK due to exception] chat={chat_id} text={text}")
        return False

    if response.status_code == 200:
        print(f"Ответ успешно отправлен в чат {chat_id}.")
        return True
    else:
        # On error (for example chat not found), log and fallback to printing the message locally
        try:
            err_text = response.text
        except Exception:
            err_text = '<no-response-body>'
        app.logger.warning("Ошибка отправки в Telegram: %s %s", response.status_code, (err_text or '')[:200])
        print(f"[TELEGRAM ERROR fallback] status={response.status_code} chat={chat_id} text={text}")
        return False

if __name__ == '__main__':
    # Небольшая проверка переменных окружения — полезно ловить ошибки на старте
    if not TELEGRAM_API_TOKEN:
        print("WARNING: TELEGRAM_API_TOKEN is not set. Telegram messages will fail.")
    if not DIRECT_LINE_SECRET:
        print("WARNING: DIRECT_LINE_SECRET is not set. Direct Line calls will fail.")

    # Запуск в production: рекомендуем использовать Waitress на Windows (простая и надёжная)
    # Установите dependency: pip install waitress
    port = int(os.getenv('PORT', '8080'))
    use_waitress = os.getenv('USE_WAITRESS', '1') == '1'
    if use_waitress:
        try:
            from waitress import serve
            print(f"Starting with Waitress on 0.0.0.0:{port}")
            serve(app, host='0.0.0.0', port=port)
        except Exception as e:
            print("Waitress failed to start, falling back to Flask dev server. Error:", e)
            app.run(host='0.0.0.0', port=port)
    else:
        app.run(host='0.0.0.0', port=port)
