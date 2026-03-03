// SCOUT — Azure AI Foundry Provider
// Implements AI analysis using Azure's OpenAI-compatible API.

const AIProvider = require('./provider');
const prompts = require('./prompts');

class AzureFoundryProvider extends AIProvider {
  constructor(config) {
    super(config);
    this.endpoint = config.azure.endpoint.replace(/\/$/, '');
    this.apiKey = config.azure.apiKey;
    this.textDeployment = config.azure.textDeployment;
    this.visionDeployment = config.azure.visionDeployment;
    this.apiVersion = config.azure.apiVersion;
  }

  async analyzeText(text, language = 'English') {
    const start = Date.now();
    const prompt = prompts.textAnalysisPrompt(text, language);

    const raw = await this._chatCompletion(
      [
        { role: 'system', content: 'You are a proofreading assistant. Respond with ONLY a JSON array. No markdown, no explanation.' },
        { role: 'user', content: prompt },
      ],
      { deployment: this.textDeployment, max_tokens: 1000 }
    );

    const issues = this._parseIssues(raw);
    return {
      issues,
      issuesFound: issues.length > 0,
      raw,
      model: this.textDeployment,
      durationMs: Date.now() - start,
    };
  }

  async analyzeScreenshot(screenshot, context = '') {
    const start = Date.now();
    const base64 = Buffer.isBuffer(screenshot) ? screenshot.toString('base64') : screenshot;
    const prompt = prompts.visionAnalysisPrompt(context);

    const messages = [
      { role: 'system', content: 'You are a visual QA analyst. Respond with ONLY a JSON array. No markdown, no explanation.' },
      {
        role: 'user',
        content: [
          { type: 'text', text: prompt },
          { type: 'image_url', image_url: { url: `data:image/png;base64,${base64}` } },
        ],
      },
    ];

    const raw = await this._chatCompletion(messages, {
      deployment: this.visionDeployment,
      max_tokens: 1000,
    });

    const issues = this._parseIssues(raw);
    return {
      issues,
      issuesFound: issues.length > 0,
      raw,
      model: this.visionDeployment,
      durationMs: Date.now() - start,
    };
  }

  async compareText(baselineText, currentText, language = 'English') {
    const start = Date.now();
    const prompt = prompts.textComparisonPrompt(baselineText, currentText, language);

    const raw = await this._chatCompletion(
      [
        { role: 'system', content: 'You are a proofreading assistant. Respond with ONLY a JSON array. No markdown, no explanation.' },
        { role: 'user', content: prompt },
      ],
      { deployment: this.textDeployment, max_tokens: 1500 }
    );

    const differences = this._parseIssues(raw);
    return {
      differences,
      hasDifferences: differences.length > 0,
      raw,
      model: this.textDeployment,
      durationMs: Date.now() - start,
    };
  }

  async generateTest(description, context = {}) {
    const systemPrompt = prompts.testGenerationSystemPrompt(context.helpers);
    const raw = await this._chatCompletion(
      [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: description },
      ],
      { deployment: this.textDeployment, max_tokens: 2000 }
    );
    return raw;
  }

  async healthCheck() {
    try {
      const raw = await this._chatCompletion(
        [{ role: 'user', content: 'Reply with "ok"' }],
        { deployment: this.textDeployment, max_tokens: 10 }
      );
      return {
        healthy: true,
        provider: 'azure',
        details: {
          endpoint: this.endpoint,
          textDeployment: this.textDeployment,
          visionDeployment: this.visionDeployment,
          response: raw.trim(),
        },
      };
    } catch (err) {
      return {
        healthy: false,
        provider: 'azure',
        details: { error: err.message },
      };
    }
  }

  async _chatCompletion(messages, options = {}) {
    const deployment = options.deployment || this.textDeployment;
    const url = `${this.endpoint}/openai/deployments/${deployment}/chat/completions?api-version=${this.apiVersion}`;

    const body = {
      messages,
      max_completion_tokens: options.max_tokens ?? 1000,
    };

    let lastError;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'api-key': this.apiKey,
          },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(60000),
        });

        if (response.status === 429) {
          const retryAfter = parseInt(response.headers.get('retry-after') || '2', 10);
          const delay = Math.min(retryAfter * 1000, 10000) * (attempt + 1);
          console.warn(`SCOUT: Azure rate limited, retrying in ${delay}ms...`);
          lastError = new Error(`Azure API rate limited (429) after ${attempt + 1} attempts`);
          await new Promise(r => setTimeout(r, delay));
          continue;
        }

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(`Azure API ${response.status}: ${errorBody}`);
        }

        const data = await response.json();
        return data.choices[0].message.content;
      } catch (err) {
        lastError = err;
        if (attempt < 2 && !err.message.includes('401') && !err.message.includes('403')) {
          await new Promise(r => setTimeout(r, 1000 * (attempt + 1)));
          continue;
        }
        throw err;
      }
    }
    throw lastError;
  }
}

module.exports = AzureFoundryProvider;
