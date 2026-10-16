import base64
from dataclasses import FrozenInstanceError, replace
import json
import threading

import httpx
import pytest

from sidhu.ai import AIClient, AIError, MAX_IMAGE_BYTES, VISION_SYSTEM, VisionTarget
from sidhu.config import Settings


# A one-pixel PNG; tests never capture or transmit a real desktop.
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def client(context=False):
    return AIClient(Settings(ai_base_url='https://vision.test/v1', ai_model='vision-model', ai_key_env='VISION_TEST_KEY', ai_context_enabled=context), threading.Event())


def fake_http(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))


def answer(text='Image description'):
    return httpx.Response(200, json={'choices': [{'message': {'content': text}}]})


def test_target_is_immutable_metadata_without_key_values(monkeypatch):
    monkeypatch.setenv('VISION_TEST_KEY', 'fake-private-key-value')
    fake_http(monkeypatch, lambda _: pytest.fail('Preparing an approval must not make a request'))
    target = client().vision_target()
    assert (target.base_url, target.host, target.model, target.key_env) == ('https://vision.test/v1', 'vision.test', 'vision-model', 'VISION_TEST_KEY')
    assert 'fake-private-key-value' not in repr(target)
    with pytest.raises(FrozenInstanceError):
        target.model = 'other'


@pytest.mark.parametrize('consent_kind', ['missing', 'object', 'foreign', 'copied', 'constructed'])
def test_absent_forged_or_foreign_approval_never_sends(monkeypatch, consent_kind):
    instance = client()
    fake_http(monkeypatch, lambda _: pytest.fail('Unapproved image must not be sent'))
    target = instance.vision_target()
    candidates = {
        'missing': None,
        'object': object(),
        'foreign': client().vision_target(),
        'copied': replace(target),
        'constructed': VisionTarget(target.base_url, target.model, target.key_env, target.generation),
    }
    with pytest.raises(AIError, match='approval is required'):
        instance.analyze_image(PNG, 'Describe this image', consent=candidates[consent_kind])


@pytest.mark.parametrize(('png', 'prompt', 'expected'), [
    (b'not png', 'Describe', 'PNG image'),
    (bytearray(PNG), 'Describe', 'PNG image'),
    (PNG + b'x' * MAX_IMAGE_BYTES, 'Describe', '4 MiB'),
    (PNG, '', '8,000'),
    (PNG, '  ', '8,000'),
    (PNG, 'x' * 8001, '8,000'),
    (PNG, None, '8,000'),
])
def test_invalid_images_and_questions_are_rejected_before_network(monkeypatch, png, prompt, expected):
    fake_http(monkeypatch, lambda _: pytest.fail('Invalid image request must not be sent'))
    instance = client()
    with pytest.raises(AIError, match=expected):
        instance.analyze_image(png, prompt, consent=instance.vision_target())


def test_image_payload_is_one_time_and_separate_from_text_context(monkeypatch):
    requests = []
    def handler(request):
        requests.append(json.loads(request.content))
        return answer('Visible image text' if len(requests) == 2 else 'Chat answer')
    fake_http(monkeypatch, handler)
    instance = client(context=True)
    instance.chat('Earlier private conversation')
    old_turns = [dict(turn) for turn in instance._turns]
    assert instance.analyze_image(PNG, 'What is visible?', consent=instance.vision_target()) == 'Visible image text'
    assert instance._turns == old_turns
    image_payload = requests[1]
    assert image_payload['model'] == 'vision-model'
    assert len(image_payload['messages']) == 2
    assert image_payload['messages'][0] == {'role': 'system', 'content': VISION_SYSTEM}
    assert 'one-time image' in VISION_SYSTEM and 'no continuous or live screen access' in VISION_SYSTEM
    blocks = image_payload['messages'][1]['content']
    assert blocks[0] == {'type': 'text', 'text': 'What is visible?'}
    assert base64.b64decode(blocks[1]['image_url']['url'].split(',', 1)[1]) == PNG
    assert blocks[1]['image_url']['url'].startswith('data:image/png;base64,')
    instance.chat('Follow up on the earlier conversation')
    assert all(isinstance(message['content'], str) for message in requests[2]['messages'])
    assert 'What is visible?' not in json.dumps(requests[2])
    assert 'Visible image text' not in json.dumps(requests[2])


