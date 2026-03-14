// SCOUT — Shared Prompt Templates
// Provider-agnostic prompts used by all AI providers.

/**
 * Text analysis prompt — spelling, grammar, homophone detection.
 */
function textAnalysisPrompt(text, language = 'English') {
  return `You are a strict proofreading assistant for educational assessment items written in ${language}.

Analyze the text below for ONLY these concrete issues:
1. **Spelling errors** — misspelled words (not formatting or style)
2. **Homophone misuse** — wrong word used (e.g., "their" vs "there", "affect" vs "effect")
3. **Grammar errors** — subject-verb disagreement, broken sentence structure
4. **Garbled text** — corrupted characters, extra whitespace within words, encoding artifacts

IMPORTANT RULES:
- Only report issues you are highly confident about.
- Do NOT flag stylistic choices, mathematical notation, variable names, or assessment-specific formatting.
- Do NOT flag extra whitespace between words — only within words.
- Respond with ONLY a JSON array — no explanation, no markdown, no commentary.
- If no issues exist, respond with exactly: []

Each issue in the array must have these fields:
{"type": "spelling|homophone|grammar|garbled", "text": "the problematic text", "suggestion": "the correction", "context": "short snippet showing where it appears"}

Text to analyze:
"""
${text}
"""`;
}

/**
 * Vision analysis prompt — screenshot readability and layout check.
 */
function visionAnalysisPrompt(context = '') {
  return `You are a visual QA analyst for educational assessment items. Analyze this screenshot for ONLY significant visual defects:

1. **readability** — Blurry, overlapping, or cut-off text that prevents reading
2. **layout** — Misaligned or overlapping UI elements that break the interface
3. **contrast** — Text that is unreadable due to insufficient color contrast
4. **rendering** — Broken images, missing icons, garbled characters, visual artifacts
5. **completeness** — Visibly truncated or missing content

${context ? `Additional context: ${context}` : ''}

IMPORTANT RULES:
- Only report genuine defects that would impact a student taking this assessment.
- Do NOT flag minor cosmetic details, normal UI chrome, or intentional design choices.
- Respond with ONLY a JSON array — no explanation, no markdown, no commentary.
- If no issues exist, respond with exactly: []

Each issue: {"type": "readability|layout|contrast|rendering|completeness", "detail": "description", "severity": "high|medium|low"}`;
}

/**
 * Text comparison prompt — compare two versions of assessment text.
 */
function textComparisonPrompt(baselineText, currentText, language = 'English') {
  return `Compare these two versions of the same ${language} assessment item text and identify meaningful differences. Ignore whitespace-only changes.

**Previous version (baseline):**
"""
${baselineText}
"""

**Current version:**
"""
${currentText}
"""

Return your findings as a JSON array. Each difference should have:
- "type": one of "added", "removed", "changed", "reworded"
- "baseline": the original text (if applicable)
- "current": the new text (if applicable)
- "significance": "high" (meaning change), "medium" (minor rewording), "low" (cosmetic)

If the texts are identical or only differ by whitespace, return exactly: []`;
}

/**
 * Test generation system prompt — used by the AI test builder.
 * @param {object} helperDocs - Object mapping helper names to their descriptions
 */
function testGenerationSystemPrompt(helperDocs = {}) {
  const helperList = Object.entries(helperDocs)
    .map(([name, desc]) => `- ${name} — ${desc}`)
    .join('\n');

  return `You are a Playwright test script generator for SCOUT, the NAEP assessment testing system.

Available helpers (import from the helpers directory):
${helperList || `- loginAndNavigate(page, url) — logs in and navigates to the given URL
- getItemUrl(itemId) — returns the URL for an assessment item
- setZoom(page, percent) — sets the browser zoom level
- setTheme(page, theme) — switches theme: 'light', 'dark', 'low-contrast'
- switchLanguage(page, lang) — toggles to 'English' or 'Spanish'
- openCalculator(page) — opens the calculator overlay, returns the calculator locator
- openHelp(page) — opens the help panel
- extractItemText(page) — extracts visible text content from the item DOM`}

Conventions:
- Use require('@playwright/test') for test and expect
- Use page.screenshot() for captures — SCOUT handles baseline comparison (do NOT use toHaveScreenshot)
- Name screenshots descriptively: test-results/item-{id}-{context}.png
- Group related tests in test.describe() blocks
- Add a comment header with generation date and purpose
- Tag tests with @smoke, @visual, @content, @feature as appropriate

Generate ONLY the test file code. Use the helpers — do not rewrite login/navigation logic.`;
}

module.exports = {
  textAnalysisPrompt,
  visionAnalysisPrompt,
  textComparisonPrompt,
  testGenerationSystemPrompt,
};
