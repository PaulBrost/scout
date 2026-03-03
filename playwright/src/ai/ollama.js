// SCOUT — Ollama Provider
// Implements AI analysis using a self-hosted Ollama instance (production/AWS target).

const AIProvider = require('./provider');
const prompts = require('./prompts');

class OllamaProvider extends AIProvider {
  constructor(config) {
    super(config);
    this.host = config.ollama.host.replace(/\/$/, '');
    this.textModel = config.ollama.textModel;
    this.visionModel = config.ollama.visionModel;
  }

  async analyzeText(text, language = 'English') {
    const start = Date.now();
    const prompt = prompts.textAnalysisPrompt(text, language);

    const raw = await this._chatCompletion(
      [{ role: 'user', content: prompt }],
      { model: this.textModel }
    );

    const issues = this._parseIssues(raw);
    return {
      issues,
      issuesFound: issues.length > 0,
      raw,
      model: this.textModel,
      durationMs: Date.now() - start,
    };
  }

  async analyzeScreenshot(screenshot, context = '') {
    const start = Date.now();
    const base64 = Buffer.isBuffer(screenshot) ? screenshot.toString('base64') : screenshot;
    const prompt = prompts.visionAnalysisPrompt(context);

    const raw = await this._chatCompletion(
      [{ role: 'user', content: prompt, images: [base64] }],
      { model: this.visionModel }
    );

    const issues = this._parseIssues(raw);
    return {
      issues,
      issuesFound: issues.length > 0,
      raw,
      model: this.visionModel,
      durationMs: Date.now() - start,
    };
  }

  async compareText(baselineText, currentText, language = 'English') {
    const start = Date.now();
    const prompt = prompts.textComparisonPrompt(baselineText, currentText, language);

    const raw = await this._chatCompletion(
      [{ role: 'user', content: prompt }],
      { model: this.textModel }
    );

    const differences = this._parseIssues(raw);
    return {
      differences,
      hasDifferences: differences.length > 0,
      raw,
      model: this.textModel,
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
      { model: this.textModel }
    );
    return raw;
  }

  async healthCheck() {
    try {
      const response = await fetch(`${this.host}/api/tags`, {
        signal: AbortSignal.timeout(10000),
      });
      if (!response.ok) throw new Error(`Ollama returned ${response.status}`);

      const data = await response.json();
      const modelNames = (data.models || []).map(m => m.name);
      const hasTextModel = modelNames.some(n => n.includes(this.textModel.split(':')[0]));
      const hasVisionModel = modelNames.some(n => n.includes(this.visionModel.split(':')[0]));

      return {
        healthy: hasTextModel && hasVisionModel,
        provider: 'ollama',
        details: {
          host: this.host,
          textModel: this.textModel,
          visionModel: this.visionModel,
          textModelLoaded: hasTextModel,
          visionModelLoaded: hasVisionModel,
          availableModels: modelNames,
        },
      };
    } catch (err) {
      return {
        healthy: false,
        provider: 'ollama',
        details: { error: err.message, host: this.host },
      };
    }
  }

  async _chatCompletion(messages, options = {}) {
    const model = options.model || this.textModel;
    const url = `${this.host}/api/chat`;

    const body = {
      model,
      messages: messages.map(m => {
        const msg = { role: m.role, content: m.content };
        if (m.images) msg.images = m.images;
        return msg;
      }),
      stream: false,
    };

    let lastError;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        // Ollama can be slow on first request (model loading), use longer timeout
        const timeout = attempt === 0 ? 120000 : 60000;
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: AbortSignal.timeout(timeout),
        });

        if (!response.ok) {
          const errorBody = await response.text();
          throw new Error(`Ollama API ${response.status}: ${errorBody}`);
        }

        const data = await response.json();
        return data.message.content;
      } catch (err) {
        lastError = err;
        if (attempt < 2) {
          await new Promise(r => setTimeout(r, 2000 * (attempt + 1)));
          continue;
        }
        throw err;
      }
    }
    throw lastError;
  }
}

module.exports = OllamaProvider;
