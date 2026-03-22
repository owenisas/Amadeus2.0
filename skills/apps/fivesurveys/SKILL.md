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
- Treat the landing page as an onboarding and account gate, not as a survey-solving surface.
- Prefer current hierarchy components when they exist, but expect the first screen to behave like a webview and sometimes expose little or no UIAutomator text.
- If the screen shows email entry, social sign-in buttons, payout branding, or sign-up prompts, stop unless the user explicitly asked for account setup.
- On the logged-in main feed, the first featured survey is reachable from the left-side `Take Survey` button near `x=0.09, y=0.30`.
- After entering a survey, a qualification overlay can appear on top of the feed; the overlay is the active surface even if the underlying survey cards remain in the hierarchy.
- The birthday qualification step exposes a focused year `text_input` labeled `0.0`, plus `Select Month` and `Select Day`. Use those overlay controls instead of tapping through the obscured feed beneath.

## Stable visual anchors

- The default landing screen shows the `5 surveys` wordmark, payout brand logos, an email field, a `Continue` button, and social sign-in buttons.
- The current device build may render the landing page visually while returning a sparse or empty XML hierarchy.
- The logged-in feed shows `Current Balance`, `Claim Reward`, and multiple `Take Survey` cards.
- The qualification birthday screen shows `Qualification`, `Just a few questions before the survey`, `Enter your birthday`, `Select Month`, and `Select Day`.

## Risk surfaces to avoid

- Login, signup, password reset, or email verification.
- Survey submission, answer selection, or any step that claims completion credit.
- Cash-out, reward redemption, PayPal, Visa, bank, referral, or invite flows.

## Known recipes

- `inspect onboarding`: launch the app, capture state, and stop when the landing page or login gate is visible.
- `open first featured survey`: from the logged-in feed, tap the left `Take Survey` CTA, then use the overlay controls from the qualification screen rather than the feed components that remain visible underneath.
