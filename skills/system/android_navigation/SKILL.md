---
name: android_navigation
description: System-level Android navigation guidance for dialogs, permissions, onboarding surfaces, and safe handoff to the user.
---

# Android navigation skill

## Purpose

- Guide safe navigation outside any single app.
- Handle system dialogs, permission prompts, onboarding overlays, and app-switching surfaces consistently.

## Core rules

- Do not grant, deny, dismiss, or confirm system or app popups without explicit user approval unless the current app skill says the popup is low-risk and safe to continue automatically.
- When a modal dialog, permission prompt, onboarding surface, or account-selection screen appears, stop and ask the user what to do.
- Prefer the least-invasive interpretation of unknown popups.
- Keep the user's end goal primary. Do not stop at the first partial success if the screen still offers a safe, relevant path that moves closer to the actual requested outcome.
- Look for all plausible low-risk completion paths on the current surface before defaulting to `wait`, `stop`, or repeating the same action.
- If one path stalls or leaves the goal incomplete, pivot to the next viable path instead of retrying the identical step indefinitely.
- Prefer reversible exploration in this order:
  1. use a clearly labeled primary action already on screen
  2. use a secondary in-app path such as another tab, section, or tracked game that serves the same goal
  3. back out or reopen the app only after stronger in-app paths are exhausted
- Treat repeated no-op actions as a signal to search for another route, not as evidence that the current route is correct.

## Approval gating

- Treat Android permission dialogs, notification prompts, account chooser screens, and feature-onboarding cards as approval-required.
- Summarize the popup using the top visible text and the available action labels.
- If the user approves a specific action, perform only that action and then recapture the screen.

## System navigation

- Use `back` to leave uncertain surfaces before using `home`.
- Avoid destructive system actions, account changes, or settings mutations unless the user asked for them explicitly.
- When multiple safe routes can satisfy the user's goal, choose the route with the highest expected progress, not just the most familiar one.
- For earning or completion goals, continue chaining safe progress opportunities while they remain visible instead of pausing after a single subtask is done.
- Re-check the goal after every meaningful state change: if the requested outcome is still not achieved, continue with the next best safe action.

## Automation scripts

- When you identify a repetitive navigation sequence (e.g., search for X, dismiss popup, tap result), save it as a script using the `save_script` tool.
- Scripts are stored per-app under `skills/apps/<app>/scripts/` and can be replayed with `run_script`.
- Before performing a multi-step navigation you have done before, check `list_scripts` to see if a reusable script already exists.
- A script is a JSON object with `name`, `description`, and `steps` (list of action objects).
- Each step has `action` (tap/type/swipe/back/home/wait/launch_app/run_script) and optional fields like `target_label`, `input_text`, `submit_after_input`, `package_name`, `wait_seconds`, `script_name`.
