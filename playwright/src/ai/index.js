// SCOUT — AI Provider Factory
// Returns the configured AI provider based on AI_PROVIDER environment variable.

const config = require('../config');
const AzureFoundryProvider = require('./azure-foundry');
const OllamaProvider = require('./ollama');
const MockProvider = require('./mock');

let instance = null;

function createAIProvider() {
  if (instance) return instance;

  switch (config.aiProvider) {
    case 'azure':
      instance = new AzureFoundryProvider(config);
      break;
    case 'ollama':
      instance = new OllamaProvider(config);
      break;
    case 'mock':
      instance = new MockProvider(config);
      break;
    default:
      throw new Error(`Unknown AI provider: "${config.aiProvider}". Use azure, ollama, or mock.`);
  }

  console.log(`SCOUT: AI provider initialized — ${config.aiProvider}`);
  return instance;
}

// Export singleton with lazy initialization
module.exports = new Proxy({}, {
  get(_, prop) {
    const provider = createAIProvider();
    if (typeof provider[prop] === 'function') {
      return provider[prop].bind(provider);
    }
    return provider[prop];
  },
});
