# Native Android Agent

Native Android implementation of the phone agent, built with Kotlin, AccessibilityService, MediaProjection, an on-device approval overlay, and local skill storage.

## Build

```bash
cd /Users/user/Documents/Amadeus2.0/native-android
./gradlew :app:assembleDebug
```

Debug APK output:

```text
app/build/outputs/apk/debug/app-debug.apk
```

## Runtime setup on phone

1. Install the debug APK.
2. Open the app and enter a Gemini API key.
3. Enable the `Native Agent Control` accessibility service.
4. Grant overlay permission.
5. Grant screen-capture permission from the Home screen.
6. Optional: enable `YOLO mode` from the Home screen or Run Composer if you want the native agent to bypass approval overlays.
7. Start a run from `Run Composer`.

## Current native scope

- Gmail read-only inbox inspection
- Play Store search and free-install scaffolding
- On-device approval overlay for permission prompts and ambiguous popups
- Optional `YOLO mode` that bypasses approval overlays and shows a warning notice in run status/history while still keeping local purchase/destructive safety blocks active
- Local bootstrap skills for:
  - system navigation
  - Gmail
  - Play Store

## Verification

```bash
cd /Users/user/Documents/Amadeus2.0/native-android
./gradlew :app:testDebugUnitTest :app:assembleDebug
```
