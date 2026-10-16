import base64
import json
import httpx
from sidhu.config import Settings
from sidhu.core import Engine
from sidhu.memory import Memory

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def test_cli_and_regular_engine_commands_cannot_capture_without_desktop_approval(tmp_path):
    engine = Engine(Settings(screen_capture_enabled=True), Memory(tmp_path/'notes.db'))
    for command in ('capture screen', 'analyze screen'):
        result = engine.execute(command)
        assert not result.ok and 'desktop' in result.message and result.agent == 'Screen'


def test_screen_analysis_requires_fresh_client_consent_and_excludes_data_from_history(tmp_path, monkeypatch):
    settings = Settings(ai_base_url='https://vision.test/v1', ai_model='image-model', history_enabled=True, ai_context_enabled=True)
    engine = Engine(settings, Memory(tmp_path/'notes.db'))
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': 'Private visual answer'}}]})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    denied = engine.analyze_screen(PNG, 'Private visual question')
    assert not denied.ok and calls == []
    consent = engine.ai.vision_target()
    result = engine.analyze_screen(PNG, 'Private visual question', consent=consent)
    assert result.ok and result.agent == 'Vision'
    assert len(calls) == 1 and result.elapsed_ms >= 0
    assert engine.ai._turns == [] and not engine.memory.path.exists()
    raw = engine.activity.path.read_bytes()
    assert PNG not in raw
    assert b'Private visual question' not in raw and b'Private visual answer' not in raw
    assert engine.activity.list()[0][1] == 'analyze screen'
