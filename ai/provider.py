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
