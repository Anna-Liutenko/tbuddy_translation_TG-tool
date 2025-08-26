import os
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv

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

def send_message_to_copilot(conversation_id, token, text):
    """Отправляет сообщение пользователя в Copilot Studio."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    payload = {
        "type": "message",
        "from": {"id": "user"},
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

def get_copilot_response(conversation_id, token, last_watermark):
    """Получает ответ от Copilot Studio."""
    url = f"https://directline.botframework.com/v3/directline/conversations/{conversation_id}/activities"
    if last_watermark:
        url += f"?watermark={last_watermark}"
    
    headers = {
        'Authorization': f'Bearer {token}',
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        bot_messages = [act['text'] for act in data.get('activities', []) if act['from']['id'] != 'user' and 'text' in act]
        new_watermark = data.get('watermark', last_watermark)
        try:
            print("DL activities response (count):", len(data.get('activities', [])))
            # print a small sample for debugging
            print("DL activities sample:", data.get('activities', [])[:3])
        except Exception:
            pass
        return "\n".join(bot_messages), new_watermark
    else:
        print(f"Ошибка получения ответа: {response.status_code} {response.text}")
        return None, last_watermark

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
                    conversations[chat_id] = {"conv_id": conv_id, "token": token, "watermark": None}

                session = conversations[chat_id]

                # 1. Отправляем сообщение пользователя в Copilot
                send_message_to_copilot(session['conv_id'], session['token'], user_message)

                # 2. Небольшая пауза и получение ответа
                import time
                time.sleep(2)
                bot_response, new_watermark = get_copilot_response(session['conv_id'], session['token'], session['watermark'])
                conversations[chat_id]['watermark'] = new_watermark

                # 3. Если есть ответ, отправляем его обратно в Telegram
                if bot_response:
                    send_telegram_message(chat_id, bot_response)
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
