import json
import threading
import httpx
import pytest
from sidhu.ai import AIClient, AIError
from sidhu.config import Settings


def fake_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def make_client(context=False):
    return AIClient(Settings(ai_model='test-model', ai_context_enabled=context), threading.Event())


def test_opt_in_context_sends_previous_turns_and_clear_resets(monkeypatch):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'response'}}]})
    fake_http(monkeypatch, handler)
    client = make_client(context=True)
    client.chat('first question')
    client.chat('followup')
    assert [message['role'] for message in requests[1]['messages']] == ['system', 'user', 'assistant', 'user']
    assert requests[1]['messages'][1]['content'] == 'first question'
    client.clear()
    client.chat('fresh')
    assert len(requests[2]['messages']) == 2


def test_disabled_context_never_sends_prior_turns(monkeypatch):
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    fake_http(monkeypatch, handler)
    client = make_client()
    client.chat('private one')
    client.chat('two')
    assert len(payloads[1]['messages']) == 2
    assert client._turns == []


def test_provider_or_model_change_drops_prior_context(monkeypatch):
    payloads = []
    def handler(request):
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    fake_http(monkeypatch, handler)
    client = make_client(context=True)
    client.chat('first provider context')
    client.settings.ai_model = 'different-model'
    client.chat('new model')
    assert len(payloads[1]['messages']) == 2


def test_models_queries_actual_endpoint_without_requiring_selected_model(monkeypatch):
    def handler(request):
        assert request.method == 'GET'
        assert request.url.path == '/v1/models'
        return httpx.Response(200, json={'data': [{'id': 'model-a'}, {'id': 'model-b'}]})
    fake_http(monkeypatch, handler)
    client = AIClient(Settings(), threading.Event())
    assert client.models() == ['model-a', 'model-b']


@pytest.mark.parametrize('url', ['http://example.com/v1', 'https://user:pass@example.com/v1', 'https://example.com/v1?key=secret', 'https://example.com/v1#fragment', 'https:///v1', 'http://localhost:invalid/v1'])
def test_invalid_or_credential_bearing_endpoint_never_sends_request(monkeypatch, url):
    fake_http(monkeypatch, lambda _: pytest.fail('Invalid endpoint must not be requested'))
    client = make_client()
    client.settings.ai_base_url = url
    with pytest.raises(AIError):
        client.chat('hello')


def test_cancelled_or_cleared_response_never_enters_context(monkeypatch):
    client = make_client(context=True)
    def handler(request):
        client.clear()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'late answer'}}]})
    fake_http(monkeypatch, handler)
    with pytest.raises(AIError, match='cleared'):
        client.chat('hello')
    assert client._turns == []


def test_response_byte_limit_and_prompt_limit(monkeypatch):
    import sidhu.ai as module
    monkeypatch.setattr(module, 'MAX_RESPONSE_BYTES', 10)
    fake_http(monkeypatch, lambda _: httpx.Response(200, content=b'a' * 11))
    client = make_client()
    with pytest.raises(AIError, match='limit'):
        client.chat('hello')
    with pytest.raises(AIError, match='8,000'):
        client.chat('a' * 8001)


def test_http_status_and_malformed_or_tool_only_response_are_not_success(monkeypatch):
    replies = iter([httpx.Response(401, text='secret-provider-detail'), httpx.Response(200, content=b'not json'), httpx.Response(200, json={'choices': [{'message': {'tool_calls': []}}]})])
    fake_http(monkeypatch, lambda _: next(replies))
    client = make_client()
    for expected in ('HTTP 401', 'invalid JSON', 'unsupported chat response'):
        with pytest.raises(AIError, match=expected) as error:
            client.chat('hello')
        assert 'secret-provider-detail' not in str(error.value)


def test_context_has_bounded_turns_and_characters(monkeypatch):
    fake_http(monkeypatch, lambda _: httpx.Response(200, json={'choices': [{'message': {'content': 'a' * 2000}}]}))
    client = make_client(context=True)
    for _ in range(12):
        client.chat('p' * 1000)
    assert len(client._turns) <= 16
    assert sum(len(turn['content']) for turn in client._turns) <= 16000


def test_cleared_generation_prevents_old_context_going_to_new_provider(monkeypatch):
    destinations = []
    def handler(request):
        destinations.append(str(request.url))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    fake_http(monkeypatch, handler)
    client = make_client(context=True)
    client.settings.ai_base_url = 'https://old-provider.test/v1'
    client.chat('private old-provider context')
    original_request = client._request
    def reconfigure_before_dispatch(*args, **kwargs):
        client.clear()
        client.settings.ai_base_url = 'https://new-provider.test/v1'
        return original_request(*args, **kwargs)
    monkeypatch.setattr(client, '_request', reconfigure_before_dispatch)
    with pytest.raises(AIError, match='cleared'):
        client.chat('followup')
    assert destinations == ['https://old-provider.test/v1/chat/completions']


def test_compressed_response_is_refused_before_decompression(monkeypatch):
    # MockTransport eagerly decodes constructed response bodies; use an unconsumed stream instead.
    def handler(request):
        assert request.headers['accept-encoding'] == 'identity'
        return httpx.Response(200, headers={'content-encoding': 'gzip'}, stream=httpx.ByteStream(b'not decoded'))
    fake_http(monkeypatch, handler)
    with pytest.raises(AIError, match='compression'):
        make_client().chat('hello')


def test_elapsed_response_budget_stops_slow_stream(monkeypatch):
    import sidhu.ai as module
    ticks = iter([0, 31])
    monkeypatch.setattr(module.time, 'monotonic', lambda: next(ticks))
    fake_http(monkeypatch, lambda _: httpx.Response(200, stream=httpx.ByteStream(b'{}')))
    with pytest.raises(AIError, match='elapsed response time'):
        make_client().chat('hello')


def test_runtime_reconfiguration_is_atomic_with_request_snapshot(monkeypatch):
    switched, release, sent = threading.Event(), threading.Event(), threading.Event()
    class ObservedSettings(Settings):
        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == 'ai_base_url' and self.__dict__.get('armed'):
                switched.set()
                assert release.wait(3)
    settings = ObservedSettings(ai_model='old', ai_base_url='https://old.test/v1', ai_key_env='OLD_TEST_AI_KEY')
    client = AIClient(settings, threading.Event())
    requests, errors = [], []
    def handler(request):
        requests.append((request.url.host, request.headers.get('authorization')))
        sent.set()
        return httpx.Response(200, json={'choices': [{'message': {'content': 'answer'}}]})
    fake_http(monkeypatch, handler)
    monkeypatch.setenv('OLD_TEST_AI_KEY', 'old-fake-key')
    monkeypatch.setenv('NEW_TEST_AI_KEY', 'new-fake-key')
    settings.armed = True
    change = threading.Thread(target=lambda: client.reconfigure(base_url='https://new.test/v1', model='new', key_env='NEW_TEST_AI_KEY', keep_context=False))
    def chat():
        try:
            client.chat('hello')
        except Exception as exc:
            errors.append(exc)
    request = threading.Thread(target=chat)
    change.start()
    try:
        assert switched.wait(3)
        request.start()
        assert not sent.wait(0.05)
    finally:
        release.set()
        change.join(3)
        request.join(3)
    assert not change.is_alive() and not request.is_alive()
    assert not errors
    assert requests == [('new.test', 'Bearer new-fake-key')]
