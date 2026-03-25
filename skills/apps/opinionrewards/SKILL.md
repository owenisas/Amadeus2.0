---
name: opinionrewards
description: App-specific guidance for Google Opinion Rewards on Android.
---

# Google Opinion Rewards skill

## Purpose

- Support conservative navigation for `com.google.android.apps.paidtasks`.
- Default goal hint: inspect survey availability and balance read-only.

## Current device reality

- The app is installed on the phone.
- The observed launch surface was `.onboarding.WarmWelcomeActivity`.
- The current visible error is: `Setup encountered an error, please try again later.`

## Safe workflow

- Treat the app as read-only unless the user explicitly asks otherwise.
- If the launch surface shows setup, account, or verification prompts, stop and report them.
- Do not answer surveys or submit responses automatically.
- Do not attempt redemptions or payout actions.

## Notes

- Useful targets are survey availability, account/setup state, and visible balance.
- If the app recovers from the current setup error later, record the new stable screens in `screens.json` and `selectors.json`.
