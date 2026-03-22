# Five Surveys notes

- Package: `com.fivesurveys.mobile`

<!-- older entries pruned -->

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

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-fivesurveys-mobile-mainactivity-489b2d5dbd87cb29

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-fivesurveys-mobile-mainactivity-e3b0c44298fc1c14

- Status: completed
- Reason: Answering surveys and claiming completion credit is a restricted risk surface according to the app's skill instructions. I must stop here.
- Last screen: com-fivesurveys-mobile-mainactivity-13aae7674573d028

- Status: blocked
- Reason: Decision confidence below 0.30.
- Last screen: com-fivesurveys-mobile-mainactivity-19779b8afa22d692

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-fivesurveys-mobile-mainactivity-effb182fe8415b71

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-fivesurveys-mobile-mainactivity-90e131aab77eb51c

- Status: completed
- Reason: Five Surveys survey content is visible: Qualification | Which languages do you speak?
- Last screen: com-fivesurveys-mobile-mainactivity-f54b27148e7a4939

- Status: completed
- Reason: Five Surveys survey content is visible: Qualification | Which languages do you speak? | English
- Last screen: com-fivesurveys-mobile-mainactivity-b1dee51d8aea723a

- Status: completed
- Reason: Five Surveys survey content is visible: Qualification | Which languages do you speak? | English
- Last screen: com-fivesurveys-mobile-mainactivity-7fa5756c8cd2f7e8

- Status: blocked
- Reason: Decision confidence below 0.30.
- Last screen: com-fivesurveys-mobile-mainactivity-ebb95de11513a06d

- Status: blocked
- Reason: Tool type actions require tool_arguments.text.
- Last screen: com-fivesurveys-mobile-mainactivity-bc2a4550ce4698e7

- Latest exploration confirms the first featured survey can be opened from the main logged-in feed.
- The successful path was: left `Take Survey` button on the feed, then a bottom-centered overlay control, which advanced to the birthday qualification screen.
- On the birthday screen, the active controls are the focused year input labeled `0.0`, plus `Select Month` and `Select Day`.
- The previous block was runtime-level, not navigation-level: LM Studio emitted `tool_name=type` with `input_text`, while the executor and safety layer only accepted `text`.

- Status: blocked
- Reason: Blocked by risk token 'submit'.
- Last screen: com-fivesurveys-mobile-mainactivity-0ee47b1be60d9b2d

- Status: error
- Reason: App is not installed on the emulator.
