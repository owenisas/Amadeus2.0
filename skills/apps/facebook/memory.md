# Facebook memory

- Logged-in phone flow is working on `com.facebook.katana`.
- The reliable Marketplace route on this phone is `reset_app`, `Back` once if the Messenger backup prompt appears, then `Marketplace, tab 4 of 6` from the home shell.
- The `Back` step must stay conditional on the Messenger backup prompt; sending `Back` from the clean home shell is the wrong path.
- `Menu` -> `Marketplace` is still available as a fallback, but it is slower than the direct Marketplace tab after clean reset.
- Marketplace feed confirms local context with `Location: Bothell, Washington`.
- Facebook home feed exposes a top-right `Messaging` button with bounds roughly `[948,80][1069,201]`.
- Entering Facebook messaging currently triggers a recovery dialog on this phone: `Are you sure?` / `Some of your end-to-end encrypted messages may be missing.` with `CANCEL` and `YES`.
- Treat `Message seller`, `Buy now`, `Contact seller`, `Sell`, and publish/listing flows as blocked surfaces unless the user explicitly asks.
- Marketplace messaging only: reading inboxes, seller reply composers, and `Send` are in scope only when the goal explicitly references Facebook Marketplace; otherwise Marketplace remains read-only.
- In YOLO mode, the Marketplace messaging recovery dialog should be auto-continued without asking the user.
- Do not restrict Marketplace hunting to seeded categories; any local item with strong resale spread and reasonable liquidity is in scope.
- Useful first-pass listing anchors seen in Marketplace feed:
  - `Just listed, $100 · Two 32" LG monitors from costco`
  - `Just listed, $150 · MSI 34 inch curved monitor`
  - `Just listed, $620 · Apple Mac Mini M4 16GB 256GB`

- Status: blocked
- Reason: Blocked by risk token 'buy'.
- Last screen: com-facebook-katana-immersiveactivity-immersiveactivity-ece948708ebeaa90

- Status: blocked
- Reason: Blocked by risk token 'buy'.
- Last screen: com-facebook-katana-immersiveactivity-immersiveactivity-ece948708ebeaa90

- Status: blocked
- Reason: Blocked by risk token 'message seller'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-13f979b0dbaa301b

- Status: blocked
- Reason: Tap actions require a target_box.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-13f979b0dbaa301b

- Status: blocked
- Reason: Blocked by risk token 'purchase'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-3ad1ecd1172d581f

- Status: blocked
- Reason: Blocked by risk token 'message seller'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-3ad1ecd1172d581f

- Status: blocked
- Reason: Blocked by risk token 'message seller'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-3ad1ecd1172d581f

- Status: blocked
- Reason: Blocked by risk token 'message seller'.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-3ad1ecd1172d581f

- Status: completed
- Reason: Facebook Marketplace listing detail is visible for read-only inspection.
- Last screen: com-facebook-katana-activity-react-immersivereactactivity-3ad1ecd1172d581f

- Status: blocked
- Reason: Tap actions require a target_box.
- Last screen: com-facebook-katana-loginactivity-c16645d9323bd8cc

- Status: max_steps_reached
- Reason: Max steps reached.
- Last screen: com-facebook-katana-loginactivity-b1a87975dece3063

- Status: completed
- Reason: Facebook message inbox is visible for read-only inspection.
- Last screen: com-facebook-katana-com-facebook-messaginginblue-inbox-activities-inboxactivity-59a173fa71ac548b

- Status: completed
- Reason: Facebook message inbox is visible for read-only inspection.
- Last screen: com-facebook-katana-com-facebook-messaginginblue-diode-activity-inboxinterstitialactivity-d22697c9437d3449

- Status: completed
- Reason: Target 'Marketplace, tab 4 of 6' matched the goal, but no stable target box was available on the current screen.
- Last screen: com-facebook-katana-loginactivity-cef7d0208059cf64
