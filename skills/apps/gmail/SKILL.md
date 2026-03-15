---
name: gmail
description: App-specific navigation guidance for the Gmail Android workflow.
---

# Gmail skill

## Purpose

- Support read-only Gmail automation for `com.google.android.gm`.
- Default goal hint: Open Gmail, inspect the inbox read-only, and stop without composing, replying, deleting, or archiving.

## Navigation conventions

- Treat the inbox list as the primary safe surface.
- Allow at most light scrolling through the inbox when the user asks to look through emails.
- Prefer visible inbox anchors like `Inbox`, `Primary`, `Social`, `Promotions`, `收件箱`, and `主要`.

## Dynamic components

- Record message-list rows, inbox tabs, and search boxes in `selectors.json` when observed.
- Do not reuse selectors from compose or reply surfaces.

## Risk surfaces to avoid

- Compose, send, reply, reply all, forward, delete, archive, spam, move-to, and label actions.

## Known recipes

- `open Gmail and look through emails`: launch Gmail, wait for the inbox, scroll once if needed, then stop.
