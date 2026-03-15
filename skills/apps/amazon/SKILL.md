---
name: amazon
description: App-specific navigation guidance for Amazon Android automation.
---

# Amazon skill

## Purpose

- Support low-risk status checks and detail-reading flows for the Amazon Shopping Android app.
- Treat login as a manual prerequisite.

## Navigation conventions

- Prefer home, account, orders, and tracking pages.
- Use top navigation labels, order cards, and tracking labels as anchors.
- Reuse normalized target boxes only when package, activity, and visible anchor text still match.

## Stable visual anchors

- `Your Orders`
- `Orders`
- `Track package`
- `Arriving`
- `Delivered`
- `Out for delivery`

## Risk surfaces to avoid

- Buy now
- Place your order
- Review your order
- Payment method
- One-click checkout
- Account credential updates

## Known recipes

- `check latest order status`: open Amazon, navigate to orders, open the most recent order, read delivery status, and stop.
- `track current delivery`: prefer existing tracking or order detail screens if they are already visible.
