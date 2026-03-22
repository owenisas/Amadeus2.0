from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

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
DATA_DIR = "data"
DEFAULT_BACKUP_JSON_FILE = f"{DATA_DIR}/backup.json"
DEFAULT_BACKUP_SUMMARY_FILE = f"{DATA_DIR}/backup.md"
SCRIPTS_DIR = "scripts"
MAX_RECENT_SCREENS = 12
MAX_BACKUP_ITEMS = 25
MAX_BACKUP_THREADS = 20
MAX_THREAD_MESSAGES = 12


class SkillManager:
    def __init__(self, skills_root: Path, system_skill_file: Path | None = None) -> None:
        self.skills_root = skills_root
        self.system_skill_file = system_skill_file or (skills_root.parent / "system" / "android_navigation" / "SKILL.md")
        self._pending_events: list[dict[str, Any]] = []

    def consume_events(self) -> list[dict[str, Any]]:
        events = self._pending_events[:]
        self._pending_events.clear()
        return events

    def load_skill(self, app: AppConfig) -> SkillBundle:
        app_dir = ensure_directory(self.skills_root / app.name)
        self._ensure_defaults(app, app_dir)
        bundle = self._bundle_from_dir(app.name, app_dir)
        facebook_backup = bundle.backup_data.get("facebook_marketplace", {})
        self._queue_event(
            "skill_loaded",
            {
                "app_name": app.name,
                "path": str(app_dir / "SKILL.md"),
                "screens_path": str(app_dir / DEFAULT_SCREEN_FILE),
                "selectors_path": str(app_dir / DEFAULT_SELECTOR_FILE),
                "state_path": str(app_dir / DEFAULT_STATE_FILE),
                "memory_path": str(app_dir / DEFAULT_MEMORY_FILE),
                "backup_json_path": str(app_dir / DEFAULT_BACKUP_JSON_FILE),
                "backup_summary_path": str(app_dir / DEFAULT_BACKUP_SUMMARY_FILE),
                "screen_count": len(bundle.screens.get("screens", {})),
                "selector_count": len(bundle.selectors.get("selectors", [])),
                "backup_thread_count": len(facebook_backup.get("threads", [])),
                "backup_item_count": len(facebook_backup.get("contacted_items", [])),
            },
        )
        return bundle

    def load_system_skill(self) -> str:
        skill_path = self.system_skill_file
        ensure_directory(skill_path.parent)
        if not skill_path.exists():
            skill_path.write_text(self._default_system_skill_markdown(), encoding="utf-8")
        contents = skill_path.read_text(encoding="utf-8")
        self._queue_event(
            "system_skill_loaded",
            {
                "path": str(skill_path),
            },
        )
        return contents

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
            (
                app_dir / DEFAULT_BACKUP_JSON_FILE,
                {
                    "app_name": app_name,
                    "package_name": package_name,
                    "last_updated": None,
                    "recent_screens": [],
                },
            ),
        ]:
            if not path.exists():
                ensure_directory(path.parent)
                dump_json(path, payload)
        memory_path = app_dir / DEFAULT_MEMORY_FILE
        if not memory_path.exists():
            memory_path.write_text(
                f"# {app_name.title()} memory\n\n- Bootstrapped skill for `{package_name}`.\n",
                encoding="utf-8",
            )
        backup_summary_path = app_dir / DEFAULT_BACKUP_SUMMARY_FILE
        if not backup_summary_path.exists():
            ensure_directory(backup_summary_path.parent)
            backup_summary_path.write_text(
                self._render_backup_summary(
                    {
                        "app_name": app_name,
                        "package_name": package_name,
                        "last_updated": None,
                        "recent_screens": [],
                    }
                ),
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
        existing_screen = screen_id in screens
        selector_count_before = len(selectors)
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
        selector_count_after = len(bundle.selectors.get("selectors", []))
        self._queue_event(
            "skill_auto_updated",
            {
                "app_name": bundle.app_name,
                "screen_id": screen_id,
                "new_screen": not existing_screen,
                "selectors_added": max(0, selector_count_after - selector_count_before),
                "component_count": len(components[:20]),
                "files": [
                    str(bundle.app_dir / DEFAULT_SCREEN_FILE),
                    str(bundle.app_dir / DEFAULT_SELECTOR_FILE),
                    str(bundle.app_dir / DEFAULT_STATE_FILE),
                ],
            },
        )
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
        self._queue_event(
            "skill_state_updated",
            {
                "app_name": bundle.app_name,
                "reason": "Recorded search transition in skill state.",
                "files": [str(bundle.app_dir / DEFAULT_STATE_FILE)],
            },
        )

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
        bundle.memory = memory_path.read_text(encoding="utf-8")
        self._queue_event(
            "skill_state_updated",
            {
                "app_name": bundle.app_name,
                "reason": reason,
                "status": status,
                "files": [str(bundle.app_dir / DEFAULT_STATE_FILE)],
            },
        )
        self._queue_event(
            "memory_updated",
            {
                "app_name": bundle.app_name,
                "status": status,
                "reason": reason,
                "path": str(memory_path),
            },
        )

    def update_backup(
        self,
        bundle: SkillBundle,
        state: ScreenState,
    ) -> None:
        backup = bundle.backup_data
        backup.setdefault("app_name", bundle.app_name)
        backup.setdefault("package_name", state.package_name)
        backup.setdefault("recent_screens", [])

        changed_sections: list[str] = []
        if self._update_recent_screens_backup(backup, state):
            changed_sections.append("recent_screens")

        if bundle.app_name == "facebook":
            changed_sections.extend(self._update_facebook_marketplace_backup(backup, state))

        if not changed_sections:
            return

        backup["last_updated"] = self._now_iso()
        backup_json_path = bundle.app_dir / DEFAULT_BACKUP_JSON_FILE
        backup_summary_path = bundle.app_dir / DEFAULT_BACKUP_SUMMARY_FILE
        dump_json(backup_json_path, backup)
        bundle.backup_summary = self._render_backup_summary(backup)
        backup_summary_path.write_text(bundle.backup_summary, encoding="utf-8")
        self._queue_event(
            "backup_updated",
            {
                "app_name": bundle.app_name,
                "path": str(backup_json_path),
                "summary_path": str(backup_summary_path),
                "sections": changed_sections,
                "thread_count": len(backup.get("facebook_marketplace", {}).get("threads", [])),
                "contacted_item_count": len(backup.get("facebook_marketplace", {}).get("contacted_items", [])),
                "inspected_item_count": len(backup.get("facebook_marketplace", {}).get("inspected_items", [])),
            },
        )

    def _queue_event(self, event_type: str, payload: dict[str, Any]) -> None:
        self._pending_events.append({"type": event_type, **payload})

    def _ensure_defaults(self, app: AppConfig, app_dir: Path) -> None:
        skill_path = app_dir / "SKILL.md"
        if not skill_path.exists():
            skill_path.write_text(self._default_skill_markdown(app), encoding="utf-8")
        for path, payload in [
            (app_dir / DEFAULT_SCREEN_FILE, {"screens": {}}),
            (app_dir / DEFAULT_SELECTOR_FILE, {"selectors": []}),
            (app_dir / DEFAULT_STATE_FILE, {"app": app.name}),
            (
                app_dir / DEFAULT_BACKUP_JSON_FILE,
                {
                    "app_name": app.name,
                    "package_name": app.package_name,
                    "last_updated": None,
                    "recent_screens": [],
                },
            ),
        ]:
            if not path.exists():
                ensure_directory(path.parent)
                dump_json(path, payload)
        memory_path = app_dir / DEFAULT_MEMORY_FILE
        if not memory_path.exists():
            memory_path.write_text(
                f"# {app.name.title()} memory\n\n- Manual login baseline required where applicable.\n",
                encoding="utf-8",
            )
        backup_summary_path = app_dir / DEFAULT_BACKUP_SUMMARY_FILE
        if not backup_summary_path.exists():
            ensure_directory(backup_summary_path.parent)
            backup_summary_path.write_text(
                self._render_backup_summary(
                    {
                        "app_name": app.name,
                        "package_name": app.package_name,
                        "last_updated": None,
                        "recent_screens": [],
                    }
                ),
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
            backup_data=load_json(
                app_dir / DEFAULT_BACKUP_JSON_FILE,
                default={"app_name": app_name, "last_updated": None, "recent_screens": []},
            ),
            backup_summary=(app_dir / DEFAULT_BACKUP_SUMMARY_FILE).read_text(encoding="utf-8"),
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
- Persist reusable app history in `data/backup.json` and the operator-facing summary in `data/backup.md`.

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
- Persist conversation, listing, or workflow history in `data/backup.json` so later runs can reuse prior context without rereading the full app surface.

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
            DEFAULT_BACKUP_JSON_FILE,
            DEFAULT_BACKUP_SUMMARY_FILE,
        }
        if file_name not in allowed:
            allowed_list = ", ".join(sorted(allowed))
            raise ValueError(f"Unsupported skill file '{file_name}'. Allowed files: {allowed_list}")
        app_dir = self.skills_root / app_name
        path = app_dir / file_name
        if create_parent:
            ensure_directory(path.parent)
        if not path.exists() and not create_parent:
            raise FileNotFoundError(path)
        return path

    def _update_recent_screens_backup(self, backup: dict[str, Any], state: ScreenState) -> bool:
        recent = backup.setdefault("recent_screens", [])
        signature = describe_state_signature(state)
        screen_id = self._screen_id(signature)
        now = self._now_iso()
        entry = {
            "screen_id": screen_id,
            "package_name": state.package_name,
            "activity_name": state.activity_name,
            "visible_text": state.visible_text[:12],
            "clickable_text": state.clickable_text[:12],
            "last_seen_at": now,
            "seen_count": 1,
        }
        existing = next((item for item in recent if item.get("screen_id") == screen_id), None)
        if existing is not None:
            existing["last_seen_at"] = now
            existing["seen_count"] = int(existing.get("seen_count", 1)) + 1
            existing["visible_text"] = entry["visible_text"]
            existing["clickable_text"] = entry["clickable_text"]
            recent.remove(existing)
            recent.append(existing)
            return True
        recent.append(entry)
        backup["recent_screens"] = recent[-MAX_RECENT_SCREENS:]
        return True

    def _update_facebook_marketplace_backup(self, backup: dict[str, Any], state: ScreenState) -> list[str]:
        if state.package_name != "com.facebook.katana":
            return []
        facebook = backup.setdefault(
            "facebook_marketplace",
            {
                "threads": [],
                "contacted_items": [],
                "inspected_items": [],
            },
        )
        changed_sections: list[str] = []
        thread_snapshot = self._extract_facebook_thread_snapshot(state)
        if thread_snapshot:
            if self._upsert_thread_record(facebook, thread_snapshot):
                changed_sections.append("threads")
            contacted_item = self._thread_to_contact_record(thread_snapshot)
            if self._upsert_contact_record(facebook.setdefault("contacted_items", []), contacted_item):
                changed_sections.append("contacted_items")
        listing_snapshot = self._extract_facebook_listing_snapshot(state)
        if listing_snapshot:
            if self._upsert_record(
                facebook.setdefault("inspected_items", []),
                key_field="item_key",
                payload=listing_snapshot,
                limit=MAX_BACKUP_ITEMS,
            ):
                changed_sections.append("inspected_items")
            if listing_snapshot.get("message_status") == "sent":
                contact_payload = {
                    "thread_key": listing_snapshot["item_key"],
                    "item_title": listing_snapshot.get("item_title"),
                    "seller_name": listing_snapshot.get("seller_name"),
                    "price": listing_snapshot.get("price"),
                    "image_label": listing_snapshot.get("image_label"),
                    "location_hint": listing_snapshot.get("location_hint"),
                    "last_outbound_message": listing_snapshot.get("draft_or_message"),
                    "last_inbound_message": None,
                    "seller_rating": listing_snapshot.get("seller_rating"),
                    "message_status": "sent",
                    "last_updated": self._now_iso(),
                }
                if self._upsert_contact_record(facebook.setdefault("contacted_items", []), contact_payload):
                    changed_sections.append("contacted_items")
        return self._dedupe_strings(changed_sections)

    def _extract_facebook_thread_snapshot(self, state: ScreenState) -> dict[str, Any] | None:
        values = self._xml_text_values(state.xml_source)
        combined = self._dedupe_strings(values + state.visible_text)
        joined = " ".join(combined)
        if "Marketplace listing" not in joined and "Seen by " not in joined and "reviews of " not in joined:
            return None
        header = next(
            (
                text
                for text in combined
                if " · " in text
                and "Marketplace listing" not in text
                and "reviews of " not in text
            ),
            None,
        )
        if not header:
            return None
        seller_name, item_title = [part.strip() for part in header.split(" · ", 1)]
        messages: list[dict[str, str]] = []
        seen_messages: set[tuple[str, str]] = set()
        for text in combined:
            if ", " not in text or text == header:
                continue
            speaker, body = [part.strip() for part in text.split(",", 1)]
            if not speaker or not body:
                continue
            if not self._is_probable_thread_message(speaker, body):
                continue
            if body.casefold().startswith("view seller profile"):
                continue
            key = (speaker.casefold(), body)
            if key in seen_messages:
                continue
            seen_messages.add(key)
            direction = "inbound" if self._speaker_matches_name(speaker, seller_name) else "outbound"
            messages.append({"speaker": speaker, "direction": direction, "text": body})
        if not messages:
            return None
        last_outbound = next((item["text"] for item in reversed(messages) if item["direction"] == "outbound"), None)
        last_inbound = next((item["text"] for item in reversed(messages) if item["direction"] == "inbound"), None)
        seller_rating = next((text.strip() for text in combined if "reviews of " in text), None)
        seen_status = next((text for text in combined if text.startswith("Seen by ")), None)
        location_hint = next(
            (
                text
                for text in reversed([message["text"] for message in messages])
                if any(token in text.casefold() for token in ("pickup", "seattle", "bothell", "washington", "near "))
            ),
            None,
        )
        thread_key = slugify(f"{seller_name}-{item_title}")
        return {
            "thread_key": thread_key,
            "thread_title": header,
            "seller_name": seller_name,
            "item_title": item_title,
            "seller_rating": seller_rating,
            "seen_status": seen_status,
            "location_hint": location_hint,
            "last_outbound_message": last_outbound,
            "last_inbound_message": last_inbound,
            "messages": messages[-MAX_THREAD_MESSAGES:],
            "last_updated": self._now_iso(),
        }

    def _extract_facebook_listing_snapshot(self, state: ScreenState) -> dict[str, Any] | None:
        texts = self._xml_text_values(state.xml_source)
        root = self._xml_root(state.xml_source)
        message_sent = "Message sent to seller" in texts
        title_texts: list[str] = []
        if root is not None:
            for element in root.iter():
                if element.attrib.get("resource-id") == "mp_pdp_title":
                    title_texts = self._collect_element_texts(element)
                    break
        if not title_texts:
            title_texts = texts + state.visible_text
        item_title = next(
            (
                text
                for text in title_texts
                if text
                and not text.startswith("$")
                and text not in {"See more", "See conversation", "Message sent to seller"}
                and "Product Image" not in text
            ),
            None,
        )
        price = next((text for text in title_texts if text.startswith("$")), None)
        image_label = next((text for text in texts if text.startswith("Product Image")), None)
        if not (image_label or price or message_sent):
            return None
        description = next(
            (
                text
                for text in texts
                if len(text) >= 40
                and text != item_title
                and not text.startswith("Product Image")
                and "reviews of " not in text
                and text not in {"Marketplace listing", "See conversation", "Message sent to seller"}
                and "started this chat" not in text.casefold()
            ),
            None,
        )
        seller_rating = next((text.strip() for text in texts if "reviews of " in text), None)
        seller_name = None
        seller_item_header = next(
            (
                text
                for text in texts
                if " · " in text
                and "Marketplace listing" not in text
                and "reviews of " not in text
            ),
            None,
        )
        if seller_item_header:
            seller_name = seller_item_header.split(" · ", 1)[0].strip()
        location_hint = next(
            (
                text
                for text in texts
                if any(token in text.casefold() for token in ("pickup", "shipping", "seattle", "bothell", "washington"))
            ),
            None,
        )
        draft_or_message = next(
            (
                text.split(",", 1)[1].strip()
                for text in texts
                if ", " in text and item_title and item_title in text
            ),
            None,
        )
        snapshot = {
            "item_key": slugify(item_title or f"{state.activity_name}-{price or 'listing'}"),
            "item_title": item_title,
            "price": price,
            "image_label": image_label,
            "description_excerpt": description,
            "seller_name": seller_name,
            "seller_rating": seller_rating,
            "location_hint": location_hint,
            "message_status": "sent" if message_sent else None,
            "draft_or_message": draft_or_message,
            "last_updated": self._now_iso(),
        }
        return snapshot

    def _upsert_thread_record(self, facebook: dict[str, Any], payload: dict[str, Any]) -> bool:
        threads = facebook.setdefault("threads", [])
        existing = next((item for item in threads if item.get("thread_key") == payload.get("thread_key")), None)
        if existing is None:
            threads.insert(0, payload)
            facebook["threads"] = threads[:MAX_BACKUP_THREADS]
            return True
        merged_messages = self._merge_messages(existing.get("messages", []), payload.get("messages", []))
        updated = dict(existing)
        updated.update(payload)
        updated["messages"] = merged_messages[-MAX_THREAD_MESSAGES:]
        if updated == existing:
            return False
        index = threads.index(existing)
        threads[index] = updated
        threads.insert(0, threads.pop(index))
        facebook["threads"] = threads[:MAX_BACKUP_THREADS]
        return True

    def _upsert_record(
        self,
        records: list[dict[str, Any]],
        *,
        key_field: str,
        payload: dict[str, Any],
        limit: int,
    ) -> bool:
        key = payload.get(key_field)
        if not key:
            return False
        existing = next((item for item in records if item.get(key_field) == key), None)
        if existing is None:
            records.insert(0, payload)
            del records[limit:]
            return True
        updated = dict(existing)
        updated.update({name: value for name, value in payload.items() if self._has_meaningful_value(value)})
        if updated == existing:
            return False
        index = records.index(existing)
        records[index] = updated
        records.insert(0, records.pop(index))
        del records[limit:]
        return True

    def _upsert_contact_record(self, records: list[dict[str, Any]], payload: dict[str, Any]) -> bool:
        item_title = str(payload.get("item_title") or "")
        seller_name = str(payload.get("seller_name") or "")
        thread_key = str(payload.get("thread_key") or "")
        existing = next(
            (
                item
                for item in records
                if item.get("thread_key") == thread_key
                or (
                    item_title
                    and str(item.get("item_title") or "") == item_title
                    and (
                        not str(item.get("seller_name") or "")
                        or not seller_name
                        or str(item.get("seller_name") or "") == seller_name
                    )
                )
            ),
            None,
        )
        if existing is None:
            records.insert(0, payload)
            self._dedupe_contact_records(records)
            del records[MAX_BACKUP_ITEMS:]
            return True
        updated = dict(existing)
        updated.update({name: value for name, value in payload.items() if self._has_meaningful_value(value)})
        if thread_key:
            updated["thread_key"] = thread_key
        if updated == existing:
            return False
        index = records.index(existing)
        records[index] = updated
        records.insert(0, records.pop(index))
        self._dedupe_contact_records(records)
        del records[MAX_BACKUP_ITEMS:]
        return True

    def _thread_to_contact_record(self, thread: dict[str, Any]) -> dict[str, Any]:
        inbound = str(thread.get("last_inbound_message") or "")
        message_status = "seller_replied" if inbound else "message_sent"
        if inbound and "available" in inbound.casefold():
            message_status = "seller_confirmed_available"
        return {
            "thread_key": thread.get("thread_key"),
            "item_title": thread.get("item_title"),
            "seller_name": thread.get("seller_name"),
            "seller_rating": thread.get("seller_rating"),
            "location_hint": thread.get("location_hint"),
            "last_outbound_message": thread.get("last_outbound_message"),
            "last_inbound_message": thread.get("last_inbound_message"),
            "seen_status": thread.get("seen_status"),
            "message_status": message_status,
            "last_updated": thread.get("last_updated"),
        }

    def _render_backup_summary(self, backup: dict[str, Any]) -> str:
        title = str(backup.get("app_name") or "App").replace("-", " ").title()
        lines = [f"# {title} backup", ""]
        if backup.get("last_updated"):
            lines.append(f"- Last updated: {backup['last_updated']}")
        if backup.get("package_name"):
            lines.append(f"- Package: `{backup['package_name']}`")
        recent_screens = list(backup.get("recent_screens") or [])[-5:]
        lines.extend(["", "## Recent screens"])
        if not recent_screens:
            lines.append("- No captured screen history yet.")
        for entry in recent_screens:
            visible = ", ".join(list(entry.get("visible_text") or [])[:4])
            lines.append(
                f"- `{entry.get('activity_name')}` x{entry.get('seen_count', 1)}: {visible or 'No visible text'}"
            )
        facebook = backup.get("facebook_marketplace")
        if isinstance(facebook, dict):
            lines.extend(["", "## Contacted items"])
            contacted = list(facebook.get("contacted_items") or [])[:5]
            if not contacted:
                lines.append("- No contacted Marketplace items yet.")
            for item in contacted:
                parts = [
                    item.get("item_title") or "Unknown item",
                    item.get("price") or "price n/a",
                    item.get("seller_name") or "seller n/a",
                    item.get("message_status") or "status n/a",
                ]
                lines.append(f"- {' | '.join(parts)}")
                if item.get("last_inbound_message"):
                    lines.append(f"  Last reply: {item['last_inbound_message']}")
            lines.extend(["", "## Thread summaries"])
            threads = list(facebook.get("threads") or [])[:4]
            if not threads:
                lines.append("- No Marketplace thread summaries yet.")
            for thread in threads:
                lines.append(f"- {thread.get('thread_title') or thread.get('item_title') or 'Unknown thread'}")
                if thread.get("last_outbound_message"):
                    lines.append(f"  You: {thread['last_outbound_message']}")
                if thread.get("last_inbound_message"):
                    lines.append(f"  Seller: {thread['last_inbound_message']}")
            lines.extend(["", "## Inspected items"])
            inspected = list(facebook.get("inspected_items") or [])[:5]
            if not inspected:
                lines.append("- No inspected Marketplace listings yet.")
            for item in inspected:
                summary = [item.get("item_title") or "Unknown item"]
                if item.get("price"):
                    summary.append(item["price"])
                if item.get("location_hint"):
                    summary.append(item["location_hint"])
                lines.append(f"- {' | '.join(summary)}")
                if item.get("description_excerpt"):
                    lines.append(f"  Details: {item['description_excerpt']}")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _xml_root(xml_source: str) -> ET.Element | None:
        if not xml_source.strip():
            return None
        try:
            return ET.fromstring(xml_source)
        except ET.ParseError:
            return None

    def _xml_text_values(self, xml_source: str) -> list[str]:
        root = self._xml_root(xml_source)
        if root is None:
            return []
        values: list[str] = []
        for element in root.iter():
            for attribute in ("text", "content-desc", "hint", "tooltip-text"):
                cleaned = self._clean_text(element.attrib.get(attribute))
                if cleaned:
                    values.append(cleaned)
        return self._dedupe_strings(values)

    def _collect_element_texts(self, element: ET.Element) -> list[str]:
        values: list[str] = []
        for node in element.iter():
            for attribute in ("text", "content-desc", "hint", "tooltip-text"):
                cleaned = self._clean_text(node.attrib.get(attribute))
                if cleaned:
                    values.append(cleaned)
        return self._dedupe_strings(values)

    @staticmethod
    def _clean_text(value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).replace("\u00a0", " ").strip()
        return " ".join(text.split())

    @staticmethod
    def _dedupe_strings(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    @classmethod
    def _merge_messages(cls, existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in list(existing) + list(incoming):
            speaker = str(item.get("speaker") or "")
            text = str(item.get("text") or "")
            if not cls._is_probable_thread_message(speaker, text):
                continue
            key = (speaker.casefold(), text)
            if not speaker or not text or key in seen:
                continue
            seen.add(key)
            merged.append(
                {
                    "speaker": speaker,
                    "direction": item.get("direction"),
                    "text": text,
                }
            )
        return merged

    @staticmethod
    def _speaker_matches_name(speaker: str, name: str | None) -> bool:
        if not speaker or not name:
            return False
        speaker_tokens = speaker.casefold().split()
        name_tokens = name.casefold().split()
        if not speaker_tokens or not name_tokens:
            return False
        return speaker_tokens[0] == name_tokens[0]

    @staticmethod
    def _is_probable_thread_message(speaker: str, body: str) -> bool:
        speaker_prefix = speaker.casefold().split()[0]
        if speaker_prefix in {"open", "view", "back", "like", "save", "share", "comment", "marketplace"}:
            return False
        body_casefold = body.casefold()
        blocked_fragments = (
            "keyboard.",
            "view seller profile",
            "open camera",
            "open photo gallery",
            "open audio recorder",
        )
        return not any(fragment in body_casefold for fragment in blocked_fragments)

    @staticmethod
    def _dedupe_contact_records(records: list[dict[str, Any]]) -> None:
        deduped: list[dict[str, Any]] = []
        seen_titles: set[str] = set()
        for record in records:
            item_title = str(record.get("item_title") or "")
            if not item_title:
                deduped.append(record)
                continue
            normalized_title = item_title.casefold()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            deduped.append(record)
        records[:] = deduped

    @staticmethod
    def _has_meaningful_value(value: Any) -> bool:
        return value is not None and value != "" and value != []

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

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

- Before replaying or saving a reusable script, normalize the app to a clean starting surface. Prefer `reset_app` when the app can resume deep links or stale screens.
- If `reset_app` reveals a transient onboarding, backup, or recovery prompt, use `back` until the main app view is visible before continuing.
- When you identify a repetitive navigation sequence (e.g., search for X, dismiss popup, tap result), save it as a script using the `save_script` tool.
- Scripts are stored per-app under `skills/apps/<app>/scripts/` and can be replayed with `run_script`.
- Before performing a multi-step navigation you have done before, check `list_scripts` to see if a reusable script already exists.
- A script is a JSON object with `name`, `description`, and `steps` (list of action objects).
- Each step has `action` (tap/type/swipe/back/home/wait/launch_app/reset_app/run_script) and optional fields like `target_label`, `input_text`, `submit_after_input`, `package_name`, `wait_seconds`, `script_name`, `only_if_activity_name`, and `only_if_visible_text`.
- Use conditional fields for intermittent prompts so a script can dismiss them only when present and otherwise keep the faster clean-state path.
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
