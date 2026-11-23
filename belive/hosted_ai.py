"""Direct JSON completions for supported hosted models."""
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from belive.store import redact

DEFAULT_MODELS = {'openai': 'gpt-6-luna', 'openrouter': 'nousresearch/hermes-4-405b'}
ENDPOINTS = {
    'openai': 'https://api.openai.com/v1/chat/completions',
    'openrouter': 'https://openrouter.ai/api/v1/chat/completions',
}
STATUS_CODES = {
    401: 'KEY_REJECTED',
    402: 'CREDITS_REQUIRED',
    403: 'KEY_REJECTED',
    404: 'MODEL_UNAVAILABLE',
    429: 'RATE_LIMITED',
}
FAILURE_MESSAGES = {
    f'{provider.upper()}_{code}': message.format(name=name)
    for provider, name in {'openai': 'OpenAI', 'openrouter': 'OpenRouter'}.items()
    for code, message in {
        'KEY_REJECTED': '{name} rejected the API key or its model permissions. Check BELIVE_AI_KEY and restart.',
        'CREDITS_REQUIRED': '{name} requires available credits for the configured key.',
        'MODEL_UNAVAILABLE': '{name} could not serve the configured model. Check the model ID and project access.',
        'RATE_LIMITED': '{name} reached a usage or credit limit. Check the project balance and rate limits.',
        'CONNECTION_FAILED': 'BeLive could not complete the {name} request. Check Internet access and provider status.',
    }.items()
}
LOCAL_FIELDS = {
    'tenant_id', 'condo_id', 'unit_ref', 'case_id', 'source', 'property_version',
    'input_id', 'verified_by', 'at', 'created_at', 'updated_at', 'expires_at',
}


def uses_direct_api(settings):
    provider = settings.llm_provider
    return getattr(settings,'agent_engine','hermes')=='direct' and provider in ENDPOINTS


def _prompt_context(value):
    if isinstance(value, dict):
        return {
            key: item if key == 'id' else _prompt_context(item)
            for key, item in value.items() if key not in LOCAL_FIELDS
        }
    if isinstance(value, list):
        return [_prompt_context(item) for item in value]
    return redact(value) if isinstance(value, str) else value


def generate(settings, messages, context, examples, schema, images=None, *, home=None, observer=None, role='', native_tools=None, dispatch=None):
    prompt = {'context': _prompt_context(context),
              'reviewed_examples': [{'id': item['id'], 'text': redact(item['text'])[:320]} for item in examples]}
    if getattr(settings,'agent_engine','hermes')=='hermes':
        from belive.hermes_native import native_request
        actual=[{'role':'system','content':messages[0]['content']},{'role':'user','content':json.dumps(prompt)}]
        if images:actual[1]['content']=[{'type':'text','text':json.dumps(prompt)}]+[{'type':'image_url','image_url':{'url':x,'detail':'auto'}} for x in images[:3]]
        return native_request(actual,settings,tools=native_tools or [],dispatch=dispatch,home=home,
            examples=[{'version_id':x['id'],'approved_reply':redact(x['text'])[:320]} for x in examples],
            response_schema=schema,observer=observer,role=role,max_steps=6)
    if getattr(settings,'agent_engine','hermes')!='direct':raise ValueError('AI_UNKNOWN_AGENT_ENGINE')
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
        'stream': False,
    }
    if images:
        content=[{'type':'text','text':json.dumps(prompt)}]
        for item in images[:3]:content.append({'type':'image_url','image_url':{'url':item,'detail':'auto'}})
        payload['messages'][1]['content']=content
    provider = settings.llm_provider
    if provider == 'openai':
        payload.update(reasoning_effort='none', max_completion_tokens=2500, service_tier='default', store=False)
    else:
        payload.update(reasoning={'enabled': False}, max_tokens=2500,
                       provider={'require_parameters': True, 'data_collection': 'deny', 'zdr': True})
    result = request_json(settings, ENDPOINTS[provider], payload)

    try:
        choice = result['choices'][0]
        reply = choice['message']['content']
    except (KeyError, IndexError, TypeError):
        raise ValueError('AI_INVALID_JSON') from None
    if choice.get('finish_reason') != 'stop' or not isinstance(reply, str) or not reply.strip():
        raise ValueError('AI_INVALID_JSON')
    return {'text': reply}


def request_json(settings, endpoint, payload):
    provider = settings.llm_provider
    request = Request(endpoint, json.dumps(payload).encode(),
                      {'Content-Type': 'application/json', 'Accept': 'application/json'})
    request.add_unredirected_header('Authorization', 'Bearer ' + settings.llm_api_key)
    try:
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    except HTTPError as exc:
        with exc:
            code = STATUS_CODES.get(exc.code, 'CONNECTION_FAILED')
            raise RuntimeError(f'{provider.upper()}_{code}') from None
    except (URLError, TimeoutError):
        raise RuntimeError(f'{provider.upper()}_CONNECTION_FAILED') from None
