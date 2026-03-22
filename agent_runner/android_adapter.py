from __future__ import annotations

from contextlib import contextmanager, suppress
import fcntl
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from agent_runner.models import BoundingBox, DeviceInfo, ScreenState, VisionDecision
from agent_runner.utils import (
    denormalize_box,
    ensure_directory,
    extract_ui_components,
    extract_visible_text,
    sha256_file,
    timestamp_slug,
)


class AndroidAdapter:
    ADB_TIMEOUT_SECONDS = 20.0
    UI_STABLE_FOR_SECONDS = 0.75
    UI_POLL_INTERVAL_SECONDS = 0.25
    PLACEHOLDER_PNG = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
        b"\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    def __init__(
        self,
        *,
        appium_url: str,
        device_serial: str,
        adb_path: str,
        android_sdk_root: str | None = None,
    ) -> None:
        self.appium_url = appium_url
        self.device_serial = device_serial
        self.adb_path = adb_path
        self.android_sdk_root = android_sdk_root
        self._driver = None

    @contextmanager
    def session_lock(self):
        lock_dir = ensure_directory(Path(tempfile.gettempdir()) / "agent_runner-locks")
        lock_path = lock_dir / f"{self.device_serial}.lock"
        with lock_path.open("w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def connect(self) -> None:
        if self._driver is not None:
            return
        try:
            from appium import webdriver
            from appium.options.android import UiAutomator2Options
            from selenium.common.exceptions import WebDriverException
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Appium dependencies are missing. Install with `pip install -e .[dev]`."
            ) from exc
        if self.android_sdk_root:
            os.environ.setdefault("ANDROID_SDK_ROOT", self.android_sdk_root)
            os.environ.setdefault("ANDROID_HOME", self.android_sdk_root)

        options = UiAutomator2Options()
        options.platform_name = "Android"
        options.automation_name = "UiAutomator2"
        options.device_name = self.device_serial
        options.udid = self.device_serial
        options.no_reset = True
        options.auto_grant_permissions = False
        options.new_command_timeout = 180
        options.set_capability("appium:uiautomator2ServerLaunchTimeout", 120000)
        options.set_capability("appium:uiautomator2ServerInstallTimeout", 120000)
        for attempt in range(1, 4):
            try:
                self._driver = webdriver.Remote(self.appium_url, options=options)
                return
            except WebDriverException as exc:
                self._driver = None
                message = str(exc)
                if not self._is_recoverable_session_error(message) or attempt == 3:
                    if "instrumentation process cannot be initialized" in message.casefold():
                        raise RuntimeError(
                            "UiAutomator2 failed to start after retries. "
                            "Ensure only one Appium session is using this emulator. "
                            "API 34/35 automation AVDs are recommended because API 36 images are often unstable."
                        ) from exc
                    raise
                self._reset_uiautomator2_services()
                time.sleep(float(attempt))
            except Exception as exc:  # pragma: no cover - transport stack varies by machine
                self._driver = None
                message = str(exc)
                if self._is_appium_unavailable_error(message):
                    raise RuntimeError(
                        f"Appium server is unavailable at {self.appium_url}. "
                        "Start Appium and retry."
                    ) from exc
                raise

    def close(self) -> None:
        if self._driver is None:
            return
        with suppress(Exception):
            self._driver.quit()
        self._driver = None

    def is_package_installed(self, package_name: str) -> bool:
        result = self._adb(["shell", "pm", "path", package_name], check=False)
        return result.returncode == 0 and "package:" in result.stdout

    def adb_command(
        self,
        args: list[str],
        *,
        check: bool = False,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self._adb(args, check=check, timeout=timeout)

    def launch_app(self, package_name: str, activity: str | None = None) -> None:
        self.connect()
        assert self._driver is not None
        try:
            if activity:
                self._driver.start_activity(package_name, activity)
            else:
                self._driver.activate_app(package_name)
        except Exception as exc:
            monkey = self._adb(
                ["shell", "monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
                check=False,
            )
            if monkey.returncode != 0:
                resolved = self._adb(
                    ["shell", "cmd", "package", "resolve-activity", "--brief", package_name],
                    check=False,
                )
                if "No activity found" in resolved.stdout:
                    raise RuntimeError(
                        f"{package_name} is installed on {self.device_serial} but this emulator image has no launchable activity for it. "
                        "Use a Play Store-enabled system image if you need to automate the Play Store app."
                    ) from exc
                raise RuntimeError(
                    f"Failed to launch {package_name} on {self.device_serial}. "
                    f"`monkey` exited with status {monkey.returncode}: {monkey.stderr.strip() or monkey.stdout.strip()}"
                ) from exc
        self.wait_for_stable_ui(1.5)

    def reset_app(self, package_name: str, activity: str | None = None) -> None:
        self._adb(["shell", "am", "force-stop", package_name], check=False)
        time.sleep(0.75)
        self.launch_app(package_name, activity)

    def capture_state(self, run_dir: Path) -> ScreenState:
        self.connect()
        assert self._driver is not None
        try:
            return self._capture_state_once(run_dir)
        except Exception as exc:
            if not self._is_recoverable_session_error(str(exc)):
                raise
            self.close()
            self.connect()
            return self._capture_state_once(run_dir)

    def _capture_state_once(self, run_dir: Path) -> ScreenState:
        assert self._driver is not None
        ensure_directory(run_dir)
        stamp = timestamp_slug()
        screenshot_path = run_dir / f"{stamp}.png"
        hierarchy_path = run_dir / f"{stamp}.xml"
        size = self._window_size()
        package_name, activity_name = self.current_focus()
        orientation = self._orientation()
        try:
            self._driver.get_screenshot_as_file(str(screenshot_path))
            xml_source = self._driver.page_source
        except Exception as exc:
            if not self._is_secure_surface_error(str(exc)):
                raise
            screenshot_path.write_bytes(self.PLACEHOLDER_PNG)
            xml_source = self._uiautomator_dump_xml()
        hierarchy_path.write_text(xml_source, encoding="utf-8")
        density = self._wm_density()
        visible_text, clickable_text = extract_visible_text(xml_source)
        components = extract_ui_components(
            xml_source,
            width=int(size["width"]),
            height=int(size["height"]),
        )
        return ScreenState(
            screenshot_path=screenshot_path,
            hierarchy_path=hierarchy_path,
            screenshot_sha256=sha256_file(screenshot_path),
            xml_source=xml_source,
            visible_text=visible_text,
            clickable_text=clickable_text,
            package_name=package_name,
            activity_name=activity_name,
            device=DeviceInfo(
                serial=self.device_serial,
                width=int(size["width"]),
                height=int(size["height"]),
                density=density,
                orientation=orientation,
                package_name=package_name,
                activity_name=activity_name,
            ),
            components=components,
        )

    def perform(self, decision: VisionDecision, state: ScreenState) -> None:
        self.connect()
        assert self._driver is not None

        if decision.next_action == "tap":
            if not decision.target_box:
                raise RuntimeError("Tap action requires a target box.")
            resolved_box = self._resolve_tap_box(decision.target_box, state)
            pixel_box = denormalize_box(resolved_box, state.device.width, state.device.height)
            center_x = pixel_box.x + (pixel_box.width / 2.0)
            center_y = pixel_box.y + (pixel_box.height / 2.0)
            self._driver.execute_script(
                "mobile: clickGesture",
                {"x": int(center_x), "y": int(center_y)},
            )
        elif decision.next_action == "swipe":
            self._driver.execute_script(
                "mobile: swipeGesture",
                {
                    "left": int(state.device.width * 0.1),
                    "top": int(state.device.height * 0.2),
                    "width": int(state.device.width * 0.8),
                    "height": int(state.device.height * 0.6),
                    "direction": "up",
                    "percent": 0.7,
                },
            )
        elif decision.next_action == "type":
            if not decision.input_text:
                raise RuntimeError("Type action requires input_text.")
            safe_text = decision.input_text.replace(" ", "%s")
            self._adb(["shell", "input", "text", safe_text], check=True)
            if decision.submit_after_input:
                self._adb(["shell", "input", "keyevent", "66"], check=True)
        elif decision.next_action == "back":
            self._driver.back()
        elif decision.next_action == "home":
            self._driver.press_keycode(3)
        elif decision.next_action == "wait":
            self.wait_for_stable_ui(2.0)
        elif decision.next_action == "stop":
            return
        else:
            raise RuntimeError(f"Unsupported action '{decision.next_action}'.")
        self.wait_for_stable_ui(1.0)

    def _resolve_tap_box(self, requested_box: BoundingBox, state: ScreenState) -> BoundingBox:
        candidates: list[BoundingBox] = []
        for component in state.components:
            if component.get("enabled") is False:
                continue
            if not component.get("clickable"):
                continue
            candidate = BoundingBox.from_dict(component.get("target_box"))
            if candidate is None:
                continue
            candidates.append(candidate.clamp())
        if not candidates:
            return requested_box.clamp()

        requested = requested_box.clamp()
        request_center = requested.center()
        request_anchor = (requested.x, requested.y)
        scored: list[tuple[int, float, float, int, float, BoundingBox]] = []
        for candidate in candidates:
            raw_anchor_contains = self._point_in_box(request_anchor, candidate)
            center_contains = self._point_in_box(request_center, candidate)
            overlap = self._box_iou(requested, candidate)
            anchor_distance = self._center_distance(request_anchor, candidate.center())
            center_distance = self._center_distance(request_center, candidate.center())
            area = candidate.width * candidate.height
            scored.append(
                (
                    1 if raw_anchor_contains else 0,
                    anchor_distance,
                    area,
                    1 if center_contains else 0,
                    center_distance,
                    candidate,
                )
            )

        scored.sort(key=lambda item: (-item[0], item[1], item[2], -item[3], item[4]))
        best_raw_anchor_contains, best_anchor_distance, _, best_center_contains, best_center_distance, best_box = scored[0]

        if best_raw_anchor_contains or best_center_contains:
            return best_box
        if best_anchor_distance <= 0.12 or best_center_distance <= 0.12:
            return best_box
        return requested

    @staticmethod
    def _point_in_box(point: tuple[float, float], box: BoundingBox) -> bool:
        px, py = point
        return box.x <= px <= (box.x + box.width) and box.y <= py <= (box.y + box.height)

    @staticmethod
    def _center_distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def _box_iou(a: BoundingBox, b: BoundingBox) -> float:
        ax1, ay1 = a.x, a.y
        ax2, ay2 = a.x + a.width, a.y + a.height
        bx1, by1 = b.x, b.y
        bx2, by2 = b.x + b.width, b.y + b.height
        inter_left = max(ax1, bx1)
        inter_top = max(ay1, by1)
        inter_right = min(ax2, bx2)
        inter_bottom = min(ay2, by2)
        inter_width = max(0.0, inter_right - inter_left)
        inter_height = max(0.0, inter_bottom - inter_top)
        inter_area = inter_width * inter_height
        if inter_area <= 0:
            return 0.0
        union = (a.width * a.height) + (b.width * b.height) - inter_area
        if union <= 0:
            return 0.0
        return inter_area / union

    def wait_for_stable_ui(self, seconds: float) -> None:
        wait_budget = max(0.0, seconds)
        if wait_budget == 0:
            return
        if self._driver is None:
            time.sleep(wait_budget)
            return

        deadline = time.monotonic() + wait_budget
        stable_for = min(self.UI_STABLE_FOR_SECONDS, wait_budget)
        last_signature: str | None = None
        stable_since: float | None = None

        while True:
            now = time.monotonic()
            signature = self._ui_stability_signature()
            if signature is not None:
                if signature == last_signature:
                    if stable_since is None:
                        stable_since = now
                    if now - stable_since >= stable_for:
                        return
                else:
                    last_signature = signature
                    stable_since = now

            remaining = deadline - now
            if remaining <= 0:
                return
            time.sleep(min(self.UI_POLL_INTERVAL_SECONDS, remaining))

    def current_focus(self) -> tuple[str, str]:
        if self._driver is not None:
            try:
                package_name = self._driver.current_package
                activity_name = self._driver.current_activity
                if package_name or activity_name:
                    return package_name or "", activity_name or ""
            except Exception:
                pass
        result = self._adb(["shell", "dumpsys", "window", "windows"], check=True)
        for line in result.stdout.splitlines():
            if "mCurrentFocus" in line or "mFocusedApp" in line:
                match = re.search(r"([A-Za-z0-9._]+)/([A-Za-z0-9.$_]+)", line)
                if match:
                    package_name, activity_name = match.groups()
                    return package_name, activity_name
        return "", ""

    def _wm_density(self) -> int | None:
        result = self._adb(["shell", "wm", "density"], check=False)
        for chunk in result.stdout.split():
            if chunk.isdigit():
                return int(chunk)
        return None

    def _window_size(self) -> dict[str, int]:
        if self._driver is not None:
            with suppress(Exception):
                size = self._driver.get_window_size()
                return {"width": int(size["width"]), "height": int(size["height"])}
        result = self._adb(["shell", "wm", "size"], check=False)
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", result.stdout)
        if match:
            width, height = match.groups()
            return {"width": int(width), "height": int(height)}
        return {"width": 1080, "height": 2400}

    def _orientation(self) -> str:
        if self._driver is not None:
            with suppress(Exception):
                return str(self._driver.orientation).lower()
        return "portrait"

    def _uiautomator_dump_xml(self) -> str:
        remote_path = "/sdcard/agent_runner_window_dump.xml"
        self._adb(["shell", "uiautomator", "dump", remote_path], check=False, timeout=30.0)
        result = self._adb(["shell", "cat", remote_path], check=False, timeout=30.0)
        if result.stdout.strip().startswith("<?xml"):
            return result.stdout
        local_dir = ensure_directory(Path(tempfile.gettempdir()) / "agent_runner-secure-dumps")
        local_path = local_dir / f"{self.device_serial.replace(':', '_')}-window_dump.xml"
        pull_result = self._adb(["pull", remote_path, str(local_path)], check=False, timeout=30.0)
        if pull_result.returncode == 0 and local_path.exists():
            xml_source = local_path.read_text(encoding="utf-8", errors="replace")
            if xml_source.strip().startswith("<?xml"):
                return xml_source
        raise RuntimeError("Failed to capture UI hierarchy from secure surface.")

    def _reset_uiautomator2_services(self) -> None:
        for package_name in [
            "io.appium.uiautomator2.server",
            "io.appium.uiautomator2.server.test",
        ]:
            self._adb(["shell", "am", "force-stop", package_name], check=False)

    @staticmethod
    def _is_recoverable_session_error(message: str) -> bool:
        lowered = message.casefold()
        return any(
            token in lowered
            for token in [
                "instrumentation process cannot be initialized",
                "socket hang up",
                "could not proxy command",
            ]
        )

    @staticmethod
    def _is_appium_unavailable_error(message: str) -> bool:
        lowered = message.casefold()
        return any(
            token in lowered
            for token in [
                "failed to establish a new connection",
                "max retries exceeded",
                "connection refused",
                "httpconnectionpool",
            ]
        )

    @staticmethod
    def _is_secure_surface_error(message: str) -> bool:
        lowered = message.casefold()
        return "secure" in lowered and "screenshot" in lowered

    def _ui_stability_signature(self) -> str | None:
        if self._driver is None:
            return None
        try:
            package_name = self._driver.current_package or ""
            activity_name = self._driver.current_activity or ""
            xml_source = self._driver.page_source or ""
        except Exception:
            return None
        digest = hashlib.sha256(xml_source.encode("utf-8")).hexdigest()[:16]
        return f"{package_name}|{activity_name}|{digest}"

    def _adb(
        self,
        args: list[str],
        *,
        check: bool,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [self.adb_path, "-s", self.device_serial, *args]
        effective_timeout = self.ADB_TIMEOUT_SECONDS if timeout is None else timeout
        try:
            return subprocess.run(
                command,
                check=check,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"adb command timed out after {effective_timeout:.1f}s: {' '.join(command)}"
            ) from exc
