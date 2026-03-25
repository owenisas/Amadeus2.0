---
name: moneytime
description: App-specific guidance for Money Time on Android.
---

# Money Time skill

## Purpose

- Support conservative navigation for `com.money.time`.
- Treat the app as a pending-reward tracker, not an immediate cashout path.

## Current device reality

- Onboarding is complete on this phone.
- The app has a 3-hour earning period and converts pending activity into cash only when that window closes.
- The current earning loop uses the `Games` tab and three tracked games:
  - `Sword Slash`
  - `Ball Sort Puzzle`
  - `Juicy Candy Quest`
- The `Cashout` tab currently shows a PayPal minimum of `$0.01`, but the visible cash balance is still `$0.00`.
- Real in-game progress matters. Passive foreground time is not enough by itself; the tracked games have to advance their own play state for the loyalty bar to keep moving.

## Proven workflow

- Use `Home` to monitor:
  - the remaining earning-period timer
  - `MONIES / 350000`
  - the current `CASHOUT` amount
- Use `Games` to:
  - confirm tracked games are listed under `Your Games`
  - launch the highest-yield tracked game again when the conversion window is still open
  - add new games from `New Games` only when the current tracked set is already stable
- Treat `Cashout` as read-only until the visible cash amount is above zero and the user explicitly authorizes redemption.

## Safe workflow

- Keep increasing pending `MONIES` while the timer is counting down.
- Prefer replaying already-attributed games over installing a large number of unknown offers.
- Verify actual progress in the tracked games instead of relying on app-open time alone:
  - `Sword Slash`: menu -> live stage -> successful throws / balance update / stage result
  - `Ball Sort Puzzle`: level entry -> valid moves -> post-level or changed board
  - `Juicy Candy Quest`: level entry -> tutorial cleared or board interactions
- Do not link PayPal, choose a gift card, redeem, or confirm any payout action without explicit user direction.
- Avoid notification prompts and other upsells unless needed to keep the earning loop visible.

## Notes

- The main blocker is time-based conversion, not navigation.
- When the app shows `$0.00 CASHOUT` with substantial pending `MONIES`, continue earning and recheck after the period ends instead of trying to force cashout.
