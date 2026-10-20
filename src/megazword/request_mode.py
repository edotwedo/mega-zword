"""Recognize explicit code inspection and no-paid instructions before routing."""
import re


def code_review(text):
    return bool(re.search(r'\b(?:review|audit|inspect|access|analy[sz]e)\b.{0,80}\b(?:code|source|repo(?:sitory)?)\b', text, re.I | re.S))


def free_only(text):
    return bool(re.search(r'\b(?:free[- ]only|only free|no paid)\b|\b(?:don[\W_]*t|dont|do not|never)\b.{0,40}\b(?:paid|spend|pay)\b', text, re.I | re.S))


def free_backend(backend):
    from . import config
    from .backends import OllamaBackend
    from .free_apis import OpenAICompatibleBackend
    if not isinstance(backend, (OpenAICompatibleBackend, OllamaBackend)) or backend.name not in config.DEFAULT_FREE:
        return False
    return not (getattr(backend, 'base_url', '').startswith('https://openrouter.ai')
                and not (getattr(backend, 'model', '').endswith(':free')
                         or getattr(backend, 'model', '') == 'openrouter/free'))
