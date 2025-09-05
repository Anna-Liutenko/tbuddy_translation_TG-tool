# План миграции на PostgreSQL

Ниже сохранён подробный план миграции вашего приложения с SQLite на PostgreSQL, включая изменения в репозитории, команды на сервере Ubuntu, скрипты миграции и проверочные шаги. Это прямое документирование предыдущего сообщения — чтобы вы могли вернуться к нему завтра.

---

Краткий план действий
- Добавить в код слой абстракции БД, который использует SQLite по умолчанию и PostgreSQL при наличии `DATABASE_URL`.
- Обновить `requirements.txt` (добавить `psycopg2-binary` или `psycopg[binary]`).
- Добавить миграционный скрипт для переноса данных из SQLite → Postgres.
- На Ubuntu-сервере установить PostgreSQL, создать БД и пользователя, добавить `DATABASE_URL` в `/etc/tbuddy/env`.
- Протестировать локально (проверить подключение к Postgres), затем переключить systemd сервис на использование Postgres.
- Верификация и откатный план.

Чеклист (видимые требования)
- [ ] Не менять логику работы бота с Copilot/Telegram (только заменить слой хранения).
- [ ] Обеспечить миграцию данных из SQLite в Postgres.
- [ ] Подготовить набор команд/скриптов, которые можно безопасно выполнить на Ubuntu.
- [ ] Обновить репозиторий минимальными и обозримыми изменениями (список файлов приведён ниже).
- [ ] Предложить вариант, при котором разработчик (я) подготовит PR, а вы только запушите и выполните инструкции.

Предпосылки / допущения
- Приложение использует таблицу `ChatSettings(chat_id PRIMARY KEY, language_codes, language_names, updated_at)` в SQLite.
- У вас есть доступ к Ubuntu-серверу с правами sudo, либо вы хотите, чтобы я подготовил скрипты.
- Вы хотите 0 изменений в логике обмена сообщениями (я буду менять только слой persistence).
- Если вы хотите, чтобы я выполнил операции на сервере, вы предоставите временный, ограниченный доступ (SSH) или выполните скрипты сами.

1) Что нужно подготовить/запушить в GitHub (минимальные изменения)
- `db.py` — фабрика подключения и API для `get_chat_settings`, `upsert_chat_settings` и т.п.; детектирует `DATABASE_URL` и выбирает psycopg2 или sqlite3.
- `requirements.txt` — добавить `psycopg2-binary>=2.9` (или psycopg3 пакет по желанию).
- `migrations/migrate_sqlite_to_postgres.py` — идемпотентный скрипт миграции с dry-run и apply режимами.
- Обновить `DEPLOY.md` — добавить секцию Postgres и точные команды.
- (Опционально) `deploy/create_postgres_db.sh` — генерирует пользователя и БД (скрипт выводит сгенерированный пароль).

2) Конкретное содержание изменений (коротко)
- `db.py` (новый)
  - detect: если `DATABASE_URL` в окружении — подключаемся к Postgres через psycopg2; иначе — sqlite3.
  - expose: `init_db()`, `get_chat_settings(chat_id)`, `upsert_chat_settings(...)`.
  - цель: минимально инвазивная замена, без изменений логики в `app.py`.
- `migrations/migrate_sqlite_to_postgres.py` (новый)
  - читает строки из `chat_settings.db`, создаёт таблицу в Postgres если нужно, upsert-ит записи.
  - поддерживает `--dry-run` и `--apply` режимы.
- `requirements.txt` — + `psycopg2-binary`
- `DEPLOY.md` — обновление с инструкциями для Postgres.

3) Что делать на сервере (Ubuntu) — последовательность команд
(перед выполнением — убедитесь, что у вас есть sudo)

A. Установить Postgres:
```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

B. Создать БД и пользователя:
```bash
sudo -u postgres psql
-- В psql:
CREATE ROLE tbuddy_user WITH LOGIN PASSWORD 'STRONG_PASSWORD_HERE';
CREATE DATABASE tbuddy_db OWNER tbuddy_user;
ALTER DATABASE tbuddy_db SET client_encoding = 'utf8';
\q
```

C. Если приложение и Postgres на одной машине, дополнительные правки в `pg_hba.conf` обычно не нужны; для TCP-подключений настройте при необходимости.

D. Добавить `DATABASE_URL` в `/etc/tbuddy/env`:
```
DATABASE_URL=postgresql://tbuddy_user:STRONG_PASSWORD_HERE@localhost:5432/tbuddy_db
```

E. Установить зависимости в virtualenv (предполагая код в `/opt/tbuddy`):
```bash
cd /opt/tbuddy
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

F. Выполнить миграцию данных (dry run, затем apply):
```bash
source venv/bin/activate
python migrations/migrate_sqlite_to_postgres.py --database-url "$DATABASE_URL" --sqlite-file ./chat_settings.db --dry-run
# если всё ок:
python migrations/migrate_sqlite_to_postgres.py --database-url "$DATABASE_URL" --sqlite-file ./chat_settings.db --apply
deactivate
```

G. Перезапустить systemd сервис и проверить логи:
```bash
sudo systemctl daemon-reload
sudo systemctl restart tbuddy
sudo journalctl -u tbuddy -f
```

4) Как избежать регресса (гарантии и тесты)
- Изменения ограничиваются `db.py` и вызовами в `app.py` — парсеры и relay не меняются.
- Тесты перед переключением в production:
  1. Локально поднять Postgres и установить `DATABASE_URL`, запустить приложение и прогнать интеграционные тесты (симулированные webhooks).
  2. Выполнить `--dry-run` миграцию и сверить данные.
  3. Сделать backup `chat_settings.db` и (если есть) бэкап Postgres.
- Откат: остановить сервис и удалить/очистить `DATABASE_URL` в `/etc/tbuddy/env` — приложение вернётся к SQLite.

5) Варианты развёртывания Postgres
- Вариант A (рекомендуемый для простоты): Postgres на том же сервере.
- Вариант B: Managed Postgres (RDS, DigitalOcean Managed, Supabase) — требует обновления `DATABASE_URL` и возможной настройки whitelist.

6) Что я могу сделать сейчас (варианты действий)
- Вариант 1 (я подготовлю PR): я создам `db.py`, `migrations/migrate_sqlite_to_postgres.py`, обновлю `requirements.txt` и `DEPLOY.md`. Я не изменяю логику работы с Copilot/Telegram. Покажу diff для ревью.
- Вариант 2 (я выполню на сервере): вы даёте ограниченный доступ (SSH ключ), я выполню скрипты и предоставлю отчёт; заранее договоримся, что правки ограничены и прозрачны.
- Вариант 3 (только инструкции): вы выполняете шаги по инструкции, я консультирую по ходу.

7) Риски и гарантии
- Риск: неверная `DATABASE_URL` или ошибка миграции → несинхронность данных. Mitigation: dry-run и бэкап `chat_settings.db`.
- Гарантия: я не буду менять логику обмена сообщениями; внесу только минимальный слой абстракции и миграционный скрипт. Все изменения будут показаны до применения.

8) Smoke tests после миграции
- Проверить `/health` → ok.
- Проверить содержимое таблицы:
```bash
sudo -u postgres psql -d tbuddy_db -c "select * from ChatSettings limit 5;"
```
- Отправить тестовый webhook, получить ответ и убедиться, что relay работает как раньше.

---

Если хотите, я сейчас подготовлю файлы и сделаю коммит в ветке `main`/создам PR с этими изменениями (вариант 1). Скажите, какой вариант вы выбираете — и я продолжу.
