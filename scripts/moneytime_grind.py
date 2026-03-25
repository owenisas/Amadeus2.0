#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path


ADB = Path("/Users/user/Library/Android/sdk/platform-tools/adb")
MONEYTIME_PKG = "com.money.time"
SWORDSLASH_PKG = "com.hideseek.swordslash"
BALLSORT_PKG = "com.hideseek.fruitsortpuzzle"
JUICY_PKG = "com.hideseek.juicycandyquest"
TARGET_MONIES = 350_000


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

    def adb(self, *args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
        return run([str(ADB), "-s", self.serial, *args], check=check, capture=capture)

    def log(self, message: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}"
        print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def launch(self, package: str) -> None:
        self.adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

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

    def dump_moneytime_state(self) -> dict[str, str | int | None]:
        remote = "/sdcard/moneytime_grind_state.xml"
        local = Path("/tmp/moneytime/moneytime_grind_state.xml")
        self.launch(MONEYTIME_PKG)
        self.sleep(2)
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
        self.log(f"moneytime_state {json.dumps(state, ensure_ascii=True)}")
        return state

    def recover_from_detour(self, package: str) -> None:
        self.log(f"recover detour package={package}")
        if package and package != MONEYTIME_PKG:
            self.force_stop(package)
            self.sleep(0.8)
        self.keyevent(3)
        self.sleep(1)

    def swordslash_burst(self, rounds: int = 18) -> None:
        self.log("swordslash_burst start")
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
            pkg, activity = self.current_focus()
            if pkg == SWORDSLASH_PKG and "AppLovinFullscreenActivity" not in activity:
                x1, y1, x2, y2 = random.choice(swipe_patterns)
                self.swipe(x1, y1, x2, y2, 100)
                self.sleep(0.45)
                continue
            if pkg in {SWORDSLASH_PKG, "com.android.vending"}:
                self.recover_from_detour(pkg)
                self.force_stop(SWORDSLASH_PKG)
                self.sleep(0.8)
                self.launch(SWORDSLASH_PKG)
                self.sleep(5)
                self.tap(540, 1900)
                self.sleep(1.5)
                continue
            self.recover_from_detour(pkg)
            self.force_stop(SWORDSLASH_PKG)
            self.sleep(0.8)
            self.launch(SWORDSLASH_PKG)
            self.sleep(5)
            self.tap(540, 1900)
            self.sleep(1.5)
        self.keyevent(3)
        self.sleep(1)
        self.log("swordslash_burst end")

    def ballsort_burst(self, rounds: int = 3) -> None:
        self.log("ballsort_burst start")
        for _ in range(rounds):
            self.force_stop(BALLSORT_PKG)
            self.sleep(0.8)
            self.launch(BALLSORT_PKG)
            self.sleep(6)
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
            self.force_stop(JUICY_PKG)
            self.sleep(0.8)
            self.launch(JUICY_PKG)
            self.sleep(6)
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
            # Make a few safe board interactions in the middle of the screen.
            for x, y in ((360, 1180), (540, 1180), (720, 1180), (540, 980), (540, 1360)):
                pkg, activity = self.current_focus()
                if pkg in {"com.android.vending", "com.playwell.playwell"}:
                    self.recover_from_detour(pkg)
                    break
                self.tap(x, y)
                self.sleep(0.45)
            self.keyevent(3)
            self.sleep(1)
        self.log("juicy_burst end")

    def run_until_full(self, max_cycles: int) -> int:
        state = self.dump_moneytime_state()
        monies = int(state["monies"] or 0)
        if monies >= TARGET_MONIES:
            self.log("target already reached")
            return monies

        for cycle in range(1, max_cycles + 1):
            self.log(f"cycle {cycle} start")
            self.swordslash_burst()
            self.ballsort_burst()
            self.juicy_burst()
            state = self.dump_moneytime_state()
            monies = int(state["monies"] or 0)
            if monies >= TARGET_MONIES:
                self.log(f"target reached monies={monies}")
                return monies
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
