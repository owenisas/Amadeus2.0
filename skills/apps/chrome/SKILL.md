---
name: chrome
description: App-specific navigation guidance for the Chrome Android workflow.
---

# Chrome skill

## Purpose

- Support read-only Chrome browsing automation for `com.android.chrome`.
- Default goal hint: Open Chrome and inspect the current start page without submitting forms.

## Navigation conventions

- Prefer reading page content, scrolling, and navigating via the address bar.
- Treat the New Tab page, bookmarks, and history as safe surfaces.
- Dismiss onboarding / sync prompts using "No thanks", "Not now", or similar affordances.
- Avoid filling forms, submitting data, or signing in.

## Dynamic components

- Record address bar, tab switcher, and menu button selectors in `selectors.json`.
- Track the current page title and URL snippet in `state.json`.

## Risk surfaces to avoid

- Payment forms, checkout pages, and purchase confirmations.
- Sign-in / sync prompts that mutate account state.
- Form submission or data entry on external sites.

## Known recipes

- `open Chrome`: launch Chrome, dismiss onboarding if present, stop when the start page or tab content is visible.
- `navigate to a URL`: tap the address bar, type the URL, submit, wait for page load, stop.
- `search for a topic`: tap the address bar, type the search query, submit, scroll through results read-only.
