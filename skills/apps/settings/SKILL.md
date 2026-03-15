---
name: settings
description: App-specific navigation guidance for the Settings Android workflow.
---

# Settings skill

## Purpose

- Support low-risk navigation and read-oriented automation for `com.android.settings`.
- Default goal hint: Navigate and inspect settings pages without changing system state.

## Navigation conventions

- Prefer tabs, order/detail pages, and dismissible popups.
- Avoid account mutation flows and irreversible confirmations.
- Use visible text, package/activity, and normalized target boxes together before falling back to blind taps.

## Stable visual anchors

- Preserve the top visible labels for important screens in `screens.json`.
- Reuse selectors only when the current screen signature matches the stored package/activity and anchor text.

## Risk surfaces to avoid

- factory reset, erase all data

## Known recipes

- `check latest order status`: navigate to orders, open the most recent order, read status, then stop.
