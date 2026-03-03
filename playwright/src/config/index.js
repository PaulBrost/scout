// SCOUT — Configuration loader
// Loads environment variables, validates required settings, exports frozen config.

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });

const config = {
  // Assessment application
  assessmentUrl: process.env.ASSESSMENT_URL || 'https://assessment.internal',
  assessmentUsername: process.env.ASSESSMENT_USERNAME || '',
  assessmentPassword: process.env.ASSESSMENT_PASSWORD || '',

  // AI provider
  aiProvider: process.env.AI_PROVIDER || 'mock',
  aiTextEnabled: process.env.AI_TEXT_ENABLED !== 'false',
  aiVisionEnabled: process.env.AI_VISION_ENABLED !== 'false',

  // Azure AI Foundry
  azure: {
    endpoint: process.env.AZURE_AI_ENDPOINT || '',
    apiKey: process.env.AZURE_AI_API_KEY || '',
    textDeployment: process.env.AZURE_AI_TEXT_DEPLOYMENT || 'gpt-4o-mini',
    visionDeployment: process.env.AZURE_AI_VISION_DEPLOYMENT || 'gpt-4o',
    apiVersion: process.env.AZURE_AI_API_VERSION || '2024-10-21',
  },

  // Ollama
  ollama: {
    host: process.env.OLLAMA_HOST || 'http://localhost:11434',
    textModel: process.env.OLLAMA_TEXT_MODEL || 'qwen2.5:14b',
    visionModel: process.env.OLLAMA_VISION_MODEL || 'gemma3:12b',
  },

  // Database
  databaseUrl: process.env.DATABASE_URL || 'postgresql://scout_user:@localhost:5432/scout',

  // Test configuration
  baselineVersion: process.env.BASELINE_VERSION || 'v2024',
  itemTier: process.env.ITEM_TIER || 'smoke',

  // Mock AI mode
  mockAiMode: process.env.MOCK_AI_MODE || 'clean',
};

/**
 * Validates required configuration for the selected AI provider.
 * Throws with a clear message if anything is missing.
 */
function validate() {
  const errors = [];

  if (config.aiProvider === 'azure') {
    if (!config.azure.endpoint) errors.push('AZURE_AI_ENDPOINT is required when AI_PROVIDER=azure');
    if (!config.azure.apiKey) errors.push('AZURE_AI_API_KEY is required when AI_PROVIDER=azure');
  }

  if (config.aiProvider === 'ollama') {
    if (!config.ollama.host) errors.push('OLLAMA_HOST is required when AI_PROVIDER=ollama');
  }

  if (errors.length > 0) {
    console.error('\n❌ SCOUT Configuration Errors:');
    errors.forEach(e => console.error(`   • ${e}`));
    console.error('\n   Copy .env.example to .env and fill in required values.\n');
    process.exit(1);
  }
}

// Validate on load unless explicitly skipped (for tests with mock provider)
if (process.env.SCOUT_SKIP_VALIDATION !== 'true') {
  validate();
}

module.exports = Object.freeze(config);
