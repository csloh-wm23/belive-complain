"""One persistent local draft reservation, shared by automatic and manual requests."""
import json
import os
import secrets
import threading

from belive import public_preview
from belive.ai import FAILURE_MESSAGES, failure_code
from belive.credentials import credential_scope
from belive.store import digest, now, redact

KIND = 'public_draft_job'
_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()
_INTERRUPTED = 'Draft preparation was interrupted. The saved draft is unchanged; choose Rewrite to try again.'
_STALE = 'The case changed while the draft was being prepared. Review the latest assessment before trying again.'
_PAUSED = 'Automatic drafting is paused for this case. An explicit Rewrite is still available.'


def eligible(case):
    assessment = case.get('analysis') or {}
    return bool(case.get('entrypoint') == 'PUBLIC_SOURCE'
                and case.get('platform') in {'GOOGLE', 'FACEBOOK', 'THREADS'}
                and case.get('source_versions')
                and assessment.get('report_type') == 'COMPLAINT'
                and assessment.get('relevance') == 'SUPPORT'
                and not assessment.get('uncertainty')
                and case.get('status') not in {'CLOSED', 'SKIPPED', 'VERIFIED', 'ANSWERED'})


def _find(service, db, case_id):
    row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (KIND, case_id)).fetchone()
    return json.loads(row[0]) if row else None


def _inputs(service, db, case):
    followups = service.public_followups(db, case['id'])
    value = {'format_version': public_preview.VERSION,
             'source_version': (case.get('source_versions') or [None])[-1],
             'context': public_preview.context(case, followups)}
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False)), followups


def _describe(job, case, fingerprint, preview_current):
    return {key: job.get(key) for key in
            ('id', 'status', 'error', 'error_code', 'created_at', 'updated_at', 'started_at', 'finished_at')} | {
                'case_id': case['id'], 'current_input': job['input_fingerprint'] == fingerprint,
                'preview_current': preview_current,
            }


def status(service, db, case):
    """Read-only dashboard state; an unqueued legacy draft can await bounded backfill."""
    job = _find(service, db, case['id'])
    if not job and not eligible(case):
        return None
    fingerprint, followups = _inputs(service, db, case)
    current = public_preview.is_current(case, followups)
    if job:
        result = _describe(job, case, fingerprint, current)
        if job['status'] == 'QUEUED' and case.get('automation_paused') and not job.get('manual'):
            result.update(status='STALE', error=_PAUSED, error_code='PAUSED')
        if (job['status'] not in {'RUNNING', 'QUEUED'} and job['input_fingerprint'] != fingerprint
                and eligible(case) and not case.get('automation_paused')):
            result.update(status='COMPLETE' if current else 'QUEUED', error='', error_code='')
        return result
    if eligible(case) and not case.get('automation_paused'):
        return {'id': case['id'], 'case_id': case['id'], 'status': 'COMPLETE' if current else 'QUEUED',
                'error': '', 'error_code': '', 'current_input': True, 'preview_current': current}
    return None


def _owner_alive(job):
    pid = job.get('owner_pid')
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        with _ACTIVE_LOCK:
            return job.get('attempt_id') in _ACTIVE
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # An inaccessible process may still own the work.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def _recover(service, db):
    count = 0
    for job in service.store.all(db, KIND):
        if job['status'] != 'RUNNING' or _owner_alive(job):
            continue
        case = service.store.get(db, 'case', job['id'])
        fingerprint, followups = _inputs(service, db, case)
        completed = job['input_fingerprint'] == fingerprint and public_preview.is_current(case, followups)
        job.update(status='COMPLETE' if completed else 'FAILED', error='' if completed else _INTERRUPTED,
                   error_code='' if completed else 'INTERRUPTED', updated_at=now(), finished_at=now())
        service.store.put(db, KIND, job)
        service.store.event(db, case['id'], 'PUBLIC_DRAFT_RECOVERED',
                            'Saved draft recovered' if completed else 'Interrupted generation requires an explicit retry')
        count += 1
    return count


def recover(service):
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        return _recover(service, db)


def _queue(service, db, case, actor, manual):
    old = _find(service, db, case['id'])
    fingerprint, followups = _inputs(service, db, case)
    if old and old['status'] == 'RUNNING':
        return old
    if not eligible(case):
        return None
    if not manual and case.get('automation_paused'):
        return None
    if not manual and public_preview.is_current(case, followups):
        return None
    if old and old['input_fingerprint'] == fingerprint:
        if old['status'] == 'QUEUED':
            if manual and not old.get('manual'):
                old.update(manual=True, actor=redact(str(actor))[:120], updated_at=now())
                service.store.put(db, KIND, old)
            return old
        if old['status'] in {'FAILED', 'STALE'} and old.get('error_code') != 'PAUSED' and not manual:
            return None
    job = {'id': case['id'], 'input_fingerprint': fingerprint, 'status': 'QUEUED',
           'revision': case['revision'], 'actor': redact(str(actor))[:120], 'manual': bool(manual),
           'attempt_id': secrets.token_hex(16), 'owner_pid': None,
           'created_at': (old or {}).get('created_at', now()), 'updated_at': now(),
           'started_at': None, 'finished_at': None, 'error': '', 'error_code': ''}
    service.store.put(db, KIND, job)
    return job


