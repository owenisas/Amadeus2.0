---
name: chrome
description: App-specific navigation guidance for the Chrome Android workflow.
---

# Chrome skill

## Purpose

- Support low-risk navigation and read-oriented automation for `com.android.chrome`.
- Default goal hint: Open Chrome and inspect the current start page without submitting forms.

## Navigation conventions

- Prefer tabs, order/detail pages, and dismissible popups.
- Avoid account mutation flows and irreversible confirmations.
- Use visible text, package/activity, and normalized target boxes together before falling back to blind taps.

## Stable visual anchors

- Preserve the top visible labels for important screens in `screens.json`.
- Reuse selectors only when the current screen signature matches the stored package/activity and anchor text.

## Risk surfaces to avoid

- payment, checkout, confirm form resubmission

## Known recipes

- `check latest order status`: navigate to orders, open the most recent order, read status, then stop.
