"""AI provider factory — DB-driven, per-feature provider selection."""
import time
from django.conf import settings


class BaseProvider:
    """Abstract base for all AI providers."""

    def analyze_text(self, text, language='English', custom_prompt=None):
        raise NotImplementedError

    def analyze_screenshot(self, screenshot_b64, context='', custom_prompt=None):
        raise NotImplementedError

    def compare_text(self, baseline, current, language='English'):
        raise NotImplementedError

    def generate_test(self, description, context=None):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError

    def chat_completion(self, messages, options=None):
        raise NotImplementedError

    def _parse_response(self, raw):
        """Parse JSON response — handles {summary, issues} objects and plain arrays."""
        import json
        if not raw:
            return {'summary': '', 'issues': []}
        text = raw.strip()
        if text.startswith('```'):
            lines = text.split('\n')
            text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {
                    'summary': parsed.get('summary', ''),
                    'issues': parsed.get('issues', []),
                }
            if isinstance(parsed, list):
                return {'summary': '', 'issues': parsed}
        except Exception:
            pass
        return {'summary': '', 'issues': []}

    def _parse_issues(self, raw):
        """Parse JSON array from AI response (backward compat)."""
        return self._parse_response(raw)['issues']


# ── Provider cache: keyed by provider UUID, values are (instance, cached_at) ──
_provider_cache = {}
_CACHE_TTL = 300  # 5 minutes


def _instantiate_provider(provider_type, config):
    """Build a provider instance from a type string and flat config dict."""
    if provider_type == 'anthropic':
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(config)
    elif provider_type == 'azure_openai':
        from .azure_foundry import AzureFoundryProvider
        return AzureFoundryProvider(config)
    elif provider_type == 'openai_compat':
        from .openai_compat import OpenAICompatProvider
        return OpenAICompatProvider(config)
    elif provider_type == 'mock':
        from .mock import MockProvider
        return MockProvider(config)
    # Legacy type names for backward compat
    elif provider_type == 'azure':
        from .azure_foundry import AzureFoundryProvider
        return AzureFoundryProvider(config)
    elif provider_type == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider(config)
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def _get_mock_provider():
    """Return a MockProvider with the configured mode."""
    from .mock import MockProvider
    return MockProvider({'mockAiMode': getattr(settings, 'MOCK_AI_MODE', 'clean')})


def _get_provider_by_id(provider_id):
    """Look up an AIProvider by UUID, instantiate, and cache with TTL."""
    now = time.time()
    cached = _provider_cache.get(str(provider_id))
    if cached:
        instance, cached_at = cached
        if now - cached_at < _CACHE_TTL:
            return instance

    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            """SELECT provider_type, api_key, model, base_url, deployment_id, api_version
               FROM ai_providers WHERE id = %s AND enabled = true""",
            [str(provider_id)]
        )
        row = cursor.fetchone()

    if not row:
        return None

    provider_type, api_key, model, base_url, deployment_id, api_version = row
    config = {
        'api_key': api_key or '',
        'model': model or '',
        'base_url': base_url or '',
        'deployment_id': deployment_id or '',
        'api_version': api_version or '',
    }
    instance = _instantiate_provider(provider_type, config)
    _provider_cache[str(provider_id)] = (instance, now)
    return instance


def get_provider_for_feature(feature):
    """Return a provider for a specific feature ('builder', 'text', 'vision').

    Reads {feature}_provider_id from ai_settings. Returns Mock if 'mock' or missing.
    """
    import json
    from django.db import connection

    setting_key = f'{feature}_provider_id'
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT value FROM ai_settings WHERE key = %s", [setting_key]
            )
            row = cursor.fetchone()
    except Exception:
        return _get_mock_provider()

    if not row:
        return _get_mock_provider()

    val = row[0]
    # Unwrap potentially double-encoded JSON strings
    for _ in range(3):
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                break
        else:
            break

    if not val or val == 'mock':
        return _get_mock_provider()

    provider = _get_provider_by_id(val)
    if provider is None:
        return _get_mock_provider()
    return provider


def get_provider():
    """Backward-compatible entry point — delegates to builder feature provider."""
    return get_provider_for_feature('builder')


def invalidate_provider_cache(provider_id=None):
    """Clear cached provider instances. Called after admin saves."""
    global _provider_cache
    if provider_id:
        _provider_cache.pop(str(provider_id), None)
    else:
        _provider_cache.clear()
