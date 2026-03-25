---
name: swordslash
description: App-specific guidance for Sword Slash on Android.
---

# Sword Slash skill

## Purpose

- Support brief, repeatable gameplay for `com.hideseek.swordslash`.
- Use it only as a tracked earning source for Money Time.

## Current device reality

- The game is installed and launches reliably to `com.unity3d.player.UnityPlayerActivity`.
- The game can resume directly into a live stage instead of always returning to a menu.
- The bottom banner area is an ad surface; avoid tapping it.

## Safe workflow

- Prefer short gameplay bursts:
  - launch the app
  - if a `PLAY` button is visible, tap it once
  - if already in a stage, throw a few swords into the target
  - only count the burst as valid if a throw lands, a `Balance Update` appears, or the stage result changes
  - stop after clear progress is visible and return to Money Time
- Do not tap ad banners, rewarded multipliers, store buttons, or purchase prompts.

## Notes

- This is currently the strongest proven Money Time tracked game on the device.
- The purpose is session attribution and light progress, not deep optimization.
