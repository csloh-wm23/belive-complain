"""Public draft inputs and freshness, separate from case progress and delivery."""
import json

from belive.store import digest
from belive.workflow import complaint_level

VERSION = 3


def context(case, followups=()):
    return {
        'title': case['title'], 'report': case['description'], 'platform': case['platform'],
        'category': case['category'], 'complaint_level': complaint_level(case),
        'assessment_summary': (case.get('analysis') or {}).get('summary', ''),
        'public_followups': [
            {key: item.get(key, '') for key in ('id', 'text', 'source_url')}
            for item in list(followups)[-8:]
        ],
    }


def fingerprint(inputs):
    return digest(json.dumps(inputs, sort_keys=True, ensure_ascii=False))


def is_current(case, followups=()):
    preview = case.get('public_reply_preview') or {}
    return bool(
        preview.get('format_version') == VERSION
        and case.get('source_versions')
        and preview.get('source_version') == case['source_versions'][-1]
        and preview.get('input_fingerprint') == fingerprint(context(case, followups))
    )
