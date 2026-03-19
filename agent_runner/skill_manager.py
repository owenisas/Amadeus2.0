from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_runner.models import AppConfig, ScreenState, SkillBundle, VisionDecision
from agent_runner.utils import (
    describe_state_signature,
    dump_json,
    ensure_directory,
    extract_ui_components,
    load_json,
    slugify,
)


DEFAULT_SCREEN_FILE = "screens.json"
DEFAULT_SELECTOR_FILE = "selectors.json"
DEFAULT_STATE_FILE = "state.json"
DEFAULT_MEMORY_FILE = "memory.md"
SCRIPTS_DIR = "scripts"


class SkillManager:
    def __init__(self, skills_root: Path, system_skill_file: Path | None = None) -> None:
        self.skills_root = skills_root
        self.system_skill_file = system_skill_file or (skills_root.parent / "system" / "android_navigation" / "SKILL.md")

    def load_skill(self, app: AppConfig) -> SkillBundle:
        app_dir = ensure_directory(self.skills_root / app.name)
        self._ensure_defaults(app, app_dir)
        return self._bundle_from_dir(app.name, app_dir)

    def load_system_skill(self) -> str:
        skill_path = self.system_skill_file
        ensure_directory(skill_path.parent)
        if not skill_path.exists():
            skill_path.write_text(self._default_system_skill_markdown(), encoding="utf-8")
        return skill_path.read_text(encoding="utf-8")

    def bootstrap_skill(
        self,
        *,
        app_name: str,
        package_name: str,
        default_goal_hint: str = "Explore the app safely and record robust navigation anchors.",
    ) -> SkillBundle:
        app_dir = ensure_directory(self.skills_root / app_name)
        if not (app_dir / "SKILL.md").exists():
            instructions = self._custom_skill_markdown(
                app_name=app_name,
                package_name=package_name,
                default_goal_hint=default_goal_hint,
            )
            (app_dir / "SKILL.md").write_text(instructions, encoding="utf-8")
        for path, payload in [
            (app_dir / DEFAULT_SCREEN_FILE, {"screens": {}}),
            (app_dir / DEFAULT_SELECTOR_FILE, {"selectors": []}),
            (app_dir / DEFAULT_STATE_FILE, {"app": app_name, "package_name": package_name}),
        ]:
            if not path.exists():
                dump_json(path, payload)
        memory_path = app_dir / DEFAULT_MEMORY_FILE
        if not memory_path.exists():
            memory_path.write_text(
                f"# {app_name.title()} memory\n\n- Bootstrapped skill for `{package_name}`.\n",
                encoding="utf-8",
            )
        return self._bundle_from_dir(app_name, app_dir)

    def read_skill_file(self, app_name: str, file_name: str) -> str:
        path = self._skill_file_path(app_name, file_name)
        return path.read_text(encoding="utf-8")

    def write_skill_file(self, app_name: str, file_name: str, content: str) -> Path:
        path = self._skill_file_path(app_name, file_name, create_parent=True)
        path.write_text(content, encoding="utf-8")
        return path

    def update_skill_json(self, app_name: str, file_name: str, payload: dict[str, Any]) -> Path:
        path = self._skill_file_path(app_name, file_name, create_parent=True)
        dump_json(path, payload)
        return path

    # --- Script management ---

    def list_scripts(self, app_name: str) -> list[str]:
        """List available script files for an app skill."""
        scripts_dir = self.skills_root / app_name / SCRIPTS_DIR
        if not scripts_dir.exists():
            return []
        return sorted(f.name for f in scripts_dir.iterdir() if f.suffix == ".json" and f.is_file())

    def read_script(self, app_name: str, script_name: str) -> dict[str, Any]:
        """Read a saved automation script."""
        path = self._script_path(app_name, script_name)
        if not path.exists():
            raise FileNotFoundError(f"Script '{script_name}' not found for app '{app_name}'.")
        return load_json(path, default={})

    def save_script(self, app_name: str, script_name: str, script: dict[str, Any]) -> Path:
        """Save an automation script under the app's scripts/ directory."""
        if not script_name.endswith(".json"):
            script_name = f"{script_name}.json"
        scripts_dir = ensure_directory(self.skills_root / app_name / SCRIPTS_DIR)
        path = scripts_dir / script_name
        dump_json(path, script)
        return path

    def delete_script(self, app_name: str, script_name: str) -> bool:
        """Delete a saved script. Returns True if it existed."""
        path = self._script_path(app_name, script_name)
        if path.exists():
            path.unlink()
            return True
        return False

    def _script_path(self, app_name: str, script_name: str) -> Path:
        if not script_name.endswith(".json"):
            script_name = f"{script_name}.json"
        return self.skills_root / app_name / SCRIPTS_DIR / script_name

    def update_after_observation(
        self,
        bundle: SkillBundle,
        state: ScreenState,
        decision: VisionDecision | None,
    ) -> str:
        signature = describe_state_signature(state)
        screen_id = self._screen_id(signature)
        screens = bundle.screens.setdefault("screens", {})
        selectors = bundle.selectors.setdefault("selectors", [])
        components = state.components or extract_ui_components(
            state.xml_source,
            width=state.device.width,
            height=state.device.height,
        )

        if screen_id not in screens:
            screens[screen_id] = {
                "screen_id": screen_id,
                "package_name": state.package_name,
                "activity_name": state.activity_name,
                "signature": signature,
                "anchors": state.visible_text[:12],
                "clickable_text": state.clickable_text[:12],
                "components": components[:20],
                "fallback_actions": [],
            }
        else:
            screens[screen_id]["components"] = components[:20]

        if decision and decision.target_box and decision.target_label:
            selectors.append(
                {
                    "screen_id": screen_id,
                    "label": decision.target_label,
                    "target_box": decision.target_box.to_dict(),
                    "reason": decision.reason,
                    "activity_name": state.activity_name,
                    "package_name": state.package_name,
                    "anchor_text": state.visible_text[:6],
                }
            )
            selectors[:] = self._dedupe_selectors(selectors)

        selectors.extend(
            self._component_selectors(
                screen_id=screen_id,
                state=state,
                components=components,
            )
        )
        selectors[:] = self._dedupe_selectors(selectors)

        bundle.state.update(
            {
                "last_successful_screen": screen_id,
                "last_screen_signature": signature,
                "last_detected_inputs": [
                    component
                    for component in components
                    if component.get("component_type") in {"text_input", "search_action"}
                ][:8],
            }
        )
        dump_json(bundle.app_dir / DEFAULT_SCREEN_FILE, bundle.screens)
        dump_json(bundle.app_dir / DEFAULT_SELECTOR_FILE, bundle.selectors)
        dump_json(bundle.app_dir / DEFAULT_STATE_FILE, bundle.state)
        self.prune_selectors(bundle)
        return screen_id

    def update_after_transition(
        self,
        bundle: SkillBundle,
        *,
        before_state: ScreenState,
        decision: VisionDecision,
        after_state: ScreenState,
    ) -> None:
        if not self._is_search_transition(decision):
            return
        transition = {
            "from_screen_id": self._screen_id(describe_state_signature(before_state)),
            "to_screen_id": self._screen_id(describe_state_signature(after_state)),
            "action": decision.next_action,
            "input_text": decision.input_text,
            "submit_after_input": decision.submit_after_input,
            "trigger_label": decision.target_label,
            "result_activity": after_state.activity_name,
            "result_package": after_state.package_name,
            "result_anchors": after_state.visible_text[:15],
            "result_clickable_text": after_state.clickable_text[:12],
        }
        transitions = bundle.state.setdefault("search_transitions", [])
        transitions.append(transition)
        bundle.state["search_transitions"] = transitions[-10:]
        bundle.state["last_search_transition"] = transition
        dump_json(bundle.app_dir / DEFAULT_STATE_FILE, bundle.state)

    def update_run_state(
        self,
        bundle: SkillBundle,
        *,
        status: str,
        reason: str,
        last_screen_id: str | None,
        action_history: list[dict[str, Any]],
        failure_count: int,
    ) -> None:
        bundle.state.update(
            {
                "status": status,
                "reason": reason,
                "last_successful_screen": last_screen_id,
                "last_working_action_chain": action_history[-10:],
                "screen_transition_confidence": 1.0 if failure_count == 0 else max(0.1, 1 - (failure_count * 0.2)),
                "failure_count": failure_count,
            }
        )
        dump_json(bundle.app_dir / DEFAULT_STATE_FILE, bundle.state)
        memory_path = bundle.app_dir / DEFAULT_MEMORY_FILE
        new_entry = (
            f"\n- Status: {status}\n- Reason: {reason}\n"
            + (f"- Last screen: {last_screen_id}\n" if last_screen_id else "")
        )
        self._append_memory(memory_path, bundle.memory, new_entry)

    def _ensure_defaults(self, app: AppConfig, app_dir: Path) -> None:
        skill_path = app_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(self._default_skill_markdown(app), encoding="utf-8")
        for path, payload in [
            (app_dir / DEFAULT_SCREEN_FILE, {"screens": {}}),
            (app_dir / DEFAULT_SELECTOR_FILE, {"selectors": []}),
            (app_dir / DEFAULT_STATE_FILE, {"app": app.name}),
        ]:
            if not path.exists():
                dump_json(path, payload)
        memory_path = app_dir / DEFAULT_MEMORY_FILE
        if not memory_path.exists():
            memory_path.write_text(
                f"# {app.name.title()} memory\n\n- Manual login baseline required where applicable.\n",
                encoding="utf-8",
            )

    def _bundle_from_dir(self, app_name: str, app_dir: Path) -> SkillBundle:
        return SkillBundle(
            app_name=app_name,
            app_dir=app_dir,
            instructions=(app_dir / "SKILL.md").read_text(encoding="utf-8"),
            screens=load_json(app_dir / DEFAULT_SCREEN_FILE, default={"screens": {}}),
            selectors=load_json(app_dir / DEFAULT_SELECTOR_FILE, default={"selectors": []}),
            state=load_json(app_dir / DEFAULT_STATE_FILE, default={}),
            memory=(app_dir / DEFAULT_MEMORY_FILE).read_text(encoding="utf-8"),
        )

    def _default_skill_markdown(self, app: AppConfig) -> str:
        blocked = ", ".join(app.high_risk_signatures) or "none"
        return f"""---
name: {app.name}
description: App-specific navigation guidance for the {app.name.title()} Android workflow.
---

# {app.name.title()} skill

## Purpose

- Support low-risk navigation and read-oriented automation for `{app.package_name}`.
- Default goal hint: {app.default_goal_hint}

## Navigation conventions

- Prefer tabs, order/detail pages, and dismissible popups.
- Avoid account mutation flows and irreversible confirmations.
- Use visible text, package/activity, and normalized target boxes together before falling back to blind taps.

## Stable visual anchors

- Preserve the top visible labels for important screens in `screens.json`.
- Reuse selectors only when the current screen signature matches the stored package/activity and anchor text.

## Risk surfaces to avoid

- {blocked}

## Known recipes

- `explore the app`: launch the app, inspect the main screen, scroll once if needed, then stop.
"""

    def _custom_skill_markdown(
        self,
        *,
        app_name: str,
        package_name: str,
        default_goal_hint: str,
    ) -> str:
        title = app_name.replace("-", " ").title()
        return f"""---
name: {app_name}
description: App-specific navigation guidance for the {title} Android workflow.
---

# {title} skill

## Purpose

- Support low-risk Android automation for `{package_name}`.
- Default goal hint: {default_goal_hint}

## Navigation conventions

- Record stable visible text, package/activity pairs, and normalized boxes before reusing a selector.
- Prefer screen summaries, hierarchy components, and known selectors over blind coordinate taps.

## Dynamic components

- Note text inputs, search boxes, and submit buttons in `selectors.json`.
- Persist search-result transitions in `state.json`.

## Risk surfaces to avoid

- Purchases, destructive settings, account mutations, and irreversible confirmation dialogs.
"""

    def _skill_file_path(self, app_name: str, file_name: str, *, create_parent: bool = False) -> Path:
        allowed = {
            "SKILL.md",
            DEFAULT_SCREEN_FILE,
            DEFAULT_SELECTOR_FILE,
            DEFAULT_STATE_FILE,
            DEFAULT_MEMORY_FILE,
        }
        if file_name not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ValueError(f"Unsupported skill file '{file_name}'. Allowed files: {allowed_list}")
        app_dir = self.skills_root / app_name
        if create_parent:
            ensure_directory(app_dir)
        path = app_dir / file_name
        if not path.exists() and not create_parent:
            raise FileNotFoundError(path)
        return path

    def _default_system_skill_markdown(self) -> str:
        return """---
name: android_navigation
description: System-level Android navigation guidance for dialogs, permissions, onboarding surfaces, and safe handoff to the user.
---

# Android navigation skill

## Purpose

- Guide safe navigation outside any single app.
- Handle system dialogs, permission prompts, onboarding overlays, and app-switching surfaces consistently.

## Core rules

- Do not grant, deny, dismiss, or confirm system/app popups without explicit user approval unless the current app skill says the popup is low-risk and safe to continue automatically.
- When a modal dialog, permission prompt, onboarding surface, or account-selection screen appears, stop and ask the user what to do.
- Prefer the least-invasive interpretation of unknown popups.

## Approval gating

- Treat Android permission dialogs, notification prompts, account chooser screens, and feature-onboarding cards as approval-required.
- Summarize the popup using the top visible text and the available action labels.
- If the user approves a specific action, perform only that action and then recapture the screen.

## System navigation

- Use `back` to leave uncertain surfaces before using `home`.
- Avoid destructive system actions, account changes, or settings mutations unless the user asked for them explicitly.

## Automation scripts

- When you identify a repetitive navigation sequence (e.g., search for X, dismiss popup, tap result), save it as a script using the `save_script` tool.
- Scripts are stored per-app under `skills/apps/<app>/scripts/` and can be replayed with `run_script`.
- Before performing a multi-step navigation you have done before, check `list_scripts` to see if a reusable script already exists.
- A script is a JSON object with `name`, `description`, and `steps` (list of action objects).
- Each step has `action` (tap/type/swipe/back/home/wait/launch_app/run_script) and optional fields like `target_label`, `input_text`, `submit_after_input`, `package_name`, `wait_seconds`, `script_name`.
"""

    def _screen_id(self, signature: dict[str, Any]) -> str:
        return slugify(
            f"{signature['package_name']}-{signature['activity_name']}-{signature['text_digest']}"
        )

    def _dedupe_selectors(self, selectors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str, str]] = set()
        deduped: list[dict[str, Any]] = []
        for selector in selectors:
            key = (
                selector.get("screen_id", ""),
                selector.get("label", "").casefold(),
                selector.get("activity_name", ""),
                selector.get("component_type", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(selector)
        return deduped

    def _component_selectors(
        self,
        *,
        screen_id: str,
        state: ScreenState,
        components: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        selectors: list[dict[str, Any]] = []
        for component in components:
            component_type = component.get("component_type", "")
            if component_type not in {"text_input", "search_action"}:
                continue
            target_box = component.get("target_box")
            if not target_box:
                continue
            selectors.append(
                {
                    "screen_id": screen_id,
                    "label": component.get("label") or component_type,
                    "target_box": target_box,
                    "reason": "Observed dynamic component from UI hierarchy.",
                    "activity_name": state.activity_name,
                    "package_name": state.package_name,
                    "anchor_text": state.visible_text[:6],
                    "component_type": component_type,
                    "resource_id": component.get("resource_id", ""),
                    "search_related": component.get("search_related", False),
                }
            )
        return selectors

    def _is_search_transition(self, decision: VisionDecision) -> bool:
        if decision.next_action == "type":
            return True
        label = (decision.target_label or "").casefold()
        return any(token in label for token in ["search", "enter", "go", "submit"])

    MAX_MEMORY_LINES = 80
    MAX_SELECTORS = 200

    def _append_memory(self, memory_path: Path, current_memory: str, new_entry: str) -> None:
        """Append to memory.md and prune to MAX_MEMORY_LINES, keeping the header and most recent entries."""
        full_text = current_memory + new_entry
        lines = full_text.splitlines()
        if len(lines) <= self.MAX_MEMORY_LINES:
            memory_path.write_text(full_text, encoding="utf-8")
            return
        # Keep the first 3 lines (header) and the most recent entries
        header = lines[:3]
        recent = lines[-(self.MAX_MEMORY_LINES - 4) :]
        pruned = header + ["", "<!-- older entries pruned -->"] + recent
        memory_path.write_text("\n".join(pruned) + "\n", encoding="utf-8")

    def prune_selectors(self, bundle: SkillBundle) -> None:
        """Keep selectors under MAX_SELECTORS by dropping the oldest entries."""
        selectors = bundle.selectors.get("selectors", [])
        if len(selectors) <= self.MAX_SELECTORS:
            return
        selectors[:] = selectors[-self.MAX_SELECTORS :]
        dump_json(bundle.app_dir / DEFAULT_SELECTOR_FILE, bundle.selectors)
