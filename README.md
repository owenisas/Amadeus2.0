# Agent Runner

Vision-first Android automation framework for emulator-driven app workflows.

## Quick start

1. Add local secrets in `.env.local` or export them directly:
   `GEMINI_API_KEY=...`
2. Export Android SDK paths and start Appium:
   `export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" ANDROID_HOME="$HOME/Library/Android/sdk" && appium`
3. Run a workflow:
   `python -m agent_runner run --app amazon --goal "check delivery status for my latest order"`
4. To bypass interactive approval prompts for onboarding or permission surfaces, use YOLO mode:
   `python -m agent_runner run --app settings --goal "open network settings" --yolo`
5. To use the local desktop dashboard instead of the terminal:
   `python -m agent_runner gui --open-browser`

## Notes

- The framework uses Appium/UIAutomator2 for execution and supports either Gemini or a local LM Studio model for decisioning.
- Model selection is controlled with `AGENT_RUNNER_MODEL_PROVIDER=gemini|lmstudio`.
- Gemini uses `GEMINI_API_KEY` and `GEMINI_MODEL`.
- LM Studio uses `LMSTUDIO_BASE_URL` and `LMSTUDIO_MODEL` and keeps Gemini available as an alternative provider.
- The built-in GUI shows the registered apps, current device screen mirror, direct control buttons, task controls, and the live event/action trace for the running job.
- If the configured model backend is unavailable, the runtime falls back to conservative local heuristics for development and testability.
- For long-running work, use `task start` and `task resume` instead of a one-shot `run`. Tasks persist checkpoints across runs and enforce one unfinished task per device because the phone screen is not headless.
- Amazon login is treated as a manual prerequisite.
- `--yolo` bypasses interactive approval prompts and emits a warning notice in the run result, but local purchase and destructive-action safety blocks still remain active.
- The current `Medium_Phone_API_36.0` emulator may fail during UiAutomator2 instrumentation startup. If that happens, prefer an API 34/35 automation AVD or re-verify Appium UiAutomator2 compatibility with the emulator image.
