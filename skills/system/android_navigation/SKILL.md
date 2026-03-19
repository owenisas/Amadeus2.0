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

## Approval gating

- Treat Android permission dialogs, notification prompts, account chooser screens, and feature-onboarding cards as approval-required.
- Summarize the popup using the top visible text and the available action labels.
- If the user approves a specific action, perform only that action and then recapture the screen.

## System navigation

- Use `back` to leave uncertain surfaces before using `home`.
- Avoid destructive system actions, account changes, or settings mutations unless the user asked for them explicitly.

## Automation scripts

- When you identify a repetitive navigation sequence (e.g., search for X, dismiss popup, tap result), save it as a script using the `save_script` tool.
- Scripts are stored per-app under `skills/apps/<app>/scripts/` and can be replayed with `run_script`.
- Before performing a multi-step navigation you have done before, check `list_scripts` to see if a reusable script already exists.
- A script is a JSON object with `name`, `description`, and `steps` (list of action objects).
- Each step has `action` (tap/type/swipe/back/home/wait/launch_app/run_script) and optional fields like `target_label`, `input_text`, `submit_after_input`, `package_name`, `wait_seconds`, `script_name`.
