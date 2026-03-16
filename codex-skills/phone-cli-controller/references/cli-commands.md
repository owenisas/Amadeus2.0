# CLI Commands

Use these commands from `/Users/user/Documents/Amadeus2.0`.

## Environment

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner doctor --json
```

The `doctor` output is the source of truth for:

- `appium_url`
- `device_serial`
- `gemini_model`
- `gemini_api_key_present`
- `skills_dir`
- `system_skill_file`
- `runs_dir`
- `appium_start_hint`

## Full autonomous run

```bash
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner run --app gmail --goal "Open Gmail and inspect the inbox read-only"
```

Useful flags:

- `--app <registry key>`
- `--goal "<plain language goal>"`
- `--max-steps <n>`

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
/Users/user/Documents/Amadeus2.0/.venv/bin/python -m agent_runner tools run --tool tap --app youtube --args '{"target_box":{"x0":0.10,"y0":0.20,"x1":0.90,"y1":0.28},"target_label":"Search"}'
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