def queue(service, case_id, revision, actor, manual=False):
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _recover(service, db)
        case = service.store.get(db, 'case', case_id)
        if case['revision'] != revision:
            raise ValueError('Case changed. Refresh it before preparing a preview.')
        if manual and not eligible(case):
            raise ValueError('A confirmed, active public complaint assessment is required')
        return _queue(service, db, case, actor, manual)


def queue_next(service):
    """Backfill at most one old active case, without filling a startup queue."""
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _recover(service, db)
        if any(job['status'] in {'RUNNING', 'QUEUED'} for job in service.store.all(db, KIND)):
            return None
        cases = sorted(service.store.all(db, 'case'),
                       key=lambda case: case.get('updated_at') or case.get('created_at', ''), reverse=True)
        for case in cases:
            if eligible(case) and not case.get('automation_paused'):
                job = _queue(service, db, case, 'Automatic public reply draft', False)
                if job:
                    return job
    return None


def _claim(service, case_id):
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _recover(service, db)
        case = service.store.get(db, 'case', case_id)
        job = _find(service, db, case_id)
        if not job or job['status'] != 'QUEUED':
            return None
        fingerprint, _ = _inputs(service, db, case)
        if case.get('automation_paused') and not job.get('manual'):
            job.update(status='STALE', error=_PAUSED, error_code='PAUSED', updated_at=now(), finished_at=now())
            service.store.put(db, KIND, job)
            return None
        if not eligible(case) or fingerprint != job['input_fingerprint']:
            job.update(status='STALE', error=_STALE, error_code='STALE', updated_at=now(), finished_at=now())
            service.store.put(db, KIND, job)
            return None
        if any(other['status'] == 'RUNNING' for other in service.store.all(db, KIND)):
            return None
        job.update(status='RUNNING', owner_pid=os.getpid(), revision=case['revision'],
                   started_at=now(), updated_at=now())
        with _ACTIVE_LOCK:
            _ACTIVE.add(job['attempt_id'])
        service.store.put(db, KIND, job)
        return job


def _safe_error(exc):
    message = str(exc)
    if message in FAILURE_MESSAGES.values():
        code = next(key for key, value in FAILURE_MESSAGES.items() if value == message)
        return code, message
    code = failure_code(exc)
    return code, FAILURE_MESSAGES[code]


def _execute(service, job):
    failure = None
    result = None
    try:
        with credential_scope(service.store.path):
            result = service.prepare_public_preview(job['id'], job['revision'], job['actor'])
    except Exception as exc:
        failure = exc
    except BaseException:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(job['attempt_id'])
        raise
    try:
        with service.lock, service.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            saved = _find(service, db, job['id'])
            case = service.store.get(db, 'case', job['id'])
            fingerprint, _ = _inputs(service, db, case)
            stale = fingerprint != job['input_fingerprint'] or (
                failure is not None and str(failure).startswith('Case changed'))
            code, message = ('STALE', _STALE) if stale else _safe_error(failure) if failure else ('', '')
            if saved and saved['attempt_id'] == job['attempt_id']:
                saved.update(status='STALE' if stale else 'FAILED' if failure else 'COMPLETE',
                             error=message, error_code=code, updated_at=now(), finished_at=now())
                service.store.put(db, KIND, saved)
        if stale:
            raise ValueError(_STALE)
        if failure is not None:
            raise ValueError(message) from failure
        return result
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(job['attempt_id'])


def prepare(service, case_id, revision, actor, manual=False):
    """Return a completed preview or the existing queued/running state, never duplicate it."""
    queue(service, case_id, revision, actor, manual)
    job = _claim(service, case_id)
    if job:
        return _execute(service, job)
    with service.store.connect() as db:
        case = service.store.get(db, 'case', case_id)
        state = status(service, db, case)
        if state and state['status'] == 'COMPLETE' and state['preview_current']:
            return case['public_reply_preview']
        return state


def run_next(service):
    with service.lock, service.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        _recover(service, db)
        pending = sorted((job for job in service.store.all(db, KIND) if job['status'] == 'QUEUED'),
                         key=lambda job: job['created_at'])
    if pending:
        job = _claim(service, pending[0]['id'])
        if job:
            return _execute(service, job)
    return None


def has_queued(service):
    with service.store.connect() as db:
        jobs = service.store.all(db, KIND)
        return any(job['status'] == 'QUEUED' for job in jobs) and not any(job['status'] == 'RUNNING' for job in jobs)
