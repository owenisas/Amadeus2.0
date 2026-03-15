---
name: youtube
description: App-specific navigation guidance for the YouTube Android workflow.
---

# YouTube skill

## Purpose

- Support safe YouTube navigation for `com.google.android.youtube`.
- Default goal hint: Open YouTube, search for a channel or video, inspect it safely, and require explicit user approval before subscribing or other account actions.

## Navigation conventions

- Prefer search, channel pages, and read-only inspection of visible metadata.
- Use the search box and channel result rows before opening videos.
- When the user asks to subscribe, treat the final subscribe tap as approval-required unless the exact channel match is unambiguous.

## Dynamic components

- Record search fields, search-submit actions, channel result rows, and subscribe buttons in `selectors.json`.
- Keep channel anchors together: channel name, avatar position, verification badge, and subscribe state.

## Risk surfaces to avoid

- Upload, go live, comments, purchases, memberships, Super Chat, and irreversible account edits.

## Known recipes

- `search for a channel`: open search, type the query, submit it, inspect channel results, then stop if the target match is ambiguous.
- `subscribe to a channel`: navigate to the exact channel page and ask for explicit confirmation before the final subscribe action.
