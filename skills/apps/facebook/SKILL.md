---
name: facebook
description: App-specific navigation guidance for the Facebook Android workflow.
---

# Facebook skill

## Purpose

- Support low-risk Android automation for `com.facebook.katana`.
- Default goal hint: Open Facebook, navigate to Marketplace, inspect local listings read-only, and stop before messaging, buying, or publishing anything.

## Navigation conventions

- Record stable visible text, package/activity pairs, and normalized boxes before reusing a selector.
- Prefer screen summaries, hierarchy components, and known selectors over blind coordinate taps.
- After `reset_app`, expect Facebook to occasionally show a Messenger backup or recovery prompt before the main shell; use `Back` to dismiss it and return to the clean home view.
- Prefer the direct `Marketplace, tab 4 of 6` route from the clean home shell.
- Keep `Menu` -> `Marketplace` as the fallback route if the Marketplace tab is not visible on the current build.
- In Marketplace, prefer the `For you` and `Local` surfaces first, then use the top-right `What do you want to buy?` search entry for targeted queries.

## Dynamic components

- Note the Menu tab target, the `Marketplace` shortcut tile, the Marketplace search button, sub-tabs, and listing cards in `selectors.json`.
- Persist Menu-to-Marketplace transitions and Bothell-area listing feed signatures in `state.json`.
- Persist contacted listings, Marketplace thread summaries, latest seller replies, and reusable listing detail context in `data/backup.json` and the concise operator summary in `data/backup.md`.

## Risk surfaces to avoid

- Purchases, contacting sellers, listing creation, account mutations, and irreversible confirmation dialogs.
- Default Marketplace scans remain read-only unless the goal explicitly asks to read messages, reply, or send a message.

## Marketplace workflow

- Before using a reusable Marketplace shortcut, reset Facebook to a clean main view instead of resuming a stale deep-linked screen.
- For Marketplace listing, scan, search, or seller-contact goals, always normalize back to the Marketplace start flow instead of continuing from a stale listing detail, message thread, help page, or other deep-linked Facebook surface.
- If reset opens a Messenger backup or recovery prompt, use `Back` once to return to the main Facebook home shell.
- When saving or replaying a Marketplace script, make the backup-prompt dismissal conditional on that prompt actually being visible; do not send `Back` unconditionally from the clean home shell.
- From the clean home shell, open `Marketplace, tab 4 of 6`.
- If the direct Marketplace tab is unavailable, fall back to `Menu` -> `Marketplace`.
- Confirm the Marketplace shell by looking for `Sell`, `For you`, `Local`, `Location: Bothell, Washington`, and the search button labeled `What do you want to buy?`.
- Build candidates from the Marketplace feed first before doing any targeted searches.
- Keep the workflow read-only: open listings, inspect price, title, condition text, seller details, and the product image already visible in the listing screenshot, then stop short of `Message seller`, `Buy now`, `Contact seller`, or any save/publish action.
- If the listing detail exposes a `See more` description expander, use it once before leaving so the full description and condition notes are captured.
- Do not back out of a listing immediately after the image loads. Inspect detail in order:
  1. visible product image, title, and price
  2. description expander such as `See more`
  3. one short in-listing swipe to reveal seller, location, condition, pickup, or shipping details if they are not already visible
  4. back out only after those read-only details have been inspected
- Use the product image to infer obvious condition cues when possible: cracked glass, dents, scratches, worn upholstery, panel damage, missing accessories, or mismatched parts.
- If the text does not confirm important specs and the images do not make them obvious, treat the listing as incomplete and be ready to ask the seller for the missing specs.
- If condition is not described in text and the images do not make condition obvious, treat that as an information gap and ask the seller directly about current condition.
- On Marketplace feed screens, prefer short swipes that advance about one row of cards instead of large feed jumps that skip multiple listings.

## Marketplace messaging workflow

