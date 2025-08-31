from dotenv import load_dotenv
import os
import requests
import logging

load_dotenv()
log = logging.getLogger('test_directline')
logging.basicConfig(level=logging.INFO)
secret = os.getenv('DIRECT_LINE_SECRET')
endpoint = 'https://directline.botframework.com/v3/directline/conversations'
if not secret:
    log.error('NO_SECRET')
    raise SystemExit(1)
headers = {'Authorization': f'Bearer {secret}'}
try:
    resp = requests.post(endpoint, headers=headers, timeout=10)
    log.info('STATUS %s', resp.status_code)
    j = None
    try:
        j = resp.json()
    except Exception:
        log.warning('NO_JSON')
    if j:
        # log only which keys are present, do not echo values
        log.info('KEYS %s', list(j.keys()))
        # indicate if conversationId or token present
        log.info('HAS_conversationId %s', bool(j.get('conversationId') or (j.get('conversation') and j.get('conversation').get('id'))))
        log.info('HAS_token %s', bool(j.get('token') or j.get('conversationToken')))
    else:
        log.warning('EMPTY_BODY')
except Exception as e:
    log.exception('EXCEPTION %s', e)
