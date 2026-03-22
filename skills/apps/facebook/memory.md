# Facebook memory

- Logged-in phone flow is working on `com.facebook.katana`.

<!-- older entries pruned -->
- Reason: Blocked by risk token 'message seller'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-eff36f66a200ec31

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-immersiveactivity-immersiveactivity-ec62106dc81a4447

- Status: completed
- Reason: Facebook is visible but no stronger Marketplace heuristic was found.
- Last screen: com-facebook-katana-immersiveactivity-immersiveactivity-ec62106dc81a4447

- Status: completed
- Reason: Target 'What do you want to buy?' matched the goal, but no stable target box was available on the current screen.
- Last screen: com-facebook-katana-loginactivity-c9d5167b73120fc4

- Status: completed
- Reason: Facebook Marketplace search surface is visible.
- Last screen: com-facebook-katana-immersiveactivity-immersiveactivity-ec62106dc81a4447

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-loginactivity-8360afff127e14e0

- Status: completed
- Reason: Facebook Marketplace feed has been scanned and no stronger next listing heuristic was found.
- Last screen: com-facebook-katana-loginactivity-4538ccbca69c81cf

- Status: completed
- Reason: Facebook Marketplace feed has been scanned and no stronger next listing heuristic was found.
- Last screen: com-facebook-katana-loginactivity-1a4143c23e563b52

- Status: blocked
- Reason: Tap actions require a target_box.
- Last screen: com-facebook-katana-loginactivity-fbc4a2d495378594

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-b6bb0489920dfd43

- Status: completed
- Reason: Facebook is visible but no stronger Marketplace heuristic was found.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-584837daf88fcc96

- Status: blocked
- Reason: Blocked by risk token 'buy now'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-584837daf88fcc96

- Status: blocked
- Reason: Blocked by risk token 'buy now'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-f94db2a5d767b55c

- Status: blocked
- Reason: Blocked by risk token 'buy now'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-f94db2a5d767b55c

- Status: completed
- Reason: Facebook is visible but no stronger Marketplace heuristic was found.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-c7f9c8239f3d833c

- Marketplace value-scan runs now prefer Gemini `gemini-3.1-pro-preview` decisions on feed/detail surfaces instead of heuristic bypass.
- Label-only listing taps can now hydrate their target box from the current Marketplace screen state.
- Buy-now listing detail pages are treated as read-only inspection surfaces, not automatic stop points.
- Detail-page inspection should proceed in stages: image/title/price, `See more`, one short in-listing swipe for seller/location/condition, then back out.
- Feed scrolling should stay shallow; large full-screen Marketplace swipes tend to skip too many listings.
- Marketplace seller messaging should no longer rely on the default `Hi, is this available?` opener when the goal asks to contact the seller. Prefer a short custom opener that references the listing title, then send it from the inline composer.

- Status: completed
- Reason: Facebook is visible but no stronger Marketplace heuristic was found.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-c7f9c8239f3d833c

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-loginactivity-908153ea0ac53092

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-75f491c819218952
