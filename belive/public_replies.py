"""Explicit staff-approved replies to the exact collected platform object.

Only official APIs are used. An uncertain write is never retried automatically.
"""
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlencode

from belive import google_replies, public_preview
from belive.connectors import request_json, THREADS_API, FACEBOOK_COMMENT_LIMIT
from belive.credentials import get_value
from belive.store import bounded, digest, now

LABELS = {'GOOGLE': 'Google', 'FACEBOOK': 'Facebook', 'THREADS': 'Threads'}
CLOSED = {'CLOSED', 'ANSWERED', 'SKIPPED', 'VERIFIED'}


def _check(condition, message):
    if not condition: raise _Blocked(message)


class _Blocked(ValueError):
    pass


class _Rejected(ValueError):
    pass


def _graph_error_numbers(error):
    if not isinstance(error, HTTPError) or not 400 <= error.code < 500:
        return None, None
    try:
        # Numeric fields are enough; provider messages can contain URLs or credential data.
        body = error.read(16_385)
        if len(body) > 16_384: return None, None
        parsed = json.loads(body).get('error', {})
        code, subcode = parsed.get('code'), parsed.get('error_subcode')
    except (ValueError, TypeError, AttributeError, OSError):
        return None, None
    return tuple(value if type(value) is int and 0 <= value < 2 ** 31 else None
                 for value in (code, subcode))


def _authentication_detail(platform, error, numbers=None):
    code, subcode = _graph_error_numbers(error) if numbers is None else numbers
    if code != 190 or platform not in {'FACEBOOK', 'THREADS'}: return ''
    label = LABELS[platform]
    replacement = 'a new Page access token' if platform == 'FACEBOOK' else 'a new Threads access token'
    if subcode == 463:
        return label + ' access token expired. Save ' + replacement + ' in Connection settings, then try again.'
    return label + ' access token is invalid or no longer authorised. Save ' + replacement + ' in Connection settings, then try again.'


def _platform_error_detail(platform, stage, error):
    numbers = _graph_error_numbers(error)
    authentication = _authentication_detail(platform, error, numbers)
    if authentication: return authentication
    code = numbers[0]
    if platform != 'FACEBOOK' or code is None or not (code == 10 or 200 <= code <= 299):
        return ''
    if stage == 'POST_COMMENT':
        return ('Facebook did not allow this Page reply. Re-authorise the app with '
                'pages_manage_engagement and use a Page access token from someone with '
                'the MODERATE Page task. Read permissions alone cannot send replies.')
    if stage == 'PREFLIGHT':
        return ('Facebook could not read or verify the selected Page/source. Check '
                'pages_read_engagement, pages_read_user_content, the selected Page or post, '
                'and this Page token’s access. No reply was sent.')
    return ''


def _api(url, token, payload=None):
    result = request_json(url, token, payload=payload, method='POST' if payload is not None else 'GET')
    if isinstance(result, dict) and result.get('error'):
        raise _Rejected('The platform rejected the API request. Check company access and publishing permissions.')
    _check(isinstance(result, dict), 'The platform returned an invalid response.')
    return result


def _object_id(value):
    return isinstance(value, str) and bool(re.fullmatch(r'\d+(?:_\d+)*', value))


def _provenance(service, db, case):
    versions = case.get('source_versions') or []
    if not versions: return False
    row = db.execute('SELECT platform,source_id,hash FROM sources WHERE id=?', (versions[-1],)).fetchone()
    return bool(row and row['platform'] == case.get('platform') and row['source_id'] == case.get('source_id')
                and row['hash'] == digest(case.get('description', '')))


