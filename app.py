import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# --- НАСТРОЙКИ: загружаются из файла .env ---
# 1. Токен вашего Telegram бота от @BotFather
TELEGRAM_API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")

# 2. Секрет вашего бота из Copilot Studio (Settings -> Channels -> Direct Line)
DIRECT_LINE_SECRET = os.getenv("DIRECT_LINE_SECRET")

# 3. URL для получения токена Direct Line.
DIRECT_LINE_ENDPOINT = "https://directline.botframework.com/v3/directline/tokens/generate"

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
    # Запрашиваем токен для начала диалога
    response = requests.post(DIRECT_LINE_ENDPOINT, headers=headers)
    if response.status_code == 200:
        data = response.json()
        print("Успешно начали диалог с Direct Line.")
        return data['token'], data['conversationId']
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
    if response.status_code == 200:
        print("Сообщение успешно отправлено в Copilot.")
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
        return "\n".join(bot_messages), new_watermark
    else:
        print(f"Ошибка получения ответа: {response.status_code} {response.text}")
        return None, last_watermark

@app.route('/webhook', methods=['POST'])
def telegram_webhook():
    """Эта функция вызывается, когда Telegram присылает новое сообщение."""
    update = request.get_json()
    
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        user_message = update["message"]["text"]
        
        print(f"Получено сообщение от чата {chat_id}: {user_message}")

        # Проверяем, есть ли уже активный диалог для этого чата
        if chat_id not in conversations:
            token, conv_id = start_direct_line_conversation()
            if not token:
                return jsonify(status="error", message="Could not start conversation")
            conversations[chat_id] = {"conv_id": conv_id, "token": token, "watermark": None}
        
        session = conversations[chat_id]
        
        # 1. Отправляем сообщение пользователя в Copilot
        send_message_to_copilot(session['conv_id'], session['token'], user_message)
        
        # 2. Ждем и получаем ответ от Copilot
        # В простом примере делаем паузу и один запрос. В сложном приложении
        # лучше использовать WebSocket для получения ответов в реальном времени.
        import time
        time.sleep(2) # Даем боту время на обработку
        bot_response, new_watermark = get_copilot_response(session['conv_id'], session['token'], session['watermark'])
        conversations[chat_id]['watermark'] = new_watermark # Сохраняем новую отметку
        
        # 3. Если есть ответ, отправляем его обратно в Telegram
        if bot_response:
            send_telegram_message(chat_id, bot_response)

    return jsonify(status="ok")

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
    # Запуск веб-сервера. Для реального использования нужен более надежный
    # сервер, например, Gunicorn или Waitress.
    app.run(host='0.0.0.0', port=8080)
