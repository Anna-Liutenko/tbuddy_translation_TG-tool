import sys, importlib, os
# ensure we can find the app module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app = importlib.import_module('app')
import db

# Clean up previous test runs
try:
    db.delete_chat_settings(999999)
    print("Cleaned up old test records for chat_id 999999.")
except Exception as e:
    print(f"Could not clean up old test records: {e}")


tests = [
    "What's languages you prefer? Write 2 or 3 languages.",
    "Write 2 languages: English, Russian, Polish",
    "English, Russian, Polish",
    "Укажите 2 языка: русский, английский",
    "Send your message and I'll translate it.",
    "en: Hello\nru: Привет",
]

print('\nRunning parse/skip tests against app.should_skip_forwarding and parse_and_persist_setup')
for t in tests:
    print('\n---')
    print('TEXT:', t)
    try:
        print('should_skip_forwarding ->', app.should_skip_forwarding(t))
    except Exception as e:
        print('should_skip_forwarding raised', e)
    try:
        res = app.parse_and_persist_setup(999999, t)
        print('parse_and_persist_setup ->', res)
    except Exception as e:
        print('parse_and_persist_setup raised', e)

print('\n---')
print('Dumping DB rows containing chat_id=999999')
rows = db.dump_all()
found = [r for r in rows if r.get('chat_id')==999999 or str(r.get('chat_id'))=='999999']
print('found rows count=', len(found))
for r in found:
    print(r)
