"""Prompt templates for AI analysis."""


def text_analysis_prompt(text, language='English'):
    return f"""Analyze this {language} text from a student assessment for spelling errors, homophone misuse, and grammar issues.

Text:
{text}

Return ONLY a JSON array. Each item: {{"type": "spelling|homophone|grammar", "text": "wrong word", "suggestion": "correct word", "context": "surrounding text"}}
If no issues: []"""


def vision_analysis_prompt(context=''):
    ctx_part = f"\nContext: {context}" if context else ""
    return f"""Analyze this screenshot from a student assessment for visual quality issues.{ctx_part}

Check for: text readability, layout problems, missing content, contrast issues, rendering artifacts.

Return ONLY a JSON array. Each item: {{"type": "readability|layout|missing|contrast|artifact", "detail": "description", "severity": "low|medium|high"}}
If no issues: []"""


def text_comparison_prompt(baseline, current, language='English'):
    return f"""Compare these two versions of {language} assessment text and identify significant differences.

Baseline:
{baseline}

Current:
{current}

Return ONLY a JSON array of differences. Each item: {{"type": "added|removed|changed|reordered", "baseline": "...", "current": "...", "significance": "low|medium|high"}}
If no differences: []"""


def test_generation_system_prompt(helpers=None):
    helper_section = ''
    if helpers:
        helper_lines = []
        for fname, funcs in helpers.items():
            for f in funcs:
                helper_lines.append(f"- {f['name']} (from {fname})")
        if helper_lines:
            helper_section = '\n\nAvailable helpers:\n' + '\n'.join(helper_lines)

    return f"""You are SCOUT AI, an expert at writing Playwright test scripts for the NAEP assessment platform.

Generate clean, well-commented Playwright tests using:
- @playwright/test framework
- Helper functions from src/helpers/
- test.describe() blocks with descriptive names
- Proper assertions (toBeVisible, toHaveText)
- page.screenshot() for captures (SCOUT handles baseline comparison — do NOT use toHaveScreenshot)
- @smoke, @visual, @content, @feature tags{helper_section}

Return ONLY the JavaScript code, no explanation."""
