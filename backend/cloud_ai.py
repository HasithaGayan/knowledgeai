"""Opt-in Workers AI adapter. Not connected to the local app or public routes.
Cloud data must never be sent without the user's knowledge. Credentials are
server-side only. Model-specific indexes must be rebuilt, not mixed with Ollama.
"""
from __future__ import annotations

import json
import math
import re
from typing import Sequence

import httpx

CHAT_MODEL = '@cf/meta/llama-3.1-8b-instruct'
EMBED_MODEL = '@cf/baai/bge-small-en-v1.5'
EMBED_DIM = 384


class CloudAIError(RuntimeError):
    pass


class CloudAI:
    def __init__(self, account: str, token: str, *, transport=None):
        if not re.fullmatch(r'[0-9a-fA-F]{32}', account):
            raise ValueError('Invalid Cloudflare account ID')
        if not token or any(c.isspace() for c in token):
            raise ValueError('Invalid Workers AI token')
        self._base = f'https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/'
        self._token = token
        self._transport = transport

    def _post(self, model: str, payload: dict) -> dict:
        try:
            with httpx.Client(timeout=httpx.Timeout(45, connect=10),
                              follow_redirects=False, trust_env=False,
                              transport=self._transport) as client:
                response = client.post(self._base + model, json=payload,
                    headers={'Authorization': 'Bearer ' + self._token})
                if response.status_code != 200:
                    raise CloudAIError(f'Workers AI HTTP {response.status_code}')
                body = response.json()
        except (httpx.HTTPError, ValueError):
            raise CloudAIError('Workers AI network or response failure') from None
        if not isinstance(body, dict) or body.get('success') is not True or not isinstance(body.get('result'), dict):
            raise CloudAIError('Workers AI returned an invalid result')
        return body['result']

    def chat(self, messages: Sequence[dict], *, max_tokens: int = 256, json_schema: dict | None = None) -> str:
        if not isinstance(messages, (list, tuple)) or not 1 <= len(messages) <= 24:
            raise ValueError('Expected 1-24 messages')
        if type(max_tokens) is not int or not 1 <= max_tokens <= 512:
            raise ValueError('Invalid output token limit')
        for msg in messages:
            if (not isinstance(msg, dict) or set(msg) != {'role', 'content'}
                or msg['role'] not in ('system', 'user', 'assistant')
                or not isinstance(msg['content'], str) or not msg['content'].strip()):
                raise ValueError('Invalid chat message')
        if sum(len(m['content']) for m in messages) > 24000:
            raise ValueError('Chat input too large')
        payload = {'messages': list(messages), 'stream': False,
                   'max_tokens': max_tokens, 'temperature': 0.2,
                   'repetition_penalty': 1.1}
        if json_schema is not None:
            if not isinstance(json_schema, dict) or json_schema.get('type') != 'object':
                raise ValueError('Expected an object JSON schema')
            payload['response_format'] = {'type': 'json_schema', 'json_schema': json_schema}
        result = self._post(CHAT_MODEL, payload)
        answer = result.get('response')
        if json_schema is not None:
            if isinstance(answer, str):
                try:
                    answer = json.loads(answer)
                except ValueError:
                    raise CloudAIError('Workers AI returned malformed JSON') from None
            if isinstance(answer, dict) and answer:
                # Caller must validate against the requested schema and evidence.
                return json.dumps(answer, ensure_ascii=False, allow_nan=False)
            raise CloudAIError('Workers AI returned no structured object')
        if not isinstance(answer, str) or not answer.strip():
            # Report only the shape, never raw payloads or credentials.
            raise CloudAIError('Workers AI returned no text (response type: ' + type(answer).__name__ + ')')
        return answer.strip()

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if (not isinstance(texts, (list, tuple)) or not 1 <= len(texts) <= 16
            or any(not isinstance(t, str) or not t.strip() or len(t) > 4000 for t in texts)):
            raise ValueError('Expected 1-16 nonempty embedding inputs')
        result = self._post(EMBED_MODEL, {'text': list(texts)})
        vectors = result.get('data')
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise CloudAIError('Invalid embedding count')
        for vector in vectors:
            if (not isinstance(vector, list) or len(vector) != EMBED_DIM
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in vector)
                or not any(vector)):
                raise CloudAIError('Invalid embedding vector')
        return [[float(x) for x in vector] for vector in vectors]
