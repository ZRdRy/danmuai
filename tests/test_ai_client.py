import threading
from unittest.mock import patch, MagicMock

from app.ai_client import AiWorker
from app.config_store import ConfigStore


class FakeConfig:
    def get(self, key, default=""):
        return default

    def get_int(self, key, default=0):
        return default

    def get_float(self, key, default=0.0):
        return default

    def get_api_key(self):
        return "sk-test-key"

    def get_default_model_id(self):
        return ""

    def get_custom_models(self):
        return []


def test_get_http_client_returns_same_instance_per_thread():
    worker = AiWorker(FakeConfig())
    client1 = worker._get_http_client()
    client2 = worker._get_http_client()
    assert client1 is client2
    worker.close()


def test_close_cleans_up_client():
    worker = AiWorker(FakeConfig())
    client = worker._get_http_client()
    assert client is not None
    worker.close()
    assert worker._thread_local.client is None


def test_close_is_safe_when_no_client():
    worker = AiWorker(FakeConfig())
    worker.close()
    assert not hasattr(worker._thread_local, 'client') or worker._thread_local.client is None


def test_request_doubao_uses_thread_local_client():
    worker = AiWorker(FakeConfig())
    with patch.object(worker, '_stream_doubao', return_value=("test", 100, 50)) as mock_stream:
        with patch.object(worker, '_emit_safe') as mock_emit:
            worker._request_doubao("data:image/jpeg;base64,abc", "sys", "user", "p1", 1, 1, 1.0, 0)
            mock_stream.assert_called_once()
            http_client = mock_stream.call_args[0][0]
            assert http_client is worker._get_http_client()
    worker.close()


def test_request_openai_uses_thread_local_client():
    worker = AiWorker(FakeConfig())
    with patch.object(worker, '_stream_openai', return_value=("test", 100, 50)) as mock_stream:
        with patch.object(worker, '_emit_safe') as mock_emit:
            worker._request_openai("data:image/jpeg;base64,abc", "sys", "user", "p1", 1, 1, 1.0, 0)
            mock_stream.assert_called_once()
            http_client = mock_stream.call_args[0][0]
            assert http_client is worker._get_http_client()
    worker.close()


def test_request_doubao_rebuilds_client_on_exception():
    worker = AiWorker(FakeConfig())
    first_client = worker._get_http_client()

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("connection broken")
        return ("recovered", 100, 50)

    with patch.object(worker, '_stream_doubao', side_effect=side_effect):
        with patch.object(worker, '_emit_safe'):
            worker._request_doubao("data:image/jpeg;base64,abc", "sys", "user", "p1", 1, 1, 1.0, 0)

    new_client = worker._get_http_client()
    assert new_client is not first_client
    assert call_count == 2
    worker.close()


def test_request_openai_rebuilds_client_on_exception():
    worker = AiWorker(FakeConfig())
    first_client = worker._get_http_client()

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("connection broken")
        return ("recovered", 100, 50)

    with patch.object(worker, '_stream_openai', side_effect=side_effect):
        with patch.object(worker, '_emit_safe'):
            worker._request_openai("data:image/jpeg;base64,abc", "sys", "user", "p1", 1, 1, 1.0, 0)

    new_client = worker._get_http_client()
    assert new_client is not first_client
    assert call_count == 2
    worker.close()


def test_different_threads_get_different_clients():
    worker = AiWorker(FakeConfig())
    results = {}

    def get_client(name):
        results[name] = worker._get_http_client()

    t1 = threading.Thread(target=get_client, args=("t1",))
    t2 = threading.Thread(target=get_client, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["t1"] is not results["t2"]
    worker.close()
