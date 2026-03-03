import time
import requests
from .provider import BaseProvider
from . import prompts as p


class OllamaProvider(BaseProvider):
    def __init__(self, config):
        host = config['ollama']['host']
        self.base_url = f"http://{host}"
        self.text_model = config['ollama']['textModel']
        self.vision_model = config['ollama']['visionModel']

    def analyze_text(self, text, language='English'):
        start = time.time()
        prompt = p.text_analysis_prompt(text, language)
        raw = self._chat_completion(
            [
                {'role': 'system', 'content': 'You are a proofreading assistant. Respond with ONLY a JSON array. No markdown, no explanation.'},
                {'role': 'user', 'content': prompt},
            ],
            model=self.text_model, max_tokens=1000
        )
        issues = self._parse_issues(raw)
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'raw': raw, 'model': self.text_model,
            'durationMs': int((time.time() - start) * 1000),
        }

    def analyze_screenshot(self, screenshot_b64, context=''):
        start = time.time()
        prompt = p.vision_analysis_prompt(context)
        raw = self._chat_completion(
            [
                {'role': 'user', 'content': prompt,
                 'images': [screenshot_b64]},
            ],
            model=self.vision_model, max_tokens=1000
        )
        issues = self._parse_issues(raw)
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'raw': raw, 'model': self.vision_model,
            'durationMs': int((time.time() - start) * 1000),
        }

    def compare_text(self, baseline, current, language='English'):
        start = time.time()
        prompt = p.text_comparison_prompt(baseline, current, language)
        raw = self._chat_completion(
            [
                {'role': 'system', 'content': 'You are a proofreading assistant. Respond with ONLY a JSON array. No markdown, no explanation.'},
                {'role': 'user', 'content': prompt},
            ],
            model=self.text_model, max_tokens=1500
        )
        diffs = self._parse_issues(raw)
        return {
            'differences': diffs, 'hasDifferences': len(diffs) > 0,
            'raw': raw, 'model': self.text_model,
            'durationMs': int((time.time() - start) * 1000),
        }

    def generate_test(self, description, context=None):
        context = context or {}
        system_prompt = p.test_generation_system_prompt(context.get('helpers'))
        return self._chat_completion(
            [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': description},
            ],
            model=self.text_model, max_tokens=2000
        )

    def health_check(self):
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m['name'] for m in resp.json().get('models', [])]
            return {
                'healthy': True, 'provider': 'ollama',
                'details': {'host': self.base_url, 'models': models},
            }
        except Exception as e:
            return {'healthy': False, 'provider': 'ollama', 'details': {'error': str(e)}}

    def chat_completion(self, messages, options=None):
        options = options or {}
        return self._chat_completion(messages, model=self.text_model, max_tokens=options.get('max_tokens', 3000))

    def _chat_completion(self, messages, model=None, max_tokens=1000):
        model = model or self.text_model
        body = {
            'model': model,
            'messages': messages,
            'stream': False,
            'options': {'num_predict': max_tokens},
        }
        resp = requests.post(f"{self.base_url}/api/chat", json=body, timeout=120)
        resp.raise_for_status()
        return resp.json()['message']['content']
