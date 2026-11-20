"""Key-based access to hosted models through OpenRouter."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from belive.store import redact

DEFAULT_MODEL = 'nousresearch/hermes-4-405b'
ENDPOINT = 'https://openrouter.ai/api/v1/chat/completions'
STATUS_CODES = {
    401: 'OPENROUTER_KEY_REJECTED',
    402: 'OPENROUTER_CREDITS_REQUIRED',
    403: 'OPENROUTER_KEY_REJECTED',
    404: 'OPENROUTER_MODEL_UNAVAILABLE',
    429: 'OPENROUTER_RATE_LIMITED',
}
LOCAL_FIELDS = {
    'tenant_id', 'condo_id', 'unit_ref', 'case_id', 'source', 'property_version',
    'input_id', 'verified_by', 'at', 'created_at', 'updated_at', 'expires_at',
}


def _prompt_context(value):
    if isinstance(value, dict):
        return {
            key: item if key == 'id' else _prompt_context(item)
            for key, item in value.items() if key not in LOCAL_FIELDS
        }
    if isinstance(value, list):
        return [_prompt_context(item) for item in value]
    return redact(value) if isinstance(value, str) else value


def generate(settings, messages, context, examples, schema):
    prompt = {'context': _prompt_context(context),
              'reviewed_examples': [{'id': item['id'], 'text': redact(item['text'])[:320]} for item in examples]}
    response_format = {'type': 'json_object'}
    if schema:
        response_format = {'type': 'json_schema', 'json_schema': {
            'name': 'belive_support', 'strict': True, 'schema': schema,
        }}
    system = messages[0]['content'] + (
        '\nReviewed examples are writing style only. Do not use them as facts, policies or promises.'
    )
    payload = {
        'model': settings.llm_model,
        'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': json.dumps(prompt)}],
        'response_format': response_format,
        'reasoning': {'enabled': False},
        'provider': {'require_parameters': True, 'data_collection': 'deny', 'zdr': True},
        'max_tokens': 2500,
        'stream': False,
    }
    request = Request(ENDPOINT, json.dumps(payload).encode(),
                      {'Content-Type': 'application/json', 'Accept': 'application/json'})
    request.add_unredirected_header('Authorization', 'Bearer ' + settings.llm_api_key)
    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as exc:
        with exc:
            raise RuntimeError(STATUS_CODES.get(exc.code, 'OPENROUTER_CONNECTION_FAILED')) from None
    except (URLError, TimeoutError):
        raise RuntimeError('OPENROUTER_CONNECTION_FAILED') from None

    try:
        choice = result['choices'][0]
        reply = choice['message']['content']
    except (KeyError, IndexError, TypeError):
        raise ValueError('AI_INVALID_JSON') from None
    if choice.get('finish_reason') != 'stop' or not isinstance(reply, str) or not reply.strip():
        raise ValueError('AI_INVALID_JSON')
    return {'text': reply}
