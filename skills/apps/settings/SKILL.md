---
name: settings
description: App-specific navigation guidance for the Android Settings workflow.
---

# Settings skill

## Purpose

- Support read-only Settings navigation for `com.android.settings`.
- Default goal hint: Navigate and inspect settings pages without changing system state.

## Navigation conventions

- The root Settings page shows a scrollable list of category entries (Network & internet, Connected devices, Apps, etc.).
- Tapping a category opens a sub-settings page.
- Use `back` to return to the parent settings page.
- Read toggle states, storage info, and device details without modifying them.

## Dynamic components

- Record category entry selectors (Network & internet, Display, Battery, etc.) in `selectors.json`.
- Track the current sub-settings page in `state.json`.

## Risk surfaces to avoid

- Factory reset, erase all data, developer options toggles.
- Account additions, removals, or modifications.
- Accessibility service toggling (unrelated to this agent).
- Any toggle or switch that changes system behavior.

## Known recipes

- `open network settings`: launch Settings, tap "Network & internet" or "网络和互联网", stop when the sub-page is visible.
- `check storage`: navigate to Storage, read the usage summary, stop.
- `view device info`: scroll to "About phone" or "About emulated device", tap it, stop when build info is visible.