def _binding(service, db, case):
    platform, target = case.get('platform'), case.get('source_id', '')
    facebook_comment=(platform=='FACEBOOK' and case.get('public_source_kind')=='FACEBOOK_COMMENT')
    _check(_object_id(target), 'This case has no exact official platform object ID. A webpage link alone cannot be used to send.')
    sources = [s for s in service.store.all(db, 'source') if s.get('platform') == platform
               and s.get('authorised') is True]
    if platform == 'THREADS':
        _check(bool(re.fullmatch(r'\d+', target)), 'Threads needs the exact numeric reply ID from the official API.')
        parent = case.get('parent_source_id', '')
        for source in sources:
            resource = source.get('resource', '')
            if re.fullmatch(r'\d+/threads', resource) and _object_id(parent):
                return {'target': target, 'parent': parent, 'account': resource.split('/')[0], 'source': source}
            if re.fullmatch(r'\d+/replies', resource):
                selected_parent = resource.split('/')[0]
                if parent == selected_parent or not parent:
                    return {'target': target, 'parent': selected_parent, 'account': None, 'source': source}
    if platform == 'FACEBOOK':
        comment_sources = []
        for source in sources:
            resource = source.get('resource', '')
            if re.fullmatch(r'\d+/feed',resource) and facebook_comment:
                parent=case.get('parent_source_id','')
                if _object_id(parent):
                    return {'target':target,'parent':parent,'account':resource.split('/')[0],'source':source}
            if re.fullmatch(r'\d+/feed', resource) and target.startswith(resource.split('/')[0] + '_'):
                if facebook_comment:continue
                return {'target': target, 'parent': None, 'account': resource.split('/')[0], 'source': source}
            if re.fullmatch(r'\d+(?:_\d+)*/comments', resource):
                parent = resource.rsplit('/', 1)[0]
                if case.get('parent_source_id') == parent or target.startswith(parent + '_'):
                    return {'target': target, 'parent': parent, 'account': None, 'source': source}
                comment_sources.append(source)
        if len(comment_sources) == 1:
            # Opaque comment IDs cannot prove a parent; live membership is required before any write.
            source = comment_sources[0]
            return {'target': target, 'parent': source['resource'].rsplit('/', 1)[0], 'account': None, 'source': source}
    raise ValueError('This exact source is not bound to an authorised company API source. Import it from the authorised source first.')


def _eligibility(service, case, db):
    platform = case.get('platform')
    result = {'ready': False, 'platform': platform, 'target_label': LABELS.get(platform, 'original platform'),
              'publishing_verified': False}
    try:
        _check(platform in LABELS and case.get('entrypoint') == 'PUBLIC_SOURCE', 'Choose a collected Google, Facebook or Threads complaint.')
        _check(case.get('status') not in CLOSED, 'Reopen this complaint before sending a public reply.')
        _check(_provenance(service, db, case), 'The original source evidence does not match this case. Reimport and assess the source first.')
        assessment = case.get('analysis') or {}
        _check(assessment.get('report_type') == 'COMPLAINT' and assessment.get('relevance') == 'SUPPORT'
               and not assessment.get('uncertainty'), 'Assess this complaint before sending a public reply.')
        followups = [x for x in service.store.all(db, 'public_followup') if x.get('case_id') == case['id']]
        followups.sort(key=lambda x: x['created_at'])
        _check(public_preview.is_current(case, followups), 'Prepare a fresh reply for the current source and customer follow-up before sending.')
        previous = case.get('public_reply') or {}
        _check(previous.get('status') not in {'SENDING', 'UNKNOWN'}, 'A previous send is unconfirmed. Check the original platform; do not retry it.')
        _check(previous.get('status') != 'PENDING' or (previous.get('container_id')
               and previous.get('stage') in {'CHECK_CONTAINER', 'WAIT_CONTAINER'}), 'A send is already being checked. Wait for its result.')
        if platform == 'GOOGLE':
            ready = google_replies.readiness(service.store, db, case)
            _check(ready['ready'], ready['reason'])
        else:
            _binding(service, db, case)
            _check(bool(get_value('BELIVE_' + platform + '_TOKEN', database=service.store.path)), 'Save the company ' + result['target_label'] + ' API token in Connection settings first.')
            if platform == 'FACEBOOK':
                _check(bool(re.fullmatch(r'v\d+\.\d+', get_value('BELIVE_FACEBOOK_VERSION', database=service.store.path))), 'Configure the Facebook Graph API version first.')
        result.update(ready=True, reason='Sends the approved text publicly on ' + result['target_label']
                      + '. Company account and source are checked on send; publishing permission is not verified by a saved token alone.')
    except ValueError as exc:
        result['reason'] = str(exc)
    return result


