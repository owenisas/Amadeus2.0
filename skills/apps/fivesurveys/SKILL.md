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

## Stable visual anchors

- The default landing screen shows the `5 surveys` wordmark, payout brand logos, an email field, a `Continue` button, and social sign-in buttons.
- The current device build may render the landing page visually while returning a sparse or empty XML hierarchy.

## Risk surfaces to avoid

- Login, signup, password reset, or email verification.
- Survey submission, answer selection, or any step that claims completion credit.
- Cash-out, reward redemption, PayPal, Visa, bank, referral, or invite flows.

## Known recipes

- `inspect onboarding`: launch the app, capture state, and stop when the landing page or login gate is visible.
