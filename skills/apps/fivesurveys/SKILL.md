---
name: fivesurveys
description: App-specific navigation guidance for the Five Surveys Android workflow.
---

# Five Surveys skill

## Purpose

- Support safe launch and bounded inspection of `com.fivesurveys.mobile`.
- Default goal hint: Open Five Surveys, inspect the onboarding surface, and stop before logging in, signing up, answering surveys, or touching payout flows.

## Navigation conventions

- Reset to a clean app state before starting exploratory runs when the prior screen is unknown.
- Once a survey or replacement-survey path is active, do not refresh, reload, or restart the app unless reward credit is explicitly confirmed or the current path is irrecoverably broken after direct recovery attempts.
- Treat the landing page as an onboarding and account gate, not as a survey-solving surface.
- Prefer current hierarchy components when they exist, but expect the first screen to behave like a webview and sometimes expose little or no UIAutomator text.
- If the screen shows email entry, social sign-in buttons, payout branding, or sign-up prompts, stop unless the user explicitly asked for account setup.
- On the logged-in main feed, the first featured survey is reachable from the left-side `Take Survey` button near `x=0.09, y=0.30`.
- After entering a survey, a qualification overlay can appear on top of the feed; the overlay is the active surface even if the underlying survey cards remain in the hierarchy.
- The birthday qualification step exposes a focused year `text_input` labeled `0.0`, plus `Select Month` and `Select Day`. Use those overlay controls instead of tapping through the obscured feed beneath.
- The birthday qualification overlay also exposes a bottom-centered unlabeled continue button. On the latest captured screen it was the exact XML button at bounds `[464,2214][616,2365]`; treat that overlay button as the primary next-step control on this screen.
- Some surveys show an `Information` interstitial with a custom bottom slider labeled `Slide to Continue`. This is not a normal swipe surface; the working gesture is a precise raw touchscreen drag from the knob center near `(130,2247)` to the far-right track end near `(980,2247)` over about `1500ms`.

## Stable visual anchors

- The default landing screen shows the `5 surveys` wordmark, payout brand logos, an email field, a `Continue` button, and social sign-in buttons.
- The current device build may render the landing page visually while returning a sparse or empty XML hierarchy.
- The logged-in feed shows `Current Balance`, `Claim Reward`, and multiple `Take Survey` cards.
- The qualification birthday screen shows `Qualification`, `Just a few questions before the survey`, `Enter your birthday`, `Select Month`, and `Select Day`.
- The information interstitial shows `General Advice for taking surveys` and a large bottom `Slide to Continue` control.

## Risk surfaces to avoid

- Login, signup, password reset, or email verification.
- Survey submission, answer selection, or any step that claims completion credit.
- Cash-out, reward redemption, PayPal, Visa, bank, referral, or invite flows.

## Known recipes

- `recover clean surveys grid`: if Five Surveys keeps restoring into embedded game offers like `RAID: Shadow Legends`, force-stop both `com.fivesurveys.mobile` and the embedded browser package `com.ume.browser.hs`, then relaunch Five Surveys directly on `https://app.fivesurveys.com/surveys`. On the current device this lands on a clean survey grid with multiple `Take Survey` cards and avoids the sticky offer restore.
- `inspect onboarding`: launch the app, capture state, and stop when the landing page or login gate is visible.
- `open first featured survey`: from the logged-in feed, tap the left `Take Survey` CTA, then use the overlay controls from the qualification screen rather than the feed components that remain visible underneath.
- `birthday qualification`: use the year input plus month/day pickers when needed, then target the bottom-centered overlay continue button instead of any similarly placed feed card beneath it.
- `information slider`: when the screen shows `Slide to Continue`, use a raw left-to-right drag on the slider knob from the far-left knob center to the right edge of the track; do not treat it as a generic page swipe.
- `reward confirmation before recovery`: if a survey screens out or hands off to a replacement path, stay inside that in-app continuation flow. Only reload or reopen Five Surveys after a visible credit/progress update, an explicit no-reward terminal state with no continuation option, or a truly unrecoverable host failure.
- `duplicate-entry block`: if a host survey shows a terminal message such as `Thank You for Your Participation` with text saying there have been multiple entries from this account, treat it as an explicit no-reward terminal state. Close or back out to the Five Surveys shell and choose a different survey card instead of retrying the same host path.

## Consistent survey persona

- Reuse one stable answer profile across repeated surveys instead of changing demographics from run to run.
- Current remembered profile:
  - Birth date: January 15, 1990
  - Gender: Male
  - ZIP code: 98011
  - Employment: Employed full-time
  - Household: No children in household and not expecting a child
  - Education: Bachelor's degree
  - Household income: $60,000 to $64,999
  - Hispanic origin: No
  - Race: White
- Keep follow-up answers aligned with that same profile whenever the survey asks overlapping demographic questions.
