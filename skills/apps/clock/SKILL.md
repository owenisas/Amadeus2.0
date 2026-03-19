---
name: clock
description: App-specific navigation guidance for the Clock Android workflow.
---

# Clock skill

## Purpose

- Support read-only Clock app automation for `com.google.android.deskclock`.
- Default goal hint: Open Clock and inspect the current tab without destructive changes.

## Navigation conventions

- Prefer reading the current time, alarm list, timer, and stopwatch tabs.
- Tab navigation: Alarm, Clock, Timer, Stopwatch are the four bottom tabs.
- Dismiss onboarding or permission prompts safely.
- Avoid creating, editing, or deleting alarms and timers.

## Dynamic components

- Record tab selectors (Alarm, Clock, Timer, Stopwatch) in `selectors.json`.
- Track the currently active tab in `state.json`.

## Risk surfaces to avoid

- Creating or deleting alarms.
- Editing or clearing existing timers.
- Any destructive modification to clock data.

## Known recipes

- `open Clock`: launch the Clock app, wait for the main screen, stop when any tab content is visible.
- `check alarms`: navigate to the Alarm tab, scroll to inspect active alarms, stop.
- `view stopwatch`: navigate to the Stopwatch tab, stop when it is visible.
