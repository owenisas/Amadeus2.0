---
name: facebook
description: App-specific navigation guidance for the Facebook Android workflow.
---

# Facebook skill

## Purpose

- Support low-risk navigation and read-oriented automation for `com.facebook.katana`.
- Default goal hint: Open Facebook, navigate to Marketplace, inspect local listings read-only, and stop before messaging, buying, or publishing anything.

## Navigation conventions

- Prefer tabs, order/detail pages, and dismissible popups.
- Avoid account mutation flows and irreversible confirmations.
- Use visible text, package/activity, and normalized target boxes together before falling back to blind taps.

## Stable visual anchors

- Preserve the top visible labels for important screens in `screens.json`.
- Reuse selectors only when the current screen signature matches the stored package/activity and anchor text.

## Risk surfaces to avoid

- buy now, contact seller, message seller, checkout, payment, publish listing, delete listing

## Known recipes

- `explore the app`: launch the app, inspect the main screen, scroll once if needed, then stop.
