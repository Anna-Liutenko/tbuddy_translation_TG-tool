import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import sqlite3
from collections import deque, defaultdict
from datetime import datetime

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

# Инициализация веб-сервера Flask
app = Flask(__name__)

# Словарь для хранения активных диалогов.
# В реальном приложении лучше использовать базу данных (например, Redis или SQLite).
# Ключ: ID чата в Telegram, Значение: ID диалога в Copilot Studio и токен.
conversations = {}

# Recent activity ids per chat to avoid duplicate forwards (keeps last 100 IDs)
recent_activity_ids = defaultdict(lambda: deque(maxlen=100))

# Simple SQLite DB to persist chat settings when Copilot confirms setup
DB_PATH = os.path.join(os.path.dirname(__file__), 'chat_settings.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS ChatSettings (
        chat_id TEXT PRIMARY KEY,
        language_codes TEXT,
        language_names TEXT,
        updated_at TEXT
    )
    ''')
    conn.commit()
    conn.close()

def set_chat_settings(chat_id, language_codes, language_names):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('REPLACE INTO ChatSettings (chat_id, language_codes, language_names, updated_at) VALUES (?, ?, ?, ?)',
                (str(chat_id), language_codes or '', language_names or '', datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_chat_settings(chat_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT language_codes, language_names FROM ChatSettings WHERE chat_id = ?', (str(chat_id),))
    row = cur.fetchone()
    conn.close()
    if row:
        return row[0], row[1]
    return None, None

init_db()

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
    response = requests.post(DIRECT_LINE_ENDPOINT, headers=headers)
    if response.status_code in (200, 201):
        data = response.json()
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
    response = requests.post(url, headers=headers, json=payload)
    # Direct Line may return 200 or 201 on activity post
    if response.status_code in (200, 201):
        print("Сообщение успешно отправлено в Copilot.")
        try:
            print("DL send response:", response.json())
        except Exception:
            pass
    else:
        print(f"Ошибка отправки сообщения: {response.status_code} {response.text}")

def get_copilot_response(conversation_id, token, last_watermark, user_from_id="user"):
    """Return list of bot activities (dicts) not from user and updated watermark."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    if last_watermark:
        url += f"?watermark={last_watermark}"

    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        activities = data.get('activities', [])
        # Filter activities that are not from the Telegram user and have text
        bot_activities = [act for act in activities if act.get('from', {}).get('id') != str(user_from_id) and act.get('text')]
        new_watermark = data.get('watermark', last_watermark)
        try:
            print("DL activities response (count):", len(activities))
            print("DL activities sample:", activities[:3])
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
                            # Detect setup-complete messages from Copilot and persist settings
                            try:
                                if isinstance(text, str) and ('Setup is complete' in text or 'Now we speak' in text):
                                    # crude parse: try to extract language names after 'Now we speak'
                                    if 'Now we speak' in text:
                                        # Extract text between 'Now we speak' and the next '.' (or end of string)
                                        try:
                                            after = text.split('Now we speak', 1)[1]
                                            # stop at the first '.' or at the phrase 'Send your message'
                                            end_idx = None
                                            for sep in ['.', '\n', 'Send your message', 'Send your message and']:
                                                idx = after.find(sep)
                                                if idx != -1:
                                                    if end_idx is None or idx < end_idx:
                                                        end_idx = idx
                                            if end_idx is not None:
                                                lang_names = after[:end_idx].strip().strip('.,\n ')
                                            else:
                                                lang_names = after.strip().strip('.,\n ')
                                            if lang_names:
                                                set_chat_settings(chat_id, None, lang_names)
                                        except Exception:
                                            pass
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

def send_telegram_message(chat_id, text):
    """Отправляет текстовое сообщение в указанный чат Telegram."""
    payload = {
        'chat_id': chat_id,
        'text': text
    }
    response = requests.post(TELEGRAM_URL, json=payload)
    if response.status_code == 200:
        print(f"Ответ успешно отправлен в чат {chat_id}.")
    else:
        print(f"Ошибка отправки в Telegram: {response.status_code} {response.text}")

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
