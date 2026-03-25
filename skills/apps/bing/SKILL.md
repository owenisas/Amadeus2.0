---
name: bing
description: App-specific guidance for Microsoft Bing on Android.
---

# Microsoft Bing skill

## Purpose

- Support conservative navigation for `com.microsoft.bing`.
- Default goal hint: use Bing Rewards surfaces conservatively to earn points online without purchases.

## Current device reality

- The app is installed on the phone.
- The app no longer blocks on first run. `Maybe later` is a safe way past the Copilot intro.
- The stable earning path is inside `com.microsoft.sapphire.runtime.templates.TemplateActivity` on the Rewards surface.
- The observed Rewards state can reach `Today's points 80/80` with:
  - `Search to earn` capped at `50/50`
  - `Read to earn` capped at `30/30`

## Safe workflow

- If the app opens on the Copilot intro, tap `Maybe later`.
- From the main Bing shell, tap the `Rewards` tile on the home surface.
- Use reward tasks, not ad hoc exploration, when the goal is to earn value.
- `Search to earn` works reliably even when the page still shows `Join to claim`.
- `Read to earn` works by opening real news articles from the Bing home feed, waiting a few seconds on the article, then backing out.
- Prefer distinct article titles for `Read to earn`; duplicate article opens may not increment points.
- Do not sign in, redeem points, or complete purchases.
- If `Join to claim` opens a microphone permission prompt, deny it. Do not grant extra permissions.

## Notes

- Reliable point loop discovered on this device:
  1. Open Rewards
  2. Complete `Search to earn` tasks until the badge shows `50/50`
  3. Return to the Bing home feed
  4. Open unique news articles for `Read to earn`
  5. Recheck Rewards until `80/80`
- Useful future flows: persist daily point totals in backup, detect if the app resets to onboarding, and automate the article-reading loop with better article deduping.
