#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal


ADB = Path("/Users/user/Library/Android/sdk/platform-tools/adb")
PROJECT_PYTHON = Path("/Users/user/Documents/Amadeus2.0/.venv/bin/python")
TESSERACT = Path("/opt/homebrew/bin/tesseract")
MONEYTIME_PKG = "com.money.time"
SWORDSLASH_PKG = "com.hideseek.swordslash"
BALLSORT_PKG = "com.hideseek.fruitsortpuzzle"
JUICY_PKG = "com.hideseek.juicycandyquest"
PLAYWELL_PKG = "com.playwell.playwell"
TARGET_MONIES = 350_000
MONEYTIME_HOME_TAB = (135, 2215)


class GrindError(RuntimeError):
    pass


def run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        capture_output=capture,
    )


class Grinder:
    def __init__(self, serial: str, log_path: Path):
        self.serial = serial
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._launch_activity_cache: dict[str, str] = {}

    def adb(self, *args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
        return run([str(ADB), "-s", self.serial, *args], check=check, capture=capture)

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def keep_device_awake(self) -> None:
        # Keep the screen awake while plugged in so the loop does not drift into a black
        # NotificationShade/sleep state between games.
        self.adb("shell", "svc", "power", "stayon", "true", check=False)
        self.adb("shell", "settings", "put", "system", "screen_off_timeout", "1800000", check=False)

    def is_asleep(self) -> bool:
        output = self.adb("shell", "dumpsys", "power").stdout
        return "mWakefulness=Asleep" in output

    def ensure_awake(self) -> None:
        self.keep_device_awake()
        asleep = self.is_asleep()
        if asleep:
            self.adb("shell", "input", "keyevent", "224", check=False)
            self.sleep(1)
        # Dismiss shade/keyguard if present. Avoid bottom-edge swipe while already awake
        # because Xiaomi gesture navigation can open recents instead of helping.
        self.adb("shell", "cmd", "statusbar", "collapse", check=False)
        self.adb("shell", "wm", "dismiss-keyguard", check=False)
        if asleep:
            self.adb("shell", "input", "keyevent", "82", check=False)
            self.adb("shell", "input", "swipe", "540", "1600", "540", "700", "180", check=False)
        self.sleep(0.8)

    def resolve_launch_activity(self, package: str) -> str:
        if package in self._launch_activity_cache:
            return self._launch_activity_cache[package]
        output = self.adb("shell", "cmd", "package", "resolve-activity", "--brief", package).stdout
        activity = ""
        for line in output.splitlines():
            line = line.strip()
            if "/" in line and not line.startswith("priority="):
                activity = line
        if not activity:
            raise GrindError(f"unable to resolve launch activity for {package}")
        self._launch_activity_cache[package] = activity
        return activity

    def launch(self, package: str) -> None:
        self.ensure_awake()
        activity = self.resolve_launch_activity(package)
        self.adb("shell", "am", "start", "-n", activity)

    def force_stop(self, package: str) -> None:
        self.adb("shell", "am", "force-stop", package)

    def keyevent(self, code: int) -> None:
        self.adb("shell", "input", "keyevent", str(code))

    def tap(self, x: int, y: int) -> None:
        self.adb("shell", "input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 100) -> None:
        self.adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def current_focus(self) -> tuple[str, str]:
        output = self.adb("shell", "dumpsys", "window", "displays").stdout
        pkg_match = re.search(r"mCurrentFocus=Window\{[^\s]+\s+u0\s+([^/]+)/", output)
        act_match = re.search(r"mCurrentFocus=Window\{[^\s]+\s+u0\s+[^/]+/([^\s\}]+)", output)
        pkg = pkg_match.group(1) if pkg_match else ""
        act = act_match.group(1) if act_match else ""
        return pkg, act

    def capture_png(self, local_path: Path) -> Path:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        remote = "/sdcard/moneytime_grind_screen.png"
        self.adb("shell", "screencap", "-p", remote)
        self.adb("pull", remote, str(local_path))
        return local_path

    def ocr_image(self, image_path: Path) -> str:
        if not TESSERACT.exists():
            return ""
        result = subprocess.run(
            [str(TESSERACT), str(image_path), "stdout", "--psm", "6"],
            check=False,
            text=False,
            capture_output=True,
        )
        return (result.stdout or b"").decode("utf-8", errors="ignore").strip()

    def classify_swordslash_state(
        self,
        package: str,
        activity: str,
        ocr_text: str,
    ) -> Literal[
        "stage",
        "bonus_modal",
        "playwell_offer",
        "store_detour",
        "fullscreen_ad",
        "launcher_detour",
        "menu",
        "result_restart",
        "unknown",
    ]:
        text = ocr_text.lower()
        if package == "com.android.vending":
            return "store_detour"
        if package == "com.miui.home":
            return "launcher_detour"
        if "restart" in text or ("home" in text and "stage" in text):
            return "result_restart"
        if package == PLAYWELL_PKG or "playwell" in text or "sign in" in text:
            return "playwell_offer"
        if "applovinfullscreenactivity" in activity.lower():
            return "fullscreen_ad"
        if "moneytime" in text and "claim bonus" in text:
            return "bonus_modal"
        if "stage" in text or "balance update" in text or "new best" in text:
            return "stage"
        if package == SWORDSLASH_PKG and "unityplayeractivity" in activity.lower():
            if "play" in text and "stage" not in text:
                return "menu"
            return "stage"
        return "unknown"

    def in_system_overlay(self) -> bool:
        pkg, activity = self.current_focus()
        return pkg == "com.android.systemui" or activity == "NotificationShade"

    def dump_moneytime_state(self) -> dict[str, str | int | None]:
        remote = "/sdcard/moneytime_grind_state.xml"
        local = Path("/tmp/moneytime/moneytime_grind_state.xml")
        state: dict[str, str | int | None] = {
            "monies": None,
            "cashout": None,
            "timer": None,
            "sword_rewards": None,
            "ball_rewards": None,
        }
        for attempt in range(1, 4):
            self.ensure_awake()
            self.launch(MONEYTIME_PKG)
            self.sleep(2 + attempt)
            # Money Time often resumes on Games/Offers or over a modal after returning from
            # a tracked title. Force the Home tab so the loyalty bar can be parsed reliably.
            self.tap(*MONEYTIME_HOME_TAB)
            self.sleep(1)
            self.adb("shell", "uiautomator", "dump", remote, check=False)
            self.adb("pull", remote, str(local))
            text = local.read_text(encoding="utf-8", errors="ignore")
            monies_match = re.search(r"(\d+)&#10;/ 350000&#10;MONIES", text)
            cashout_match = re.search(r"\$(\d+\.\d\d)&#10;CASHOUT", text)
            timer_match = re.search(r"Fill the Loyalty Progress before the end of the timer: &#10;([^\"<]+)", text)
            sword_match = re.search(r"Rewards&#10;Granted&#10;([\d ]+)&#10;Sword Slash", text)
            ball_match = re.search(r"Rewards&#10;Granted&#10;([\d ]+)&#10;Ball Sort Puzzle", text)
            state = {
                "monies": int(monies_match.group(1)) if monies_match else None,
                "cashout": cashout_match.group(1) if cashout_match else None,
                "timer": timer_match.group(1) if timer_match else None,
                "sword_rewards": sword_match.group(1).replace(" ", "") if sword_match else None,
                "ball_rewards": ball_match.group(1).replace(" ", "") if ball_match else None,
            }
            if state["monies"] is not None:
                break
            self.keyevent(4)
            self.sleep(1)
        if state["monies"] is None:
            state = self.dump_moneytime_state_via_agent_runner()
        self.log(f"moneytime_state {json.dumps(state, ensure_ascii=True)}")
        return state

    def dump_moneytime_state_via_agent_runner(self) -> dict[str, str | int | None]:
        self.ensure_awake()
        self.launch(MONEYTIME_PKG)
        self.sleep(2)
        self.tap(*MONEYTIME_HOME_TAB)
        self.sleep(1)
        env = dict(os.environ)
        env["ANDROID_DEVICE_SERIAL"] = self.serial
        result = subprocess.run(
            [
                str(PROJECT_PYTHON),
                "-m",
                "agent_runner",
                "tools",
                "run",
                "--tool",
                "capture_state",
                "--app",
                "moneytime",
                "--args",
                "{}",
            ],
            check=False,
            text=True,
            capture_output=True,
            cwd="/Users/user/Documents/Amadeus2.0",
            env=env,
        )
        state: dict[str, str | int | None] = {
            "monies": None,
            "cashout": None,
            "timer": None,
            "sword_rewards": None,
            "ball_rewards": None,
        }
        if result.returncode != 0 or not result.stdout.strip():
            return state
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return state
        visible = payload.get("captured_state", {}).get("visible_text", []) or []
        text = "\n".join(str(item) for item in visible)
        monies_match = re.search(r"(\d+)\s*/\s*350000\s*MONIES", text)
        cashout_match = re.search(r"\$(\d+\.\d\d)\s*CASHOUT", text)
        timer_match = re.search(
            r"Fill the Loyalty Progress before the end of the timer:\s*([0-9hms ]+)",
            text,
        )
        sword_match = re.search(r"Rewards\s*Granted\s*([\d ]+)\s*Sword Slash", text)
        ball_match = re.search(r"Rewards\s*Granted\s*([\d ]+)\s*Ball Sort Puzzle", text)
        state["monies"] = int(monies_match.group(1)) if monies_match else None
        state["cashout"] = cashout_match.group(1) if cashout_match else None
        state["timer"] = timer_match.group(1).strip() if timer_match else None
        state["sword_rewards"] = sword_match.group(1).replace(" ", "") if sword_match else None
        state["ball_rewards"] = ball_match.group(1).replace(" ", "") if ball_match else None
        return state

    def recover_from_detour(self, package: str) -> None:
        self.log(f"recover detour package={package}")
        if package and package != MONEYTIME_PKG:
            self.force_stop(package)
            self.sleep(0.8)
        self.ensure_awake()
        self.keyevent(3)
        self.sleep(1)

    def swordslash_burst(self, rounds: int = 36) -> None:
        self.log("swordslash_burst start")
        self.ensure_awake()
        self.force_stop(SWORDSLASH_PKG)
        self.sleep(0.8)
        self.launch(SWORDSLASH_PKG)
        self.sleep(6)
        # Main menu PLAY button.
        self.tap(540, 1900)
        self.sleep(2)
        swipe_patterns = [
            (540, 1700, 540, 880),
            (260, 1220, 820, 1220),
            (820, 1000, 260, 1460),
            (260, 1000, 820, 1460),
            (250, 980, 840, 1360),
            (840, 980, 260, 1360),
        ]
        for index in range(rounds):
            self.ensure_awake()
            pkg, activity = self.current_focus()
            screenshot = self.capture_png(Path("/tmp/moneytime/sword_state.png"))
            state = self.classify_swordslash_state(pkg, activity, self.ocr_image(screenshot))
            if index % 6 == 0:
                self.log(f"sword_state package={pkg} activity={activity} state={state}")

            if state == "bonus_modal":
                self.tap(540, 1770)
                self.sleep(1.2)
                continue

            if state == "result_restart":
                # Static game-over screen; restart instead of wasting the burst on a dead board.
                self.tap(540, 1500)
                self.sleep(1.2)
                continue

            if state == "menu":
                self.tap(540, 1900)
                self.sleep(1.2)
                continue

            if state == "stage":
                x1, y1, x2, y2 = random.choice(swipe_patterns)
                self.swipe(x1, y1, x2, y2, 100)
                self.sleep(0.3)
                continue

            if state in {"playwell_offer", "store_detour", "fullscreen_ad", "launcher_detour"}:
                self.recover_from_detour(pkg)
                self.force_stop(SWORDSLASH_PKG)
                self.sleep(0.8)
                self.launch(SWORDSLASH_PKG)
                self.sleep(5)
                self.tap(540, 1900)
                self.sleep(1.0)
                continue

            if pkg in {SWORDSLASH_PKG, PLAYWELL_PKG, "com.android.vending"}:
                self.recover_from_detour(pkg)
                self.force_stop(SWORDSLASH_PKG)
                self.sleep(0.8)
                self.launch(SWORDSLASH_PKG)
                self.sleep(5)
                self.tap(540, 1900)
                self.sleep(1.0)
                continue
            self.recover_from_detour(pkg)
            self.force_stop(SWORDSLASH_PKG)
            self.sleep(0.8)
            self.launch(SWORDSLASH_PKG)
            self.sleep(5)
            self.tap(540, 1900)
            self.sleep(1.0)
        self.keyevent(3)
        self.sleep(1)
        self.log("swordslash_burst end")

    def ballsort_burst(self, rounds: int = 3) -> None:
        self.log("ballsort_burst start")
        for _ in range(rounds):
            self.ensure_awake()
            self.force_stop(BALLSORT_PKG)
            self.sleep(0.8)
            self.launch(BALLSORT_PKG)
            self.sleep(6)
            pkg, activity = self.current_focus()
            if self.in_system_overlay():
                self.ensure_awake()
                self.launch(BALLSORT_PKG)
                self.sleep(4)
                pkg, activity = self.current_focus()
            if pkg not in {BALLSORT_PKG, "com.android.vending"}:
                self.recover_from_detour(pkg)
                continue
            if pkg == "com.android.vending":
                self.recover_from_detour(pkg)
                continue
            # Tap the level button repeatedly to enter gameplay.
            for y in (1820, 1860, 1900):
                self.tap(540, y)
                self.sleep(0.8)
            # Known approximate tube positions. These moves are harmless if still on the level screen.
            tube_left = (250, 840)
            tube_mid = (540, 840)
            tube_right = (830, 840)
            moves = [
                (tube_left, tube_mid),
                (tube_mid, tube_right),
                (tube_mid, tube_right),
                (tube_left, tube_right),
                (tube_left, tube_mid),
                (tube_left, tube_mid),
                (tube_left, tube_mid),
                (tube_mid, tube_right),
            ]
            for (x1, y1), (x2, y2) in moves:
                pkg, activity = self.current_focus()
                if pkg == "com.android.vending":
                    self.recover_from_detour(pkg)
                    break
                self.tap(x1, y1)
                self.sleep(0.25)
                self.tap(x2, y2)
                self.sleep(0.65)
            self.keyevent(3)
            self.sleep(1)
        self.log("ballsort_burst end")

    def juicy_burst(self, rounds: int = 2) -> None:
        self.log("juicy_burst start")
        for _ in range(rounds):
            self.ensure_awake()
            self.force_stop(JUICY_PKG)
            self.sleep(0.8)
            self.launch(JUICY_PKG)
            self.sleep(6)
            pkg, activity = self.current_focus()
            if self.in_system_overlay():
                self.ensure_awake()
                self.launch(JUICY_PKG)
                self.sleep(4)
                pkg, activity = self.current_focus()
            if pkg == "com.android.vending":
                self.recover_from_detour(pkg)
                continue
            if pkg != JUICY_PKG:
                self.recover_from_detour(pkg)
                continue
            # Main menu LEVEL 1 button.
            for y in (1750, 1820, 1890):
                self.tap(540, y)
                self.sleep(0.8)
            # Dismiss tutorial overlay if present.
            self.tap(520, 1750)
            self.sleep(0.8)
            # Use short swaps in the middle board area so this is real match-3 progress.
            swaps = [
                (420, 1160, 560, 1160),
                (560, 1160, 700, 1160),
                (560, 1020, 560, 1160),
                (420, 1300, 560, 1300),
                (560, 1300, 700, 1300),
                (560, 1160, 560, 1300),
            ]
            for x1, y1, x2, y2 in swaps:
                self.ensure_awake()
                pkg, activity = self.current_focus()
                if pkg in {"com.android.vending", "com.playwell.playwell"}:
                    self.recover_from_detour(pkg)
                    break
                self.swipe(x1, y1, x2, y2, 180)
                self.sleep(0.8)
            self.keyevent(3)
            self.sleep(1)
        self.log("juicy_burst end")

    def run_until_full(self, max_cycles: int) -> int:
        self.ensure_awake()
        state = self.dump_moneytime_state()
        monies = int(state["monies"] or 0)
        if monies >= TARGET_MONIES:
            self.log("target already reached")
            return monies

        flat_sword_cycles = 0
        for cycle in range(1, max_cycles + 1):
            self.log(f"cycle {cycle} start")
            previous_monies = monies
            previous_sword = int(str(state["sword_rewards"] or "0").replace(" ", ""))
            previous_ball = int(str(state["ball_rewards"] or "0").replace(" ", ""))

            # Sword Slash is the highest-yield title on this account, so always try it first.
            self.swordslash_burst(rounds=36)
            state = self.dump_moneytime_state()
            monies = int(state["monies"] or 0)
            sword_rewards = int(str(state["sword_rewards"] or "0").replace(" ", ""))
            ball_rewards = int(str(state["ball_rewards"] or "0").replace(" ", ""))
            monies_delta = monies - previous_monies
            self.log(
                "post_sword "
                + json.dumps(
                    {
                        "monies_delta": monies_delta,
                        "sword_rewards_delta": sword_rewards - previous_sword,
                        "ball_rewards_delta": ball_rewards - previous_ball,
                    },
                    ensure_ascii=True,
                )
            )
            if monies >= TARGET_MONIES:
                self.log(f"target reached monies={monies}")
                return monies

            if monies_delta > 0:
                flat_sword_cycles = 0
                continue

            flat_sword_cycles += 1
            # Only fall back if Sword Slash flatlines multiple cycles in a row.
            if flat_sword_cycles < 2:
                continue

            # If Sword Slash did not move the loyalty bar for multiple cycles, add a short
            # Ball Sort burst as a recovery path instead of wasting the whole window.
            if monies_delta <= 0:
                previous_monies = monies
                previous_ball = ball_rewards
                self.ballsort_burst(rounds=2)
                state = self.dump_moneytime_state()
                monies = int(state["monies"] or 0)
                ball_rewards = int(str(state["ball_rewards"] or "0").replace(" ", ""))
                self.log(
                    "post_ballsort "
                    + json.dumps(
                        {
                            "monies_delta": monies - previous_monies,
                            "ball_rewards_delta": ball_rewards - previous_ball,
                        },
                        ensure_ascii=True,
                    )
                )
                if monies >= TARGET_MONIES:
                    self.log(f"target reached monies={monies}")
                    return monies
                if monies > previous_monies:
                    flat_sword_cycles = 0
        raise GrindError(f"target not reached after {max_cycles} cycles")


def main() -> int:
    parser = argparse.ArgumentParser(description="Grind Money Time loyalty progress")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--max-cycles", type=int, default=50)
    parser.add_argument(
        "--log-path",
        default="/tmp/moneytime/grind.log",
        help="Path to append grind logs",
    )
    args = parser.parse_args()

    grinder = Grinder(serial=args.serial, log_path=Path(args.log_path))
    try:
        monies = grinder.run_until_full(max_cycles=args.max_cycles)
    except GrindError as exc:
        grinder.log(f"error {exc}")
        return 1
    grinder.log(f"done monies={monies}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
