import time
import requests
from .provider import BaseProvider
from . import prompts as p


class AzureFoundryProvider(BaseProvider):
    def __init__(self, config):
        # Support both flat config dict and legacy nested format
        if 'azure' in config:
            azure = config['azure']
            self.endpoint = azure['endpoint'].rstrip('/')
            self.api_key = azure['apiKey']
            self.text_deployment = azure['textDeployment']
            self.vision_deployment = azure['visionDeployment']
            self.api_version = azure['apiVersion']
        else:
            self.endpoint = (config.get('base_url') or '').rstrip('/')
            self.api_key = config.get('api_key', '')
            deployment = config.get('deployment_id', '')
            self.text_deployment = deployment
            self.vision_deployment = deployment
            self.api_version = config.get('api_version', '2024-02-01')

    def analyze_text(self, text, language='English', custom_prompt=None):
        start = time.time()
        prompt = p.wrap_custom_prompt(custom_prompt + f"\n\nText:\n{text}") if custom_prompt else p.text_analysis_prompt(text, language)
        raw = self._chat_completion(
            [
                {'role': 'system', 'content': 'You are a proofreading assistant. Respond with ONLY a JSON object. No markdown, no explanation.'},
                {'role': 'user', 'content': prompt},
            ],
            deployment=self.text_deployment, max_tokens=16000, temperature=0
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
            'raw': raw, 'model': self.text_deployment,
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
                    {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{screenshot_b64}'}},
                ],
            },
        ]
        raw = self._chat_completion(messages, deployment=self.vision_deployment, max_tokens=4000, temperature=0)
        result = self._parse_response(raw)
        issues = result['issues']
        summary = result['summary'] or (
            f'Checked screenshot for visual quality. Found {len(issues)} issue{"s" if len(issues) != 1 else ""}.'
            if issues else 'Checked screenshot for visual quality. No issues detected.'
        )
        return {
            'issues': issues, 'issuesFound': len(issues) > 0,
            'summary': summary,
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

    def _chat_completion(self, messages, deployment=None, max_tokens=1000, temperature=None):
        deployment = deployment or self.text_deployment
        headers = {'Content-Type': 'application/json', 'api-key': self.api_key}
        last_error = None

        for attempt in range(3):
            try:
                # Try Chat Completions API first
                result = self._try_chat_completions(messages, deployment, max_tokens, temperature, headers)
                if result is not None:
                    return result

                # Chat Completions not supported — fall back to Responses API
                result = self._try_responses_api(messages, deployment, max_tokens, temperature, headers)
                if result is not None:
                    return result

                raise Exception(f"Model {deployment} did not return a valid response from either API")
            except _RetryableError as e:
                last_error = e.original
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue
                raise last_error
            except Exception as e:
                last_error = e
                if attempt < 2 and '401' not in str(e) and '403' not in str(e):
                    time.sleep(1 * (attempt + 1))
                    continue
                raise
        raise last_error

    def _try_chat_completions(self, messages, deployment, max_tokens, temperature, headers):
        """Try the Chat Completions API. Returns content string or None if unsupported."""
        url = f"{self.endpoint}/openai/deployments/{deployment}/chat/completions?api-version={self.api_version}"
        body = {'messages': messages, 'max_completion_tokens': max_tokens, 'model': deployment}
        if temperature is not None:
            body['temperature'] = temperature

        resp = requests.post(url, json=body, headers=headers, timeout=120)

        # If 400, try stripping params
        if resp.status_code == 400:
            error_text = resp.text[:500] if resp.text else ''
            # Model doesn't support chat completions at all — signal to try Responses API
            if 'OperationNotSupported' in error_text:
                return None
            # Try removing temperature
            if 'temperature' in body:
                body.pop('temperature')
                resp = requests.post(url, json=body, headers=headers, timeout=120)
            # Try switching max_completion_tokens → max_tokens
            if resp.status_code == 400 and 'max_completion_tokens' in body:
                body['max_tokens'] = body.pop('max_completion_tokens')
                resp = requests.post(url, json=body, headers=headers, timeout=120)

        if resp.status_code == 429:
            raise _RetryableError(Exception("Azure rate limited (429)"))

        if not resp.ok:
            error_detail = resp.text[:500] if resp.text else ''
            raise Exception(f"{resp.status_code} {resp.reason}: {error_detail}")

        data = resp.json()
        return data['choices'][0]['message']['content']

    def _try_responses_api(self, messages, deployment, max_tokens, temperature, headers):
        """Try the Azure Responses API (for models that don't support chat completions)."""
        url = f"{self.endpoint}/openai/v1/responses"
        # Convert chat messages to Responses API format
        input_items = []
        for msg in messages:
            content = msg.get('content', '')
            if isinstance(content, list):
                # Multi-part content (vision) — extract text parts
                text_parts = [p['text'] for p in content if isinstance(p, dict) and p.get('type') == 'text']
                content = '\n'.join(text_parts) if text_parts else str(content)
            if msg['role'] == 'system':
                input_items.append({'role': 'developer', 'content': content})
            else:
                input_items.append({'role': msg['role'], 'content': content})

        body = {'model': deployment, 'input': input_items}
        if max_tokens:
            body['max_output_tokens'] = max(max_tokens, 16)
        if temperature is not None:
            body['temperature'] = temperature

        resp = requests.post(url, json=body, headers=headers, timeout=120)

        if resp.status_code == 429:
            raise _RetryableError(Exception("Azure rate limited (429)"))

        if not resp.ok:
            error_detail = resp.text[:500] if resp.text else ''
            raise Exception(f"{resp.status_code} {resp.reason}: {error_detail}")

        data = resp.json()
        # Responses API returns output_text directly
        if data.get('output_text'):
            return data['output_text']
        # Or dig into output array
        for item in data.get('output', []):
            if item.get('type') == 'message':
                for c in item.get('content', []):
                    if c.get('type') == 'output_text':
                        return c.get('text', '')
        return None


class _RetryableError(Exception):
    """Wrapper to signal retryable errors in the retry loop."""
    def __init__(self, original):
        self.original = original
        super().__init__(str(original))
