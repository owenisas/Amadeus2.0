---
name: crowdtap
description: App-specific guidance for Crowdtap on Android.
---

# Crowdtap skill

## Purpose

- Support conservative handling for `com.suzy.droid`.
- Default goal hint: inspect the current surface conservatively and stop if screenshots or hierarchy dumps are blocked.

## Current device reality

- The app is installed on the phone.
- The resolved launch activity is `crc64fb407d7fb80034b3.MainActivity`.
- On this device, the current launch surface is secure: Appium screenshot and UI hierarchy capture fail.

## Safe workflow

- Treat secure-surface failures as a hard stop, not as an action prompt.
- Do not attempt to answer surveys, redeem rewards, or sign in automatically.
- Use only notification hooks or foreground-activity checks until a capturable surface becomes available.

## Notes

- This app is currently not a viable full Appium automation target on the device because the launch surface blocks screenshots and hierarchy capture.
