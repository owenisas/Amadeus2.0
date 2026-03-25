---
name: cashgiraffe
description: App-specific guidance for Cash Giraffe on Android.
---

# Cash Giraffe skill

## Purpose

- Support conservative navigation for `cashgiraffe.app`.
- Treat the app as a reward-game candidate, but do not assume it is safe to cash out or profitable yet.

## Current device reality

- The app installs successfully from Google Play on this phone.
- The first launch is gated by a MIUI `Chain start` confirmation that asks whether Google Play Store can open Cash Giraffe.
- After launch, the first visible in-app screen is a consent gate:
  - `Welcome to Cash Giraffe!`
  - `Play games and earn money or gift cards!`
  - `Complete sign up and earn 3,599`
  - `Accept`
  - `Reject`

## Safe workflow

- If the phone shows the MIUI `Chain start` dialog, use `Accept` only to reach the app launch and continue inspection.
- Once inside the app, stop at the first consent or account gate unless the goal explicitly authorizes proceeding further.
- Do not assume the game offer wall is usable until the consent/onboarding flow is cleared.
- Do not sign in, link accounts, cash out, or submit payment details without explicit user direction.

## Notes

- The app likely relies on onboarding consent and installed-app tracking before showing offers.
- This makes it a viable candidate for later automation, but it is not yet a proven earning path on this device.
