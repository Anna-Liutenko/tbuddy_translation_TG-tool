"""Quick smoke tests for the DB abstraction."""
import os
import sys
# ensure project root is on sys.path so local modules (db.py) can be imported when running this script
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from db import init_db, dump_all, upsert_chat_settings, get_chat_settings
from datetime import datetime


def run():
    print('Initializing DB...')
    init_db()
    print('Inserting test row...')
    upsert_chat_settings('test_chat', 'en,ru', 'English, Russian', datetime.utcnow().isoformat())
    print('Dumping rows:')
    rows = dump_all()
    for r in rows:
        print(r)
    print('Fetching test_chat:')
    print(get_chat_settings('test_chat'))


if __name__ == '__main__':
    run()
