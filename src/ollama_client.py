"""Transport HTTP Ollama pour un appel de génération structuré."""
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import OllamaConfig
from segmentation_schemas import Generation, GenerationError


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = Request(
            self.config.base_url.rstrip('/') + path,
            data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
        )
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                data = json.load(response)
        except HTTPError as exc:
            exc.close()
            raise GenerationError('http', f'Ollama a répondu HTTP {exc.code}.') from exc
        except (TimeoutError, URLError) as exc:
            timed_out = isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError)
            if timed_out:
                raise GenerationError('timeout', 'Délai de réponse Ollama dépassé.') from exc
            raise GenerationError('connection', f'Connexion Ollama impossible ({exc.reason}).') from exc
        except (OSError, HTTPException) as exc:
            raise GenerationError('connection', f'Connexion Ollama interrompue ({exc}).') from exc
        except ValueError as exc:
            raise GenerationError('protocol', 'La réponse HTTP Ollama ne contient pas de JSON lisible.') from exc
        if not isinstance(data, dict) or 'error' in data:
            raise GenerationError('protocol', 'Enveloppe Ollama invalide ou réponse en erreur.')
        return data

    def loaded_models(self) -> dict[str, str | None]:
        return self._models('/api/ps')

    def installed_models(self) -> dict[str, str | None]:
        return self._models('/api/tags')

    def _models(self, path: str) -> dict[str, str | None]:
        models = self._request(path).get('models')
        if not isinstance(models, list):
            raise GenerationError('protocol', f'Liste des modèles invalide ({path}).')
        return {item['name']: item.get('digest') for item in models
                if isinstance(item, dict) and isinstance(item.get('name'), str)}

    def generate(self, system_prompt: str, text: str, schema: dict) -> Generation:
        config = self.config
        payload = {
            'model': config.model_name,
            'stream': False,
            'format': schema if config.output_format == 'schema' else 'json',
            'options': {'temperature': config.temperature, 'num_predict': config.num_predict},
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': text},
            ],
        }
        if config.think is not None:
            payload['think'] = config.think
        data = self._request('/api/chat', payload)
        message = data.get('message')
        content = message.get('content') if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise GenerationError('protocol', 'Champ message.content absent ou invalide.')

        def integer(key: str) -> int | None:
            value = data.get(key)
            return value if type(value) is int and value >= 0 else None

        total = integer('total_duration')
        generation = integer('eval_duration')
        done_reason = data.get('done_reason')
        result = Generation(
            content=content,
            done_reason=done_reason if isinstance(done_reason, str) else None,
            server_seconds=total / 1e9 if total is not None else None,
            generation_seconds=generation / 1e9 if generation is not None else None,
            input_tokens=integer('prompt_eval_count'), output_tokens=integer('eval_count'),
        )
        if data.get('done') is not True or done_reason == 'length':
            raise GenerationError('truncated', 'Génération interrompue avant la fin.', result)
        return result
