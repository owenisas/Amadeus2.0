---
name: justplay
description: App-specific guidance for JustPlay on Android.
---

# JustPlay skill

## Purpose

- Support conservative navigation for `com.justplay.app`.
- Treat the app as a reward-game candidate with a potentially reachable earning loop, but avoid cash-out or account-risk actions.

## Current device reality

- The app installs successfully from Google Play on this phone.
- The first launch is gated by a MIUI `Chain start` confirmation that asks whether Google Play Store can open JustPlay.
- After launch, the first visible in-app surface is:
  - `#1 Loyalty Program for Gamers`
  - `Welcome to JustPlay, the 24h Rewards App that allows you to earn REAL MONEY for playing games you love!`
  - `OK`
- After clearing the intro dialogs, the app reaches:
  - `Welcome Reward`
  - `Here are 20,000 loyalty coins for you`
  - `Claim Now!`

## Safe workflow

- If the phone shows the MIUI `Chain start` dialog, use `Accept` only to reach the app launch and continue inspection.
- The initial `OK` buttons are benign onboarding acknowledgements and safe tutorial-dismiss actions.
- Treat `Claim Now!` as a higher-risk reward action, not a neutral tutorial dismiss.
- Prefer stopping and recording state at the first reward-claim surface unless the goal explicitly authorizes claiming.
- Do not cash out, link payment methods, or sign in unless the goal explicitly allows it.

## Notes

- Compared with Cash Giraffe, JustPlay progresses deeper into the app and reaches a reward-claim gate.
- The next useful milestone is confirming whether there is a stable offers list behind `Claim Now!` without triggering irreversible reward actions.
