import time
import requests
from .provider import BaseProvider
from . import prompts as p


class AzureFoundryProvider(BaseProvider):
    def __init__(self, config):
        self.endpoint = config['azure']['endpoint'].rstrip('/')
        self.api_key = config['azure']['apiKey']
        self.text_deployment = config['azure']['textDeployment']
        self.vision_deployment = config['azure']['visionDeployment']
        self.api_version = config['azure']['apiVersion']

    def analyze_text(self, text, language='English'):
        start = time.time()
        prompt = p.text_analysis_prompt(text, language)
        raw = self._chat_completion(
            [
                {'role': 'system', 'content': 'You are a proofreading assistant. Respond with ONLY a JSON array. No markdown, no explanation.'},
                {'role': 'user', 'content': prompt},
            ],
            deployment=self.text_deployment, max_tokens=1000
        )
        issues = self._parse_issues(raw)
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'raw': raw, 'model': self.text_deployment,
            'durationMs': int((time.time() - start) * 1000),
        }

    def analyze_screenshot(self, screenshot_b64, context=''):
        start = time.time()
        prompt = p.vision_analysis_prompt(context)
        messages = [
            {'role': 'system', 'content': 'You are a visual QA analyst. Respond with ONLY a JSON array. No markdown, no explanation.'},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{screenshot_b64}'}},
                ],
            },
        ]
        raw = self._chat_completion(messages, deployment=self.vision_deployment, max_tokens=1000)
        issues = self._parse_issues(raw)
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'raw': raw, 'model': self.vision_deployment,
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
            deployment=self.text_deployment, max_tokens=1500
        )
        diffs = self._parse_issues(raw)
        return {
            'differences': diffs, 'hasDifferences': len(diffs) > 0,
            'raw': raw, 'model': self.text_deployment,
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
            deployment=self.text_deployment, max_tokens=2000
        )

    def health_check(self):
        try:
            raw = self._chat_completion(
                [{'role': 'user', 'content': 'Reply with "ok"'}],
                deployment=self.text_deployment, max_tokens=10
            )
            return {
                'healthy': True, 'provider': 'azure',
                'details': {
                    'endpoint': self.endpoint,
                    'textDeployment': self.text_deployment,
                    'response': raw.strip(),
                },
            }
        except Exception as e:
            return {'healthy': False, 'provider': 'azure', 'details': {'error': str(e)}}

    def chat_completion(self, messages, options=None):
        options = options or {}
        return self._chat_completion(messages, max_tokens=options.get('max_tokens', 3000))

    def _chat_completion(self, messages, deployment=None, max_tokens=1000):
        deployment = deployment or self.text_deployment
        url = f"{self.endpoint}/openai/deployments/{deployment}/chat/completions?api-version={self.api_version}"
        body = {'messages': messages, 'max_completion_tokens': max_tokens}
        last_error = None

        for attempt in range(3):
            try:
                resp = requests.post(
                    url, json=body,
                    headers={'Content-Type': 'application/json', 'api-key': self.api_key},
                    timeout=60
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('retry-after', '2'))
                    delay = min(retry_after * 1000, 10000) * (attempt + 1) / 1000
                    time.sleep(delay)
                    last_error = Exception(f"Azure rate limited (429)")
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data['choices'][0]['message']['content']
            except Exception as e:
                last_error = e
                if attempt < 2 and '401' not in str(e) and '403' not in str(e):
                    time.sleep(1 * (attempt + 1))
                    continue
                raise
        raise last_error
