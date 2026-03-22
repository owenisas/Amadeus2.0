# Five Surveys notes

- Package: `com.fivesurveys.mobile`
- Launch activity: `.MainActivity`
- On this phone, the landing page renders visually but the UI hierarchy can be sparse or empty, likely due to a webview-style surface.
- Treat login, signup, survey answering, and payout actions as explicit stop points.

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-fivesurveys-mobile-mainactivity-c3b80b40284fbb0d

- Status: manual_login_required
- Reason: Manual login required before automation can continue.

- Status: error
- Reason: App is not installed on the emulator.

- Status: blocked
- Reason: Tap actions require a target_box.
- Last screen: com-fivesurveys-mobile-mainactivity-8395859c0220a598

- Status: completed
- Reason: The goal requests answering a survey question, which violates the safety policy against survey submission, answer selection, or any step that claims completion credit.
- Last screen: com-fivesurveys-mobile-mainactivity-24b2ac8e6f21546d

- Status: completed
- Reason: The first question of the survey is 'Which languages do you speak?'. I have successfully opened the survey and read the first question.
- Last screen: com-fivesurveys-mobile-mainactivity-2bc0dd4117736653

- Status: blocked
- Reason: Blocked by risk token 'submit'.
- Last screen: com-fivesurveys-mobile-mainactivity-56ab6391b9829b7a

- Status: blocked
- Reason: Tap actions require a target_box.
- Last screen: com-fivesurveys-mobile-mainactivity-922cb7682477ba30