@pytest.mark.parametrize('change', ['clear', 'reconfigure', 'ai_base_url', 'ai_model', 'ai_key_env'])
def test_provider_or_conversation_change_expires_approval(monkeypatch, change):
    fake_http(monkeypatch, lambda _: pytest.fail('Expired approval must not send image bytes'))
    instance = client()
    target = instance.vision_target()
    if change == 'clear':
        instance.clear()
    elif change == 'reconfigure':
        instance.reconfigure(base_url=target.base_url, model=target.model, key_env=target.key_env, keep_context=False)
    else:
        setattr(instance.settings, change, 'https://other.test/v1' if change == 'ai_base_url' else 'changed')
    with pytest.raises(AIError, match='approval expired'):
        instance.analyze_image(PNG, 'Describe', consent=target)


@pytest.mark.parametrize('status', [200, 401])
def test_one_approval_authorizes_only_one_dispatch_even_if_provider_fails(monkeypatch, status):
    requests = []
    def handler(request):
        requests.append(request)
        return answer() if status == 200 else httpx.Response(status)
    fake_http(monkeypatch, handler)
    instance = client()
    target = instance.vision_target()
    if status == 200:
        assert instance.analyze_image(PNG, 'Describe', consent=target) == 'Image description'
    else:
        with pytest.raises(AIError, match='HTTP 401'):
            instance.analyze_image(PNG, 'Describe', consent=target)
    with pytest.raises(AIError, match='approval is required'):
        instance.analyze_image(PNG, 'Describe again', consent=target)
    assert len(requests) == 1


def test_reconfiguration_between_snapshot_and_request_never_sends(monkeypatch):
    fake_http(monkeypatch, lambda _: pytest.fail('Changed destination must not receive an image'))
    instance = client()
    target = instance.vision_target()
    original_request = instance._request
    def changed_before_request(*args, **kwargs):
        instance.reconfigure(base_url='https://other.test/v1', model='other-model', key_env='OTHER_KEY', keep_context=False)
        return original_request(*args, **kwargs)
    monkeypatch.setattr(instance, '_request', changed_before_request)
    with pytest.raises(AIError, match='cleared|approval expired'):
        instance.analyze_image(PNG, 'Describe', consent=target)


def test_provider_change_while_http_client_is_created_is_caught_at_dispatch(monkeypatch):
    instance = client()
    target = instance.vision_target()
    original = httpx.Client
    def changed_client(**kwargs):
        instance.settings.ai_base_url = 'https://other.test/v1'
        return original(transport=httpx.MockTransport(lambda _: pytest.fail('Stale approved provider must not receive bytes')), **kwargs)
    monkeypatch.setattr(httpx, 'Client', changed_client)
    with pytest.raises(AIError, match='approval expired'):
        instance.analyze_image(PNG, 'Describe', consent=target)