def eligibility(service, case, db=None):
    """Local capability only; no platform request or permission claim is made here."""
    if db is not None: return _eligibility(service, case, db)
    with service.store.connect() as connection:
        return _eligibility(service, case, connection)


def _verify_target(platform, binding, token, version, description):
    base = THREADS_API if platform == 'THREADS' else 'https://graph.facebook.com/' + version + '/'
    profile = _api(base + 'me?' + urlencode({'fields': 'id,username' if platform == 'THREADS' else 'id,name,category'}), token)
    account = profile.get('id')
    _check(_object_id(account), 'The company account could not be verified. No reply was sent.')
    if platform == 'FACEBOOK':
        _check(isinstance(profile.get('category'), str) and bool(profile['category'].strip()), 'The token did not identify a Facebook Page. No reply was sent.')
    _check(not binding['account'] or account == binding['account'], 'The token belongs to a different company account. No reply was sent.')
    target, parent = binding['target'], binding['parent']
    if parent:
        owner = _api(base + parent + '?' + urlencode({'fields': 'id,owner' if platform == 'THREADS' else 'id,from'}), token)
        ownership = owner.get('owner' if platform == 'THREADS' else 'from', {})
        owner_id = ownership.get('id') if isinstance(ownership, dict) else ownership
        _check(owner.get('id') == parent and owner_id == account, 'The selected parent is not owned by the connected company account. No reply was sent.')
        field = 'text' if platform == 'THREADS' else 'message'
        fields = 'id,' + field + (',can_comment' if platform == 'FACEBOOK' else '')
        query={'fields':fields,'limit':100}
        if platform=='FACEBOOK':query.update(limit=FACEBOOK_COMMENT_LIMIT,filter='toplevel',order='reverse_chronological')
        response = _api(base + parent + ('/replies?' if platform == 'THREADS' else '/comments?')
                        + urlencode(query), token)
        item = next((x for x in response.get('data', []) if isinstance(x, dict) and x.get('id') == target), None)
        _check(item is not None, 'The exact complaint could not be confirmed under the authorised parent. Refresh collection before sending.')
        if platform == 'FACEBOOK':
            _check(item.get('can_comment') is True, 'Facebook does not confirm that this comment can receive a reply.')
    else:
        item = _api(base + target + '?' + urlencode({'fields': 'id,message,from'}), token)
        _check(item.get('id') == target and (item.get('from') or {}).get('id') == account, 'The exact Facebook post is not owned by the connected company Page.')
        field = 'message'
    _check(bounded(item.get(field), 1, 6000) == description, 'The original complaint changed. Collect and review its latest text before sending.')
    return account


def _save(service, case_id, attempt, result, event=None):
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        case = service.store.get(db, 'case', case_id)
        case['public_reply'] = dict(result);case['revision'] += 1
        service.store.put(db, 'case', case)
        attempt['result'] = dict(result)
        service.store.put(db, 'public_reply_attempt', attempt)
        if event: service.store.event(db, case_id, event, result.get('detail', result['stage']))
        return case['revision']


