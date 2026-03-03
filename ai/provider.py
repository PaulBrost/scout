"""AI provider factory — reads AI_PROVIDER env var to select implementation."""
from django.conf import settings


class BaseProvider:
    """Abstract base for all AI providers."""

    def analyze_text(self, text, language='English'):
        raise NotImplementedError

    def analyze_screenshot(self, screenshot_b64, context=''):
        raise NotImplementedError

    def compare_text(self, baseline, current, language='English'):
        raise NotImplementedError

    def generate_test(self, description, context=None):
        raise NotImplementedError

    def health_check(self):
        raise NotImplementedError

    def chat_completion(self, messages, options=None):
        raise NotImplementedError

    def _parse_issues(self, raw):
        """Parse JSON array from AI response."""
        import json
        if not raw:
            return []
        raw = raw.strip()
        # Strip markdown code fences
        if raw.startswith('```'):
            lines = raw.split('\n')
            raw = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return []


_provider_instance = None


def get_provider():
    """Return the configured AI provider (singleton per process)."""
    global _provider_instance
    if _provider_instance is not None:
        return _provider_instance

    provider_name = getattr(settings, 'AI_PROVIDER', 'mock')

    if provider_name == 'azure':
        from .azure_foundry import AzureFoundryProvider
        _provider_instance = AzureFoundryProvider({
            'azure': {
                'endpoint': settings.AZURE_ENDPOINT,
                'apiKey': settings.AZURE_API_KEY,
                'textDeployment': settings.AZURE_TEXT_DEPLOYMENT,
                'visionDeployment': settings.AZURE_VISION_DEPLOYMENT,
                'apiVersion': settings.AZURE_API_VERSION,
            }
        })
    elif provider_name == 'ollama':
        from .ollama import OllamaProvider
        _provider_instance = OllamaProvider({
            'ollama': {
                'host': settings.OLLAMA_HOST,
                'textModel': settings.OLLAMA_TEXT_MODEL,
                'visionModel': settings.OLLAMA_VISION_MODEL,
            }
        })
    else:
        from .mock import MockProvider
        _provider_instance = MockProvider({
            'mockAiMode': getattr(settings, 'MOCK_AI_MODE', 'clean'),
        })

    return _provider_instance


def _instantiate_provider(provider_type, provider_config):
    """Build a provider instance from an explicit type string and config dict."""
    if provider_type == 'azure':
        from .azure_foundry import AzureFoundryProvider
        return AzureFoundryProvider({
            'azure': {
                'endpoint': provider_config.get('endpoint', ''),
                'apiKey': provider_config.get('apiKey', ''),
                'textDeployment': provider_config.get('deployment', ''),
                'visionDeployment': provider_config.get('deployment', ''),
                'apiVersion': provider_config.get('apiVersion', '2024-12-01-preview'),
            }
        })
    elif provider_type == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider({
            'ollama': {
                'host': provider_config.get('host', 'localhost:11434'),
                'textModel': provider_config.get('model', 'llama3'),
                'visionModel': provider_config.get('model', 'llama3'),
            }
        })
    elif provider_type == 'mock':
        from .mock import MockProvider
        return MockProvider({
            'mockAiMode': provider_config.get('mockAiMode', 'clean'),
        })
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")


def get_provider_for_feature(feature):
    """Return a provider for a specific feature, falling back to the global provider.

    feature: 'text', 'vision', 'chat', or None.
    """
    if feature in (None, 'chat'):
        return get_provider()

    import json
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT key, value FROM ai_settings WHERE key IN (%s, %s)",
            [f'{feature}_provider_type', f'{feature}_provider_config']
        )
        rows = {row[0]: row[1] for row in cursor.fetchall()}

    provider_type = rows.get(f'{feature}_provider_type')
    # Unwrap JSON-encoded string values
    if isinstance(provider_type, str):
        try:
            provider_type = json.loads(provider_type)
        except (json.JSONDecodeError, TypeError):
            pass

    if not provider_type or provider_type == 'default':
        return get_provider()

    provider_config = rows.get(f'{feature}_provider_config', {})
    if isinstance(provider_config, str):
        try:
            provider_config = json.loads(provider_config)
        except (json.JSONDecodeError, TypeError):
            provider_config = {}

    return _instantiate_provider(provider_type, provider_config)
