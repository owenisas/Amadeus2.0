# Money Time memory

- Package: `com.money.time`
- Onboarding is complete on this phone.
- The app explicitly converts pending progress after each 3-hour earning period.
- The current working tabs are `Home`, `Games`, `Offers`, and `Cashout`.
- `Home` is the fastest place to read the timer, `MONIES`, and current `$0.00 CASHOUT` state.
- `Games` is the working earning loop.
- Proven tracked games:
  - `Sword Slash`
  - `Ball Sort Puzzle`
  - `Juicy Candy Quest`
- Keep replaying tracked games while the earning timer is running.
- Count a game burst only when the game itself advances:
  - `Sword Slash`: throws land, balance update appears, or the stage result changes
  - `Ball Sort Puzzle`: the board changes or a level clear/result appears
  - `Juicy Candy Quest`: level start, tutorial dismissal, or board interactions succeed
- Do not attempt payout until the visible cash balance is above zero.
