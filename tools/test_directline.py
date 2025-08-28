from dotenv import load_dotenv
import os
import requests

load_dotenv()
secret = os.getenv('DIRECT_LINE_SECRET')
endpoint = 'https://directline.botframework.com/v3/directline/conversations'
if not secret:
    print('NO_SECRET')
    raise SystemExit(1)
headers = {'Authorization': f'Bearer {secret}'}
try:
    resp = requests.post(endpoint, headers=headers, timeout=10)
    print('STATUS', resp.status_code)
    j = None
    try:
        j = resp.json()
    except Exception:
        print('NO_JSON')
    if j:
        # print only which keys are present, do not echo values
        print('KEYS', list(j.keys()))
        # indicate if conversationId or token present
        print('HAS_conversationId', bool(j.get('conversationId') or (j.get('conversation') and j.get('conversation').get('id'))))
        print('HAS_token', bool(j.get('token') or j.get('conversationToken')))
    else:
        print('EMPTY_BODY')
except Exception as e:
    print('EXCEPTION', type(e).__name__, str(e))
