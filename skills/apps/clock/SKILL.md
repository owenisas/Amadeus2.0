---
name: clock
description: App-specific navigation guidance for the Clock Android workflow.
---

# Clock skill

## Purpose

- Support low-risk navigation and read-oriented automation for `com.google.android.deskclock`.
- Default goal hint: Open Clock and inspect the current tab without destructive changes.

## Navigation conventions

- Prefer tabs, order/detail pages, and dismissible popups.
- Avoid account mutation flows and irreversible confirmations.
- Use visible text, package/activity, and normalized target boxes together before falling back to blind taps.

## Stable visual anchors

- Preserve the top visible labels for important screens in `screens.json`.
- Reuse selectors only when the current screen signature matches the stored package/activity and anchor text.

## Risk surfaces to avoid

- delete alarm, clear timers

## Known recipes

- `check latest order status`: navigate to orders, open the most recent order, read status, then stop.