def test_parallel_attempts_cannot_reuse_one_approval(monkeypatch):
    instance = client()
    target = instance.vision_target()
    barrier = threading.Barrier(2)
    original_request = instance._request
    def synchronized_request(*args, **kwargs):
        barrier.wait(timeout=3)
        return original_request(*args, **kwargs)
    monkeypatch.setattr(instance, '_request', synchronized_request)
    requests, results, errors = [], [], []
    def handler(request):
        requests.append(request)
        return answer()
    fake_http(monkeypatch, handler)
    def run():
        try:
            results.append(instance.analyze_image(PNG, 'Describe', consent=target))
        except AIError as exc:
            errors.append(str(exc))
    workers = [threading.Thread(target=run) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(3)
    assert not any(worker.is_alive() for worker in workers)
    assert len(requests) == 1
    assert results == ['Image description']
    assert len(errors) == 1 and 'approval is required' in errors[0]


@pytest.mark.parametrize('change', ['cancel', 'clear', 'reconfigure'])
def test_late_response_is_discarded_without_context(monkeypatch, change):
    instance = client(context=True)
    def handler(request):
        if change == 'cancel':
            instance.cancelled.set()
        elif change == 'clear':
            instance.clear()
        else:
            instance.reconfigure(base_url='https://other.test/v1', model='other-model', key_env='OTHER_KEY', keep_context=True)
        return answer('Private image answer')
    fake_http(monkeypatch, handler)
    with pytest.raises(AIError, match='discarded'):
        instance.analyze_image(PNG, 'Private image question', consent=instance.vision_target())
    assert instance._turns == []


def test_cancel_before_sending_preserves_no_image_context(monkeypatch):
    fake_http(monkeypatch, lambda _: pytest.fail('Cancelled image must not be sent'))
    instance = client()
    target = instance.vision_target()
    instance.cancelled.set()
    with pytest.raises(AIError, match='cancelled before sending'):
        instance.analyze_image(PNG, 'Describe', consent=target)
    assert instance._turns == []


@pytest.mark.parametrize('payload', [{}, {'choices': [{'message': {'tool_calls': []}}]}, {'choices': [{'message': {'content': []}}]}, {'choices': [{'message': {'content': ' '}}]}])
def test_unsupported_image_responses_do_not_claim_success(monkeypatch, payload):
    fake_http(monkeypatch, lambda _: httpx.Response(200, json=payload))
    instance = client()
    with pytest.raises(AIError, match='unsupported image response|no image text response'):
        instance.analyze_image(PNG, 'Describe', consent=instance.vision_target())
    assert instance._turns == []


def test_image_response_uses_existing_byte_limit(monkeypatch):
    import sidhu.ai as module
    monkeypatch.setattr(module, 'MAX_RESPONSE_BYTES', 10)
    fake_http(monkeypatch, lambda _: httpx.Response(200, content=b'x' * 11))
    instance = client()
    with pytest.raises(AIError, match='1 MiB'):
        instance.analyze_image(PNG, 'Describe', consent=instance.vision_target())


def test_image_request_does_not_follow_redirects(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request.url.host)
        return httpx.Response(307, headers={'Location': 'https://unapproved.test/receive'})
    fake_http(monkeypatch, handler)
    instance = client()
    with pytest.raises(AIError, match='HTTP 307'):
        instance.analyze_image(PNG, 'Describe', consent=instance.vision_target())
    assert requests == ['vision.test']


def test_local_provider_needs_no_api_key_and_answer_is_bounded(monkeypatch):
    monkeypatch.delenv('VISION_TEST_KEY', raising=False)
    def handler(request):
        assert request.url.host == 'localhost'
        assert 'authorization' not in request.headers
        return answer('x' * 17000)
    fake_http(monkeypatch, handler)
    instance = client()
    instance.settings.ai_base_url = 'http://localhost:11434/v1'
    assert len(instance.analyze_image(PNG, 'Describe', consent=instance.vision_target())) == 16000


@pytest.mark.parametrize('base', ['http://remote.test/v1', 'https://user:password@vision.test/v1', 'https://vision.test/v1?key=value'])
def test_invalid_provider_cannot_issue_approval(base):
    instance = client()
    instance.settings.ai_base_url = base
    with pytest.raises(AIError):
        instance.vision_target()


def test_no_model_cannot_issue_approval():
    instance = client()
    instance.settings.ai_model = ''
    with pytest.raises(AIError, match='vision-capable model'):
        instance.vision_target()


def test_waiting_for_provider_headers_does_not_lock_settings(monkeypatch):
    instance = client()
    target = instance.vision_target()
    started, release, changed = threading.Event(), threading.Event(), threading.Event()
    requests, errors = [], []
    def handler(request):
        requests.append(request.url.host)
        started.set()
        assert release.wait(3)
        return answer()
    fake_http(monkeypatch, handler)
    def send():
        try:
            instance.analyze_image(PNG, 'Describe', consent=target)
        except AIError as exc:
            errors.append(str(exc))
    worker = threading.Thread(target=send)
    worker.start()
    assert started.wait(3)
    def update():
        instance.reconfigure(base_url='https://new.test/v1', model='new', key_env='NEW_KEY', keep_context=False)
        changed.set()
    update_worker = threading.Thread(target=update)
    update_worker.start()
    try:
        assert changed.wait(0.5), 'Settings blocked on network headers'
    finally:
        release.set()
        worker.join(3)
        update_worker.join(3)
    assert requests == ['vision.test']
    assert len(errors) == 1 and 'discarded' in errors[0]
