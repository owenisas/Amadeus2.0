# Agent Runner

Vision-first Android automation framework for emulator-driven app workflows.

## Quick start

1. Add local secrets in `.env.local` or export them directly:
   `GEMINI_API_KEY=...`
2. Export Android SDK paths and start Appium:
   `export ANDROID_SDK_ROOT="$HOME/Library/Android/sdk" ANDROID_HOME="$HOME/Library/Android/sdk" && appium`
3. Run a workflow:
   `python -m agent_runner run --app amazon --goal "check delivery status for my latest order"`

## Notes

- The framework uses Appium/UIAutomator2 for execution and Gemini for decisioning when a key is present.
- If `GEMINI_API_KEY` is not set, or Gemini fails for a run, the runtime falls back to conservative local heuristics for development and testability.
- Amazon login is treated as a manual prerequisite.
- The current `Medium_Phone_API_36.0` emulator may fail during UiAutomator2 instrumentation startup. If that happens, prefer an API 34/35 automation AVD or re-verify Appium UiAutomator2 compatibility with the emulator image.