- Messaging actions are only in scope when the goal explicitly asks for Facebook Marketplace messages, Marketplace replies, Marketplace chat, or messaging a seller.
- Do not use this workflow for general Facebook inbox automation outside Marketplace.
- From the Facebook home feed, the top-right `Messaging` button is the entry point into Marketplace-related message surfaces when the goal explicitly references Marketplace.
- Marketplace listing detail can expose a reply composer via the `Hello, is this still available?` text input and nearby `Send` button.
- Prefer reading inboxes and threads first. Only type or send when the goal includes the exact Marketplace reply intent.
- Before rereading a long Marketplace thread from the beginning, consult `data/backup.md` and `data/backup.json` for the latest known thread summary, seller reply, and contacted-item context.
- After sending seller messages during an active scan, periodically check the Marketplace-related inbox again before messaging more new listings so seller replies are not missed.
- When the goal asks to contact a Marketplace seller but does not provide exact message text, compare the ask price against a profitable target first. If the ask price is too high for a profitable flip, start with a direct offer instead of an availability check.
- Use short human wording. Do not send robotic templates like `Hi, is this available?` when the runtime can derive a more specific opener from the listing.
- Never paste the full Marketplace listing title into the opener. Reduce it to a short natural reference like `the MacBook Air`, `your gaming PC`, `the Canon lens`, or `the monitor`.
- Example: for a `MacBook Air M2 13-inch 16GB 256GB` listed at `$700`, the profitable target is `$450`, so the opener should be closer to `Hey, if it's in good shape, would you take $450 for your MacBook Air?`
- If the listing is already at or below the profitable target, fall back to a short custom availability opener such as `Hey, is your MacBook Air still available?`
- If key specs or current condition are still unclear after checking the text and visible product image, ask the seller for the missing details instead of guessing. Example: `Hey, can you share the specs and current condition for your MacBook Air?`
- Buyer meetup preference for Marketplace deals is `University of Washington Bothell`. When arranging a meetup without a more specific user instruction, prefer proposing that location first.
- If the seller says the item is `pickup only`, ask for the exact address or at least the closest usable cross streets before assuming the meetup is settled.
- When the thread backup already contains seller location or pickup details, use that backup context instead of asking the seller to repeat the same information.
- Keep follow-up buyer messages short and practical: availability first, then meetup location, then pickup address only when needed.
- If Facebook shows the recovery dialog `Are you sure?` with the warning about end-to-end encrypted messages being missing, treat it as a recoverable gating surface.
- In YOLO mode, auto-continue through that Marketplace messaging recovery prompt instead of asking the user.
- Save reusable scripts for `open_messages_from_home`, `open_marketplace_message_composer`, and stable Marketplace reply flows once selectors are confirmed.

## Deal focus

- Do not limit discovery to fixed item categories.
- Target any listing that appears locally resellable with meaningful spread between asking price and likely resale value.
- Prefer items with strong liquidity, clear brand/model identification, and visible condition that can be assessed from photos.
- Favor local pickup or meetup listings over shipping-only offers.
- Record image-based condition notes before deciding whether a listing looks cheap relative to comps.
- Bias strongly toward higher-value electronics and premium furniture with obvious resale demand: iPhone, MacBook, iMac, Mac mini, gaming PCs, RTX GPUs, cameras, ultrawide/OLED monitors, Herman Miller, Steelcase, and similar items.
- De-prioritize cheap accessories and low-value filler such as phone cases, screen protectors, cables, chargers, and vague small add-ons unless the listing is bundled unusually well.

## Value heuristics

- Prioritize listings that look underpriced relative to obvious market cues, not just listings in preselected categories.
- Strong candidates usually combine:
  - recognizable product with repeat demand
  - enough listing detail to estimate resale value
  - low visible damage or repair risk
  - local pickup in a realistic driving radius
  - asking price that leaves room for resale margin after time and effort
- Keep obvious low-liquidity junk, damaged bulk lots, vague mystery bundles, and shipping-first listings lower priority unless the discount is unusually strong.
- If a listing has unclear model, poor photos, or ambiguous condition, lower confidence even if the price looks attractive.
