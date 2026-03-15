import time
import requests
from .provider import BaseProvider
from . import prompts as p


class AnthropicProvider(BaseProvider):
    """Provider for Anthropic Messages API (direct Anthropic + Azure AI Foundry)."""

    def __init__(self, config):
        self.api_key = config.get('api_key', '')
        self.model = config.get('model', 'claude-sonnet-4-5')
        base_url = config.get('base_url', 'https://api.anthropic.com/v1/')
        if not base_url:
            base_url = 'https://api.anthropic.com/v1/'
        if not base_url.endswith('/'):
            base_url += '/'
        self.base_url = base_url

    def analyze_text(self, text, language='English', custom_prompt=None):
        start = time.time()
        prompt = p.wrap_custom_prompt(custom_prompt + f"\n\nText:\n{text}") if custom_prompt else p.text_analysis_prompt(text, language)
        raw = self._chat_completion(
            [
                {'role': 'system', 'content': 'You are a proofreading assistant. Respond with ONLY a JSON object. No markdown, no explanation.'},
                {'role': 'user', 'content': prompt},
            ],
            max_tokens=4000
        )
        result = self._parse_response(raw)
        issues = result['issues']
        summary = result['summary'] or (
            f'Analyzed {language} text. Found {len(issues)} issue{"s" if len(issues) != 1 else ""}.'
            if issues else f'Analyzed {language} text. No issues found.'
        )
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'summary': summary,
            'raw': raw, 'model': self.model,
            'durationMs': int((time.time() - start) * 1000),
        }

    def analyze_screenshot(self, screenshot_b64, context='', custom_prompt=None):
        start = time.time()
        prompt = p.wrap_custom_prompt(custom_prompt, context) if custom_prompt else p.vision_analysis_prompt(context)
        messages = [
            {'role': 'system', 'content': 'You are a visual QA analyst. Respond with ONLY a JSON object. No markdown, no explanation.'},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/png', 'data': screenshot_b64}},
                ],
            },
        ]
        raw = self._chat_completion(messages, max_tokens=4000)
        result = self._parse_response(raw)
        issues = result['issues']
        summary = result['summary'] or (
            f'Checked screenshot for visual quality. Found {len(issues)} issue{"s" if len(issues) != 1 else ""}.'
            if issues else 'Checked screenshot for visual quality. No issues detected.'
        )
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'summary': summary,
            'raw': raw, 'model': self.model,
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
            max_tokens=1500
        )
        diffs = self._parse_issues(raw)
        return {
            'differences': diffs, 'hasDifferences': len(diffs) > 0,
            'raw': raw, 'model': self.model,
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
            max_tokens=2000
        )

    def health_check(self):
        try:
            raw = self._chat_completion(
                [{'role': 'user', 'content': 'Reply with "ok"'}],
                max_tokens=10
            )
            return {
                'healthy': True, 'provider': 'anthropic',
                'details': {
                    'base_url': self.base_url,
                    'model': self.model,
                    'response': raw.strip(),
                },
            }
        except Exception as e:
            return {'healthy': False, 'provider': 'anthropic', 'details': {'error': str(e)}}

    def chat_completion(self, messages, options=None):
        options = options or {}
        return self._chat_completion(messages, max_tokens=options.get('max_tokens', 3000))

    def _chat_completion(self, messages, max_tokens=1000):
        url = self.base_url + 'messages'

        # Extract system message — Anthropic uses top-level 'system' field
        system_text = ''
        api_messages = []
        for msg in messages:
            if msg['role'] == 'system':
                system_text += (msg.get('content') or '') + '\n'
            else:
                api_messages.append(msg)
        system_text = system_text.strip()

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': self.api_key,
            'anthropic-version': '2023-06-01',
        }
        body = {
            'model': self.model,
            'max_tokens': max_tokens,
            'messages': api_messages,
        }
        if system_text:
            body['system'] = system_text

        last_error = None
        for attempt in range(3):
            try:
                resp = requests.post(url, json=body, headers=headers, timeout=120)
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get('retry-after', '2'))
                    delay = min(retry_after, 10) * (attempt + 1)
                    time.sleep(delay)
                    last_error = Exception("Anthropic rate limited (429)")
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data['content'][0]['text']
            except Exception as e:
                last_error = e
                if attempt < 2 and '401' not in str(e) and '403' not in str(e):
                    time.sleep(1 * (attempt + 1))
                    continue
                raise
        raise last_error
