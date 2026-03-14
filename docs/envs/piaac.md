# PIAAC (Translation Portal)

The PIAAC Translation Quality Assurance portal. A WordPress-based application for reviewing translated assessment items across countries and languages. Items open in popup windows and may have multiple screens per item.

## Connection

| Setting | Value |
|---|---|
| Base URL | Configured per deployment |
| Auth Type | `username_password` (WordPress auth) |
| Credentials | Username + password stored in environment config |

## Portal Navigation

Unlike NAEP/CRA which uses a single dropdown to launch a test, PIAAC uses cascading filter dropdowns:

```
Login → Portal page
  → Version dropdown (#VerSelect)
    → Country dropdown (#CountrySelect) — populates after version selected
      → Language dropdown (#LangSelect) — populates after country selected
        → Domain dropdown (#DomainSelect) — populates after language selected
          → Item list appears as clickable links
            → Click item → opens in popup window
```

Each dropdown triggers a `change` event that populates the next dropdown. There's a delay between selections as the server fetches dependent data.

## Filter Defaults

| Filter | Selector | Default Value |
|---|---|---|
| Version | `#VerSelect` | `FT New` |
| Country | `#CountrySelect` | `ZZZ` |
| Language | `#LangSelect` | `eng` |
| Domain | `#DomainSelect` | `LITNew` |

## Item Structure

Items appear as `<li data-unit="U504-Crayons">` elements after filtering. Each item:
- Opens in a **new browser window** (popup) when clicked
- May contain **multiple screens** (navigated via Next/Finish buttons)
- May render content inside an **iframe** (configurable via `content_frame` selector)

## Item Navigation Selectors

Configured via `launcher_config.item_selectors` in the environment admin:

| Selector | Purpose | Example |
|---|---|---|
| `next_button` | Advances to next screen within item | `button:has-text("Next")` |
| `finish_button` | Indicates last screen / ends item | `button:has-text("Finish")` |
| `continue_button` | Confirmation or proceed prompt | `button:has-text("Continue")` |
| `close_button` | Closes/exits the item view | `button:has-text("Close")` |
| `content_frame` | If content renders inside an iframe | `iframe#content` |

These selectors are read by `navigateItemScreens()` at runtime. If not configured, the function returns defaults of `null` (no navigation attempted).

## Helpers Used

- **`login(page, { env })`** — WordPress login (from `auth.js`)
- **`selectFilters(page, { version, country, language, domain })`** — Cascading dropdown selection
- **`getItemLinks(page)`** — Waits for and extracts item links after filtering (polls up to 15s)
- **`openItem(portalPage, itemId)`** — Clicks an item link and returns the popup Page
- **`navigateItemScreens(itemPage, envConfig, onScreen)`** — Walks all screens in an item using configurable selectors
- **`extractItemContent(itemPage)`** — Extracts text from item page (handles iframes)
- **`getItemSelectors(envConfig)`** — Reads button selectors from environment config

## Baseline Test Pattern

```javascript
const { test } = require('@playwright/test');
const { login } = require('../src/helpers/auth');
const { selectFilters, getItemLinks, openItem, navigateItemScreens } = require('../src/helpers/piaac');

function loadEnvConfig() {
  return process.env.SCOUT_ENV_CONFIG ? JSON.parse(process.env.SCOUT_ENV_CONFIG) : {};
}

test('Baseline screenshots — PIAAC items', async ({ page }) => {
  test.setTimeout(300000);
  const envConfig = loadEnvConfig();
  await login(page, { env: envConfig });
  await selectFilters(page, { version: 'FT New', country: 'ZZZ', language: 'eng', domain: 'LITNew' });
  const items = await getItemLinks(page);

  for (const item of items) {
    const itemPage = await openItem(page, item.itemId);
    await navigateItemScreens(itemPage, envConfig, async (pg, idx) => {
      await pg.screenshot({ path: `test-results/${item.itemId}-screen-${idx}.png`, fullPage: true });
    });
    await itemPage.close();
  }
});
```

## Cross-Locale Comparison Pattern

```javascript
// Compare translated items against English baseline
await selectFilters(page, { version: 'FT New', country: 'ROU', language: 'ron', domain: 'LITNew' });
const items = await getItemLinks(page);

for (const item of items) {
  const itemPage = await openItem(page, item.itemId);
  const screenshot = await itemPage.screenshot({ fullPage: true });
  // Compare against stored baseline...
  await itemPage.close();
}
```

## Recommended `launcher_config`

```json
{
  "item_selectors": {
    "next_button": "button:has-text('Next')",
    "finish_button": "button:has-text('Finish')",
    "continue_button": "button:has-text('Continue')",
    "close_button": "button:has-text('Close')",
    "content_frame": "iframe#content"
  }
}
```

Adjust selectors to match the specific PIAAC deployment. The `content_frame` is important — many PIAAC items render inside an iframe.

## Known Behaviors

- **Cascading dropdowns**: Each filter takes ~2 seconds to load the next dropdown's options. The `selectFilters()` helper handles this with `waitForSelectOptions()`.
- **Popup windows**: Items open in new browser tabs/windows. Always call `itemPage.close()` after processing to avoid resource leaks.
- **Multi-screen items**: Some items have multiple pages. `navigateItemScreens()` handles this automatically using the configured selectors.
- **Content in iframes**: If `content_frame` is configured, button clicks target the iframe's content rather than the outer page.
- **Item link detection**: `getItemLinks()` tries `li[data-unit]` first, then falls back to text matching for `U###` patterns.