def publish(service, p, actor, key):
    _check(isinstance(key, str) and 8 <= len(key) <= 150, 'A request idempotency key is required')
    _check(p.get('confirmed') is True, 'Review the exact reply and approve sending it publicly first')
    _check(isinstance(actor, str) and 1 <= len(actor) <= 120, 'An authenticated staff actor is required')
    text = bounded(p.get('text'), 1, 3000)
    request_id = digest(key)
    payload_hash = digest(json.dumps({'id': p.get('id'), 'text': text,
                                     'platform': p.get('platform'), 'source_id': p.get('source_id'),
                                     'replace_existing': p.get('replace_existing') is True}, sort_keys=True))
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        prior_request = next((x for x in service.store.all(db, 'public_reply_request') if x['id'] == request_id), None)
        if prior_request:
            _check(prior_request['fingerprint'] == payload_hash, 'Idempotency mismatch')
            attempt = service.store.get(db, 'public_reply_attempt', prior_request['attempt_id'])
            if attempt['result']['status'] != 'PENDING' or not attempt['result'].get('container_id'):
                return attempt['result']
        case = service.store.get(db, 'case', p.get('id'))
        _check(case['revision'] == p.get('revision'), 'Case changed; reload before sending')
        _check(not p.get('platform') or p['platform'] == case['platform'], 'The platform does not match the selected case')
        _check(not p.get('source_id') or p['source_id'] == case['source_id'], 'The source does not match the selected case')
        ready = _eligibility(service, case, db);_check(ready['ready'], ready['reason'])
        platform = case['platform']
        if platform == 'THREADS':
            _check(len(text) <= 500, 'Shorten the Threads reply to at most 500 characters before sending.')
        previous = case.get('public_reply') or {}
        if previous.get('status') == 'POSTED' and previous.get('text') == text and previous.get('target_id') == case['source_id']:
            return previous
        binding = None if platform == 'GOOGLE' else _binding(service, db, case)
        identity = digest(json.dumps([platform, case['source_id'], text, case['public_reply_preview']['input_fingerprint']], sort_keys=True))
        if prior_request:
            _check(attempt['result'].get('identity') == identity, 'Idempotency mismatch: source or reviewed inputs changed')
        if previous.get('status') == 'PENDING' and previous.get('container_id') and previous.get('identity') != identity:
            old = service.store.get(db, 'public_reply_attempt', previous['attempt_id'])
            old['result'].update(status='FAILED', stage='SUPERSEDED_BEFORE_PUBLISH', retryable_container=False,
                                 detail='A new explicitly approved reply replaced this unposted container. This older request will not publish.')
            service.store.put(db, 'public_reply_attempt', old)
        reusable = (previous.get('container_id') and previous.get('identity') == identity
                    and (previous.get('status') == 'PENDING' or previous.get('retryable_container') is True))
        if reusable:
            attempt = service.store.get(db, 'public_reply_attempt', previous['attempt_id'])
            result = dict(previous)
        else:
            attempt = {'id': 'PUBSEND-' + request_id, 'fingerprint': payload_hash, 'case_id': case['id']}
            result = {'status': 'PENDING', 'platform': platform, 'target_label': LABELS[platform],
                'target_id': case['source_id'], 'text': text, 'actor': actor, 'at': now(),
                'attempt_id': attempt['id'], 'identity': identity, 'stage': 'PREFLIGHT',
                'approved_revision': p['revision'],
                'detail': 'Checking the exact source and company account before sending.'}
        service.store.put(db, 'public_reply_request', {'id': request_id, 'fingerprint': payload_hash, 'attempt_id': attempt['id']})
        result.update(status='SENDING' if reusable else 'PENDING', stage='PREFLIGHT')
        case['public_reply'] = dict(result);case['revision'] += 1
        reserved_revision = case['revision']
        service.store.put(db, 'case', case)
        attempt['result'] = dict(result);service.store.put(db, 'public_reply_attempt', attempt)
        service.store.event(db, case['id'], 'PUBLIC_REPLY_APPROVED', actor + ': exact reviewed public text approved for ' + LABELS[platform])
    writing = False
    try:
        if platform == 'GOOGLE':
            # The legacy publisher also checks the live review and explicit replacement permission.
            with service.lock:
                with service.store.connect() as db:
                    live = service.store.get(db, 'case', case['id'])
                    _check(live['revision'] == reserved_revision, 'Case changed before sending. No reply was sent.')
                receipt = google_replies.publish(service, {**p, 'revision': reserved_revision}, actor, 'public-' + digest(key))
            result.update(receipt, platform=platform, target_label=LABELS[platform], stage='COMPLETE')
        else:
            token = get_value('BELIVE_' + platform + '_TOKEN', database=service.store.path)
            version = get_value('BELIVE_FACEBOOK_VERSION', database=service.store.path) if platform == 'FACEBOOK' else ''
            account = _verify_target(platform, binding, token, version, case['description'])
            with service.lock:
                with service.store.connect() as db:
                    live = service.store.get(db, 'case', case['id'])
                    _check(live['revision'] == reserved_revision and _provenance(service, db, live), 'Case changed before sending. No reply was sent.')
                if platform == 'FACEBOOK':
                    result.update(status='SENDING', stage='POST_COMMENT')
                    _save(service, case['id'], attempt, result, 'PUBLIC_REPLY_SENDING')
                    writing = True
                    receipt = _api('https://graph.facebook.com/' + version + '/' + binding['target'] + '/comments', token, {'message': text})
                    _check(_object_id(receipt.get('id')), 'The platform did not return a confirmed reply ID.')
                    result.update(status='POSTED', stage='COMPLETE', receipt_id=receipt['id'], detail='Facebook confirmed the new reply ID. Check the original source for public display.')
                else:
                    if not result.get('container_id'):
                        result.update(status='SENDING', stage='CREATE_CONTAINER')
                        _save(service, case['id'], attempt, result, 'PUBLIC_REPLY_SENDING')
                        writing = True
                        container = _api(THREADS_API + account + '/threads', token,
                            {'media_type': 'TEXT', 'text': text, 'reply_to_id': binding['target'], 'auto_publish_text': False})
                        _check(_object_id(container.get('id')), 'The platform did not return a container ID.')
                        result.update(container_id=container['id'], status='PENDING', stage='CHECK_CONTAINER')
                        _save(service, case['id'], attempt, result)
                    writing = False
                    for poll in range(3):
                        status = _api(THREADS_API + result['container_id'] + '?fields=id,status', token)
                        _check(status.get('id') == result['container_id'], 'The platform returned a different container.')
                        state = status.get('status')
                        if state != 'IN_PROGRESS': break
                        if poll < 2: time.sleep(1)
                    if state == 'IN_PROGRESS':
                        result.update(status='PENDING', stage='WAIT_CONTAINER', detail='Threads is processing the saved container. Continue this send later; no duplicate container is needed.')
                    elif state in {'ERROR', 'EXPIRED'}:
                        result.update(status='FAILED', stage='CONTAINER_FAILED', retryable_container=False, detail='Threads did not prepare this container. A new approved attempt is needed.')
                    else:
                        _check(state == 'FINISHED', 'The saved container is not confirmed ready; check Threads before another attempt.')
                        result.update(status='SENDING', stage='PUBLISH_CONTAINER')
                        _save(service, case['id'], attempt, result, 'PUBLIC_REPLY_SENDING')
                        writing = True
                        receipt = _api(THREADS_API + account + '/threads_publish', token, {'creation_id': result['container_id']})
                        _check(_object_id(receipt.get('id')), 'The platform did not return a confirmed reply ID.')
                        result.update(status='POSTED', stage='COMPLETE', receipt_id=receipt['id'], detail='Threads confirmed the new reply ID. Check the original source for display or pending reply approval.')
    except Exception as exc:
        rejected = isinstance(exc, _Rejected) or isinstance(exc, HTTPError) and 400 <= exc.code < 500
        platform_detail = _platform_error_detail(platform, result['stage'], exc)
        unknown = writing and not rejected
        # A published or otherwise unexpected container state may already represent a public write.
        if not writing and result.get('container_id') and not rejected:
            unknown = True
        result.update(status='UNKNOWN' if unknown else 'FAILED', retryable_container=bool(rejected and result.get('container_id') and result['stage'] == 'PUBLISH_CONTAINER'),
                      detail=('The platform outcome is unconfirmed. Check the original source; do not retry this send.' if unknown
                              else platform_detail if platform_detail
                              else str(exc) if isinstance(exc, (_Blocked, _Rejected))
                              else 'The platform rejected the request or the exact source/account could not be verified. No confirmed reply was recorded.'))
    _save(service, case['id'], attempt, result, 'PUBLIC_REPLY_' + result['status'])
    return result
