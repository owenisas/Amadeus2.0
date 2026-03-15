---
name: playstore
description: App-specific navigation guidance for the Playstore Android workflow.
---

# Playstore skill

## Purpose

- Support Play Store search, result selection, free app/game installs, and post-install verification for `com.android.vending`.
- Default goal hint: Search the Play Store, open a free app or game page, install it only when explicitly requested, then stop when `Open` or `Play` appears.

## Navigation conventions

- Prefer current hierarchy components over remembered taps.
- Treat the Google Play Games promo as an interstitial. First try `以后再说` or `Not now`; if it repeats, use `Back`.
- For search: focus the search box, type the query, press Enter, then open the top result matching the query text.
- On app detail pages, prefer the combined install target labeled `安装 | 在更多设备上安装` or `Install | Install on more devices`.
- During download or install (`等待中`, `%`, `正在安装`, `取消`), wait instead of tapping again.
- Stop only when the page exposes an installed-state action such as `打开`, `Open`, `开始游戏`, or `卸载`.

## Stable visual anchors

- Search results pages expose full-width tappable rows with the app title and metadata.
- Detail pages expose a wide install control above the screenshots section.
- Installed pages expose `卸载` plus `开始游戏` or `打开`.

## Risk surfaces to avoid

- Paid, subscription, or purchase surfaces.
- Any page showing a price, currency, `付费`, `购买`, `Purchase`, or `Subscribe`.

## Known recipes

- `search for maps`: open search, submit the query, stop when the search results page is visible.
- `install free game "Number Charm: 2048 Games"`:
  - dismiss the Play Games promo if present
  - search for the requested title
  - open the top result matching the title
  - tap the wide install button
  - wait through `等待中`, progress %, and `正在安装`
  - stop when `开始游戏`, `打开`, or `卸载` appears
