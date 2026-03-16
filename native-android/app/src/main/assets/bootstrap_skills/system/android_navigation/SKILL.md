---
name: android_navigation
description: System-level Android navigation guidance for dialogs, permissions, onboarding surfaces, and safe handoff to the user.
---

# Android navigation skill

## Purpose

- Guide safe navigation outside any single app.
- Handle system dialogs, permission prompts, onboarding overlays, and app-switching surfaces consistently.

## Core rules

- Auto-dismiss low-risk onboarding cards, one-time promos, and routine permission prompts when that keeps the agent moving toward the goal.
- Only stop for account-selection, sign-in, payment, purchase, or destructive confirmation surfaces.
- Prefer continuing through lightweight setup surfaces instead of stalling on them.

## Approval gating

- Treat account chooser screens, sign-in prompts, payment surfaces, and destructive confirmations as approval-required.
- Permission prompts, onboarding cards, and harmless promos can be handled automatically when they do not change account state or spend money.

## System navigation

- Use `back` to leave uncertain surfaces before using `home`.
- Avoid destructive system actions, account changes, or settings mutations unless the user asked for them explicitly.
