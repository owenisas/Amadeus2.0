---
name: juicycandyquest
description: App-specific guidance for Juicy Candy Quest on Android.
---

# Juicy Candy Quest skill

## Purpose

- Support brief, repeatable gameplay for `com.hideseek.juicycandyquest`.
- Use it only as a tracked earning source for Money Time.

## Current device reality

- The game is installed and launches reliably to `com.unity3d.player.UnityPlayerActivity`.
- It loads to a menu with a large `LEVEL 1` button.
- The first level shows a sticky tutorial overlay that says `Match 3 of the same Candy!`

## Safe workflow

- Wait through the splash screen.
- Tap the large `LEVEL 1` button.
- Treat the tutorial overlay as a temporary blocker; clear it if possible, then make one simple match.
- Count the burst only when the level actually opens, the tutorial changes state, or the board accepts interactions.
- Return to Money Time after the level is clearly active, even if the tutorial remains sticky.
- Avoid banner ads, rewarded ads, shops, or purchases.

## Notes

- The initial install, launch, and in-level session were enough for Money Time to move the game into `Your Games`.
- This is a valid tracked title even though the first tutorial overlay still needs a cleaner automation path.
