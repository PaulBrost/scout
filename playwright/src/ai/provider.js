// SCOUT — AI Provider Base Interface
// All providers (Azure, Ollama, Mock) must implement these methods.

class AIProvider {
  constructor(config) {
    this.config = config;
  }

  /**
   * Analyze text for spelling, grammar, and homophone issues.
   * @param {string} text - The text to analyze
   * @param {string} language - 'English' or 'Spanish'
   * @returns {Promise<{issues: Array, issuesFound: boolean, raw: string, model: string, durationMs: number}>}
   */
  async analyzeText(text, language = 'English') {
    throw new Error('analyzeText() not implemented');
  }

  /**
   * Analyze a screenshot for visual issues (readability, layout, contrast).
   * @param {Buffer|string} screenshot - Image buffer or base64 string
   * @param {string} context - Description of what to evaluate
   * @returns {Promise<{issues: Array, issuesFound: boolean, raw: string, model: string, durationMs: number}>}
   */
  async analyzeScreenshot(screenshot, context = '') {
    throw new Error('analyzeScreenshot() not implemented');
  }

  /**
   * Compare two text versions and identify meaningful differences.
   * @param {string} baselineText - Previous version text
   * @param {string} currentText - Current version text
   * @param {string} language - 'English' or 'Spanish'
   * @returns {Promise<{differences: Array, hasDifferences: boolean, raw: string, model: string, durationMs: number}>}
   */
  async compareText(baselineText, currentText, language = 'English') {
    throw new Error('compareText() not implemented');
  }

  /**
   * Generate a Playwright test script from a natural language description.
   * @param {string} description - User's plain-English test description
   * @param {object} context - Available helpers, conventions, examples
   * @returns {Promise<string>} Generated JavaScript test code
   */
  async generateTest(description, context = {}) {
    throw new Error('generateTest() not implemented');
  }

  /**
   * Health check — verify provider is reachable and models are available.
   * @returns {Promise<{healthy: boolean, provider: string, details: object}>}
   */
  async healthCheck() {
    throw new Error('healthCheck() not implemented');
  }

  /**
   * Send a chat completion request. Internal method used by all analysis methods.
   * @param {Array} messages - Chat messages array
   * @param {object} options - Model, temperature, max_tokens, etc.
   * @returns {Promise<string>} The assistant's response content
   */
  async _chatCompletion(messages, options = {}) {
    throw new Error('_chatCompletion() not implemented');
  }

  /**
   * Parse LLM response into structured issue list.
   * Attempts JSON extraction first, falls back to text scanning.
   */
  _parseIssues(rawResponse) {
    if (!rawResponse || !rawResponse.trim()) return [];

    // Try JSON extraction — find the first JSON array in the response
    const jsonMatch = rawResponse.match(/\[[\s\S]*?\]/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[0]);
        if (Array.isArray(parsed)) {
          // Filter out empty/meaningless entries
          return parsed.filter(item => {
            if (!item || typeof item !== 'object') return false;
            // Text analysis: must have non-empty text or suggestion
            if (item.text || item.suggestion) {
              return (item.text && item.text.trim().length > 0) ||
                     (item.suggestion && item.suggestion.trim().length > 0);
            }
            // Vision analysis: must have non-empty detail
            if ('detail' in item) {
              return item.detail && item.detail.trim().length > 0;
            }
            // Comparison: must have baseline or current text
            if ('baseline' in item || 'current' in item) {
              return (item.baseline && item.baseline.trim().length > 0) ||
                     (item.current && item.current.trim().length > 0);
            }
            return false;
          });
        }
      } catch { /* fall through */ }
    }

    // Check for "no issues" language
    const noIssuePatterns = [
      /no issues/i, /no errors/i, /no problems/i,
      /looks correct/i, /all clear/i, /\bclean\b/i,
      /no spelling/i, /no grammar/i, /no defects/i,
      /everything appears/i, /well-formed/i,
    ];

    if (noIssuePatterns.some(p => p.test(rawResponse))) {
      return [];
    }

    // Try extracting individual JSON objects if array parse failed
    const objectMatches = rawResponse.match(/\{[^{}]+\}/g);
    if (objectMatches) {
      const issues = [];
      for (const m of objectMatches) {
        try {
          const obj = JSON.parse(m);
          if (obj.type && (obj.text || obj.detail || obj.suggestion)) {
            issues.push(obj);
          }
        } catch { /* skip */ }
      }
      if (issues.length > 0) return issues;
    }

    // If nothing parseable, return empty — avoid noisy unstructured entries
    return [];
  }
}

module.exports = AIProvider;
