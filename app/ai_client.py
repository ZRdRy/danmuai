import json
import threading

import httpx
from PyQt6.QtCore import QObject, pyqtSignal

from app.config_store import ConfigStore
from app.translations import tr


class AiWorker(QObject):
    finished = pyqtSignal(str, str, int, int, float, int, int, int)
    error = pyqtSignal(str, str, int, int, float, int, int, int)

    def __init__(self, config: ConfigStore):
        super().__init__()
        self.config = config
        self._stopping = False
        self._thread_local = threading.local()
        self._client_lock = threading.Lock()
        self._clients: set[httpx.Client] = set()

    def _get_http_client(self) -> httpx.Client:
        if not hasattr(self._thread_local, "client") or self._thread_local.client is None:
            try:
                client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0), http2=True)
            except Exception:
                client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0))
            self._thread_local.client = client
            with self._client_lock:
                self._clients.add(client)
        return self._thread_local.client

    def mark_stopping(self):
        self._stopping = True

    def reset_stopping(self):
        self._stopping = False

    def _get_model_config(self) -> dict:
        default_model_id = self.config.get_default_model_id()
        if not default_model_id:
            return {}
        custom_models = self.config.get_custom_models()
        for model in custom_models:
            if model.get("modelId") == default_model_id:
                return model
        return {}

    def _request(
        self,
        image_data_uri: str,
        system_pt: str,
        user_pt: str,
        persona_id: str = "",
        request_round: int = 0,
        screenshot_id: int = 0,
        captured_at: float = 0.0,
        scene_generation: int = 0,
    ):
        if self._stopping:
            return
        model_config = self._get_model_config()
        model_mode = model_config.get("mode", "")
        api_mode = model_mode if model_mode else self.config.get("api_mode", "doubao")
        if api_mode == "doubao":
            self._request_doubao(
                image_data_uri,
                system_pt,
                user_pt,
                persona_id,
                request_round,
                screenshot_id,
                captured_at,
                scene_generation,
            )
        else:
            self._request_openai(
                image_data_uri,
                system_pt,
                user_pt,
                persona_id,
                request_round,
                screenshot_id,
                captured_at,
                scene_generation,
            )

    def _emit_safe(self, signal_name, *args):
        if self._stopping:
            return
        try:
            getattr(self, signal_name).emit(*args)
        except RuntimeError:
            pass

    def _emit_result(
        self,
        signal_name: str,
        message: str,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ):
        self._emit_safe(
            signal_name,
            message,
            persona_id,
            request_round,
            screenshot_id,
            captured_at,
            scene_generation,
            input_tokens,
            output_tokens,
        )

    def _request_doubao(
        self,
        image_data_uri: str,
        system_pt: str,
        user_pt: str,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
    ):
        model_config = self._get_model_config()
        model_endpoint = model_config.get("endpoint", "")
        model_api_key = model_config.get("apiKey", "")
        endpoint = model_endpoint if model_endpoint else self.config.get("api_endpoint", "https://ark.cn-beijing.volces.com/api/v3")
        api_key = model_api_key if model_api_key else self.config.get_api_key()
        model = self.config.get_default_model_id() or self.config.get("model", "doubao-seed-1-6-flash-250828")
        temperature = self.config.get_float("temperature", 0.7)
        max_tokens = self.config.get_int("max_tokens", 50)
        use_thinking = self.config.get("use_thinking", "0") == "1"

        if not api_key:
            self._emit_result("error", tr("ai.error_api_key_missing"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
            return

        input_messages = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_data_uri},
                    {"type": "input_text", "text": user_pt},
                ],
            }
        ]

        data = {
            "model": model,
            "input": input_messages,
            "stream": True,
        }
        if system_pt:
            data["instructions"] = system_pt
        if temperature:
            data["temperature"] = temperature
        if use_thinking:
            data["thinking"] = {"type": "enabled"}
            if max_tokens and max_tokens < 1024:
                data["max_output_tokens"] = 1024
            elif max_tokens:
                data["max_output_tokens"] = max_tokens
        else:
            data["thinking"] = {"type": "disabled"}
            if max_tokens:
                data["max_output_tokens"] = max_tokens

        url = f"{endpoint}/responses"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        http_client = self._get_http_client()

        for attempt in range(2):
            try:
                text, input_tokens, output_tokens = self._stream_doubao(http_client, url, headers, data)
                if text:
                    self._emit_result("finished", text.strip(), persona_id, request_round, screenshot_id, captured_at, scene_generation, input_tokens, output_tokens)
                else:
                    self._emit_result("error", tr("ai.error_empty_response"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
                return
            except httpx.TimeoutException:
                if attempt < 1:
                    continue
                self._emit_result("error", tr("ai.error_timeout"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    msg = tr("ai.error_auth_failed")
                elif e.response.status_code == 429:
                    msg = tr("ai.error_rate_limited")
                elif e.response.status_code == 402:
                    msg = tr("ai.error_insufficient_balance")
                elif e.response.status_code == 404:
                    msg = tr("ai.error_model_not_found")
                elif e.response.status_code == 504:
                    msg = tr("ai.error_gateway_timeout")
                else:
                    msg = tr("ai.error_http_hidden").format(status_code=e.response.status_code)
                self._emit_result("error", msg, persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
                return
            except Exception as e:
                if attempt < 1:
                    if hasattr(self._thread_local, "client") and self._thread_local.client is not None:
                        try:
                            self._thread_local.client.close()
                        except Exception:
                            pass
                        with self._client_lock:
                            self._clients.discard(self._thread_local.client)
                        self._thread_local.client = None
                    http_client = self._get_http_client()
                    continue
                self._emit_result("error", tr("ai.error_request_failed").format(error=e), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)

    def _stream_doubao(self, http_client, url: str, headers: dict, data: dict) -> tuple[str, int, int]:
        collected = []
        summary_parts = []
        input_tokens = 0
        output_tokens = 0
        with http_client.stream("POST", url, headers=headers, json=data) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if self._stopping:
                    break
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    continue
                try:
                    chunk = json.loads(payload)
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "response.output_text.delta":
                        delta = chunk.get("delta", "")
                        if delta:
                            collected.append(delta)
                    elif chunk_type == "response.reasoning_summary_text.delta":
                        delta = chunk.get("delta", "")
                        if delta:
                            summary_parts.append(delta)
                    elif chunk_type == "response.completed":
                        usage = chunk.get("response", {}).get("usage", {})
                        if usage:
                            input_tokens = usage.get("input_tokens", 0)
                            output_tokens = usage.get("output_tokens", 0)
                except (json.JSONDecodeError, KeyError):
                    continue
        text = "".join(collected)
        if not text and summary_parts:
            text = "".join(summary_parts)
        return text, input_tokens, output_tokens

    def _request_openai(
        self,
        image_data_uri: str,
        system_pt: str,
        user_pt: str,
        persona_id: str,
        request_round: int,
        screenshot_id: int,
        captured_at: float,
        scene_generation: int,
    ):
        model_config = self._get_model_config()
        model_endpoint = model_config.get("endpoint", "")
        model_api_key = model_config.get("apiKey", "")
        endpoint = model_endpoint if model_endpoint else self.config.get("api_endpoint", "https://ark.cn-beijing.volces.com/api/v3")
        api_key = model_api_key if model_api_key else self.config.get_api_key()
        model = self.config.get_default_model_id() or self.config.get("model", "doubao-seed-1-6-flash-250828")
        temperature = self.config.get_float("temperature", 0.7)
        max_tokens = self.config.get_int("max_tokens", 50)

        if not api_key:
            self._emit_result("error", tr("ai.error_api_key_missing"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
            return

        http_client = self._get_http_client()

        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_pt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_pt},
                        {"type": "image_url", "image_url": {"url": image_data_uri}},
                    ],
                },
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        url = f"{endpoint}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(2):
            try:
                text, input_tokens, output_tokens = self._stream_openai(http_client, url, headers, data)
                if text:
                    self._emit_result("finished", text.strip(), persona_id, request_round, screenshot_id, captured_at, scene_generation, input_tokens, output_tokens)
                else:
                    self._emit_result("error", tr("ai.error_empty_response"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
                return
            except httpx.TimeoutException:
                if attempt < 1:
                    continue
                self._emit_result("error", tr("ai.error_timeout"), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    msg = tr("ai.error_auth_failed")
                elif e.response.status_code == 429:
                    msg = tr("ai.error_rate_limited")
                elif e.response.status_code == 402:
                    msg = tr("ai.error_insufficient_balance")
                elif e.response.status_code == 404:
                    msg = tr("ai.error_model_not_found")
                elif e.response.status_code == 504:
                    msg = tr("ai.error_gateway_timeout")
                else:
                    msg = tr("ai.error_http_hidden").format(status_code=e.response.status_code)
                self._emit_result("error", msg, persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)
                return
            except Exception as e:
                if attempt < 1:
                    if hasattr(self._thread_local, "client") and self._thread_local.client is not None:
                        try:
                            self._thread_local.client.close()
                        except Exception:
                            pass
                        with self._client_lock:
                            self._clients.discard(self._thread_local.client)
                        self._thread_local.client = None
                    http_client = self._get_http_client()
                    continue
                self._emit_result("error", tr("ai.error_request_failed").format(error=e), persona_id, request_round, screenshot_id, captured_at, scene_generation, 0, 0)

    def _stream_openai(self, http_client, url: str, headers: dict, data: dict) -> tuple[str, int, int]:
        collected = []
        input_tokens = 0
        output_tokens = 0
        with http_client.stream("POST", url, headers=headers, json=data) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if self._stopping:
                    break
                if not line or not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    usage = chunk.get("usage")
                    if usage:
                        input_tokens = usage.get("prompt_tokens", 0)
                        output_tokens = usage.get("completion_tokens", 0)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        collected.append(content)
                except (json.JSONDecodeError, IndexError, KeyError):
                    continue
        return "".join(collected), input_tokens, output_tokens

    def close(self):
        with self._client_lock:
            clients = list(self._clients)
            self._clients.clear()
        for client in clients:
            try:
                client.close()
            except Exception:
                pass
        if hasattr(self._thread_local, "client"):
            self._thread_local.client = None
