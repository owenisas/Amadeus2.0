---
name: ballsortpuzzle
description: App-specific guidance for Ball Sort Puzzle on Android.
---

# Ball Sort Puzzle skill

## Purpose

- Support brief, repeatable gameplay for `com.hideseek.fruitsortpuzzle`.
- Use it only as a tracked earning source for Money Time.

## Current device reality

- The game is installed and launches reliably to `com.unity3d.player.UnityPlayerActivity`.
- It loads into a simple tube-sorting puzzle with a clear first move pattern.
- The bottom banner is an ad surface and should be avoided.

## Safe workflow

- Wait through the Hide Seek splash screen.
- Once the first level is visible, make a small number of valid moves.
- Count the burst only when the board actually changes or the game shows a post-level `Next` / reward screen.
- If the game shows a post-level `Next` or reward screen, stop there and return to Money Time.
- Do not tap banner ads, rewarded multipliers, shops, or any purchase surfaces.

## Notes

- Completing the first level was enough to move the game into Money Time's `Your Games`.
- This makes it a stable secondary tracked title.
