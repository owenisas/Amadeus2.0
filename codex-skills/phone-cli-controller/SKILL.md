---
name: phone-cli-controller
description: Control an Android emulator or connected Android device from the terminal using the Amadeus agent_runner CLI in /Users/user/Documents/Amadeus2.0. Use when asked to open apps, inspect screens, tap/type/swipe, run goal-driven phone workflows, debug Appium or Gemini phone runs, or update per-app phone skills from live captures.
---

# Phone CLI Controller

Use this skill to drive the desktop CLI controller in `/Users/user/Documents/Amadeus2.0` instead of manually inventing adb/Appium commands.

## Scope

- Use the Python CLI at `/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner`.
- Target the Appium/UIAutomator2 path in this repo, not the native Android APK.
- Operate on the configured device from `agent_runner doctor`.
- Update repo app skills under `/Users/user/Documents/Amadeus2.0/skills/apps/<app>/` when the user asks to teach or stabilize an app workflow.

## Start Here

1. Run `doctor --json` first to confirm:
   - device serial
   - Appium URL
   - Gemini key presence
   - skills directory
   - runs directory
2. If Appium is not running, use the `appium_start_hint` from `doctor`.
3. If the task is exploratory or flaky, start with direct tools before a full autonomous run.

Read [references/cli-commands.md](references/cli-commands.md) for the exact commands and outputs used in this repo.

## Decision Rule

Use the smallest control surface that can solve the task.

- Use `tools run --tool capture_state` to inspect the current UI before acting.
- Use direct tools for deterministic actions:
  - `launch_app`
  - `tap`
  - `type`
  - `swipe`
  - `back`
  - `home`
  - `wait`
  - `adb_shell`
- Use `run --app ... --goal ...` when the user wants the phone agent to reason through a workflow.
- Use `bootstrap_skill`, `read_skill`, and `write_skill_file` when the task is to teach the agent an app or preserve working knowledge.

## Workflow

### 1. Verify runtime

- Run `doctor --json`.
- If the requested app is unknown, inspect `/Users/user/Documents/Amadeus2.0/agent_runner/config.py` and either add a registry entry or use `bootstrap_skill` if the repo already supports that path.
- If the user references a specific emulator, set `ANDROID_DEVICE_SERIAL` explicitly for the command you run.

### 1a. Connect over wireless debugging when needed

- If `adb devices -l` does not show the target phone, use the `adb_path` from `doctor --json`.
- On the phone, open `Developer options > Wireless debugging`.
- Use `Pair device with pairing code` when there is no existing ADB session.
- Run `adb pair <ip:pair-port>` with the pairing code shown on the phone.
- Then read the main `IP address & Port` value from the Wireless debugging screen and run `adb connect <ip:connect-port>`.
- Verify with `adb devices -l` before running the CLI.
- For all CLI commands that should target the wireless phone, set `ANDROID_DEVICE_SERIAL=<ip:connect-port>`.
- Appium does not need separate wireless setup beyond using the correct `ANDROID_DEVICE_SERIAL`.

### 2. Inspect before acting

- Capture state first unless the task is only to print config or list tools.
- Read:
  - visible text
  - clickable text
  - parsed components
  - screenshot path and hierarchy dump in the run directory
- Prefer hierarchy-backed actions over blind coordinate guesses.

### 3. Act conservatively

- Prefer `launch_app` over raw adb for normal app launches.
- Prefer `tap` with the current captured `target_box`.
- Use `type` with `submit_after_input=true` when search or enter is part of the workflow.
- Use `swipe` only after confirming the current screen content.
- Use `adb_shell` only for safe inspection or launch helpers already allowed by the tool layer.

### 4. Run autonomous workflows

- Use `run --app <app> --goal "<goal>"` for goal-driven tasks.
- Keep goals concrete and bounded.
- Increase `--max-steps` only when the workflow genuinely needs more exploration.
- After the run, inspect:
  - `status`
  - `reason`
  - `steps`
  - `run_dir`

### 5. Teach the agent

- When a new screen or stable action is discovered, update the app skill.
- Keep durable selectors based on:
  1. visible text or content descriptions
  2. resource IDs or hierarchy traits
  3. normalized bounds
  4. coordinate fallback only when nothing else exists
- Update only the needed files:
  - `SKILL.md` for procedural guidance
  - `screens.json` for screen signatures
  - `selectors.json` for reusable targets
  - `state.json` for learned transitions or current durable state
  - `memory.md` for short human-readable notes that help the next run

## Safety Rules

- Do not log into accounts, create accounts, or enter credentials for the user.
- Do not perform purchases, subscriptions, destructive actions, or account-setting changes unless the user explicitly asks and the app policy allows it.
- Treat ambiguous popups, account choosers, and irreversible confirmations as approval points.
- Prefer read-only inspection when the user’s intent is unclear.

## Debugging

- Prefer `tools run --tool capture_state` and inspect the newest files in `/Users/user/Documents/Amadeus2.0/runs/tool-debug/`.
- For autonomous runs, inspect the returned `run_dir` first.
- When a flow stalls:
  - recapture state
  - compare visible text and package/activity
  - read the app skill files for stale assumptions
  - only then patch skill files or app registry

## Output

When you finish:

- report the exact command(s) used
- summarize what the phone agent saw and did
- link the most relevant run directory or skill files
- state clearly if the result came from direct tool control versus the autonomous `run` loop
