# CLI Commands

Use these commands from `/Users/user/Documents/Amadeus2.0`.

## Environment

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner doctor --json
```

The `doctor` output is the source of truth for:

- `appium_url`
- `device_serial`
- `model_provider`
- `vision_model`
- `gemini_model`
- `gemini_api_key_present`
- `lmstudio_model`
- `lmstudio_base_url`
- `lmstudio_api_key_present`
- `skills_dir`
- `system_skill_file`
- `runs_dir`
- `appium_start_hint`

## Wireless debugging / Wi-Fi ADB

Discover the advertised service when available:

```bash
/Users/user/Library/Android/sdk/platform-tools/adb mdns services
```

Pair from the phone's `Pair device with pairing code` screen:

```bash
/Users/user/Library/Android/sdk/platform-tools/adb pair <ip:pair-port>
```

Connect using the main `IP address & Port` shown on the Wireless debugging screen:

```bash
/Users/user/Library/Android/sdk/platform-tools/adb connect <ip:connect-port>
/Users/user/Library/Android/sdk/platform-tools/adb devices -l
```

Target the wireless device explicitly for CLI runs:

```bash
ANDROID_DEVICE_SERIAL=<ip:connect-port> /Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner doctor --json
ANDROID_DEVICE_SERIAL=<ip:connect-port> /Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool capture_state --args '{}'
```

Notes:

- The pairing port and connect port are different.
- If `adb mdns services` is empty, keep the phone awake on the Wireless debugging screen and use the phone-displayed IP and ports directly.

## Full autonomous run

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner run --app gmail --goal "Open Gmail and inspect the inbox read-only"
```

Useful flags:

- `--app <registry key>`
- `--goal "<plain language goal>"`
- `--max-steps <n>`

## Persistent task workflow

Start a resumable task:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner task start --app settings --goal "Open Settings and navigate to Wi-Fi." --max-steps 2
```

Resume a task:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner task resume --task-id <task-id> --max-steps 2
```

Inspect or cancel a task:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner task show --task-id <task-id>
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner task list --json
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner task cancel --task-id <task-id>
```

Notes:

- Tasks persist checkpoints under the runs directory and can be resumed later.
- Only one unfinished task may own a given device at a time.

## List tools

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools list --json
```

## Capture state

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool capture_state --app gmail --args '{}'
```

Use this before tapping or typing.

## Launch an app

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool launch_app --app youtube --args '{}'
```

Or override package/activity:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool launch_app --args '{"package_name":"com.google.android.youtube","activity":".app.honeycomb.Shell$HomeActivity"}'
```

## Tap using normalized bounds

First capture state, then pass a `target_box`:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool tap --app youtube --args '{"target_box":{"x":0.10,"y":0.20,"width":0.80,"height":0.08},"target_label":"Search"}'
```

## Type and submit

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool type --app playstore --args '{"text":"Number Charm: 2048 Games","submit_after_input":true}'
```

## Swipe, back, home, wait

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool swipe --app gmail --args '{}'
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool back --app gmail --args '{}'
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool home --args '{}'
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool wait --args '{}'
```

## Safe adb inspection

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool adb_shell --args '{"command":"shell pm list packages"}'
```

Use this only for the safe adb patterns already enforced by the tool layer.

## Skill operations

Read:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool read_skill --app youtube --args '{"file_name":"SKILL.md"}'
```

Bootstrap:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool bootstrap_skill --args '{"app_name":"notesapp","package_name":"com.example.notes"}'
```

Write:

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool write_skill_file --app youtube --args '{"file_name":"memory.md","content":"- Learned: search opens from top-right icon\\n"}'
```

## Important file locations

- CLI entrypoint: `/Users/user/Documents/Amadeus2.0/agent_runner/cli.py`
- Tool registry: `/Users/user/Documents/Amadeus2.0/agent_runner/agent_tools.py`
- App registry: `/Users/user/Documents/Amadeus2.0/agent_runner/config.py`
- Repo app skills: `/Users/user/Documents/Amadeus2.0/skills/apps/`
- System navigation skill: `/Users/user/Documents/Amadeus2.0/skills/system/android_navigation/SKILL.md`
- Run artifacts: `/Users/user/Documents/Amadeus2.0/runs/`
