from __future__ import annotations

import base64
import json
import os
import re
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_runner.models import BoundingBox, ScreenState, SkillBundle, VisionDecision
from agent_runner.utils import describe_state_signature, slugify


class VisionAgent:
    GEMINI_TIMEOUT_SECONDS = 60
    LMSTUDIO_TIMEOUT_SECONDS = 120
    ACTION_ALIASES = {
        "click": "tap",
        "press": "tap",
        "enter_text": "type",
        "input_text": "type",
        "scroll": "swipe",
        "go_back": "back",
    }
    YOLO_PRIMARY_ACTION_TOKENS = (
        "allow",
        "agree",
        "accept",
        "continue",
        "ok",
        "got it",
        "next",
        "turn on",
        "enable",
        "yes",
        "sign in",
        "open",
        "允许",
        "同意",
        "继续",
        "确定",
        "知道了",
        "下一步",
        "完成",
        "打开",
        "转至 gmail",
    )
    YOLO_SECONDARY_ACTION_TOKENS = (
        "not now",
        "later",
        "skip",
        "dismiss",
        "close",
        "cancel",
        "deny",
        "don't allow",
        "don’t allow",
        "以后再说",
        "稍后",
        "跳过",
        "关闭",
        "取消",
        "不允许",
    )

    def __init__(
        self,
        api_key: str | None,
        model: str,
        provider: str = "gemini",
        *,
        lmstudio_base_url: str = "http://127.0.0.1:1234/v1",
        lmstudio_api_key: str | None = None,
    ) -> None:
        self.provider = provider.strip().casefold() or "gemini"
        self.api_key = api_key
        self.model = model
        self.lmstudio_base_url = lmstudio_base_url.rstrip("/")
        self.lmstudio_api_key = lmstudio_api_key
        self.gemini_timeout_seconds = self._resolve_gemini_timeout_seconds()
        self.lmstudio_timeout_seconds = self._resolve_lmstudio_timeout_seconds()
        self.last_decision_meta: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "source": "uninitialized",
        }
        self.last_decision_context: dict[str, Any] = {
            "provider": self.provider,
            "model": self.model,
            "source": "uninitialized",
            "prompt": None,
            "response_text": None,
            "response_payload": None,
        }

    def decide(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        system_instruction: str = "",
        action_history: list[dict[str, Any]],
        available_tools: list[dict[str, Any]] | None = None,
        yolo_mode: bool = False,
    ) -> VisionDecision:
        self.last_decision_context = {
            "provider": self.provider,
            "model": self.model,
            "source": "heuristic_pending",
            "prompt": None,
            "response_text": None,
            "response_payload": None,
        }
        heuristic = self._heuristic_decision(
            goal=goal,
            state=state,
            skill=skill,
            system_instruction=system_instruction,
            action_history=action_history,
            available_tools=available_tools or [],
            yolo_mode=yolo_mode,
        )
        if self._should_bypass_model(goal, state, heuristic, yolo_mode=yolo_mode):
            self._set_decision_meta(source="heuristic_bypass")
            self._set_decision_context(source="heuristic_bypass")
            return heuristic
        if self.provider == "gemini" and not self.api_key:
            self._set_decision_meta(source="heuristic_no_api_key")
            self._set_decision_context(source="heuristic_no_api_key")
            return heuristic
        if self.provider == "lmstudio":
            decision = self._lmstudio_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools or [],
                yolo_mode=yolo_mode,
            )
        else:
            decision = self._gemini_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools or [],
                yolo_mode=yolo_mode,
            )
        decision = self._apply_post_decision_overrides(
            goal=goal,
            state=state,
            skill=skill,
            action_history=action_history,
            decision=decision,
        )
        if yolo_mode:
            return self._apply_yolo_overrides(state=state, skill=skill, decision=decision)
        return decision

    def _gemini_decision(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        system_instruction: str,
        action_history: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        yolo_mode: bool,
    ) -> VisionDecision:
        prompt = self._build_prompt(
            goal=goal,
            state=state,
            skill=skill,
            system_instruction=system_instruction,
            action_history=action_history,
            available_tools=available_tools,
            yolo_mode=yolo_mode,
        )
        image_bytes = Path(state.screenshot_path).read_bytes()
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64.b64encode(image_bytes).decode("utf-8"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1,
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "screen_classification": {"type": "STRING"},
                        "goal_progress": {"type": "STRING"},
                        "next_action": {"type": "STRING"},
                        "target_box": {
                            "type": "OBJECT",
                            "nullable": True,
                            "properties": {
                                "x": {"type": "NUMBER"},
                                "y": {"type": "NUMBER"},
                                "width": {"type": "NUMBER"},
                                "height": {"type": "NUMBER"},
                            },
                        },
                        "confidence": {"type": "NUMBER"},
                        "reason": {"type": "STRING"},
                        "risk_level": {"type": "STRING"},
                        "input_text": {"type": "STRING", "nullable": True},
                        "submit_after_input": {"type": "BOOLEAN"},
                        "target_label": {"type": "STRING", "nullable": True},
                        "tool_name": {"type": "STRING", "nullable": True},
                        "tool_arguments_json": {"type": "STRING", "nullable": True},
                        "requires_user_approval": {"type": "BOOLEAN"},
                    },
                    "required": [
                        "screen_classification",
                        "goal_progress",
                        "next_action",
                        "target_box",
                        "confidence",
                        "reason",
                        "risk_level",
                    ],
                },
            },
        }
        request = urllib.request.Request(
            url=(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.gemini_timeout_seconds) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = f"Gemini request failed ({exc.code}); heuristic fallback used. {detail[:180]}"
            self._set_decision_meta(source="gemini_http_fallback", detail=detail[:180], status_code=exc.code)
            self._set_decision_context(source="gemini_http_fallback", prompt=prompt, response_text=detail[:500])
            return fallback
        except (TimeoutError, socket.timeout) as exc:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = f"Gemini request timed out; heuristic fallback used. {exc}"
            self._set_decision_meta(source="gemini_timeout_fallback", detail=str(exc))
            self._set_decision_context(source="gemini_timeout_fallback", prompt=prompt, response_text=str(exc))
            return fallback
        except urllib.error.URLError as exc:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = f"Gemini request failed; heuristic fallback used. {exc.reason}"
            self._set_decision_meta(source="gemini_network_fallback", detail=str(exc.reason))
            self._set_decision_context(source="gemini_network_fallback", prompt=prompt, response_text=str(exc.reason))
            return fallback

        text = self._extract_text(raw)
        try:
            decision_payload = json.loads(text)
        except json.JSONDecodeError:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = "Gemini returned non-JSON content; heuristic fallback used."
            self._set_decision_meta(source="gemini_non_json_fallback", detail=text[:500])
            self._set_decision_context(source="gemini_non_json_fallback", prompt=prompt, response_text=text, response_payload=raw)
            return fallback
        self._set_decision_meta(source="gemini_model")
        self._set_decision_context(source="gemini_model", prompt=prompt, response_text=text, response_payload=raw)
        return self._coerce_decision(decision_payload, state=state, skill=skill)

    def _lmstudio_decision(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        system_instruction: str,
        action_history: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        yolo_mode: bool,
    ) -> VisionDecision:
        prompt = self._build_prompt(
            goal=goal,
            state=state,
            skill=skill,
            system_instruction=system_instruction,
            action_history=action_history,
            available_tools=available_tools,
            yolo_mode=yolo_mode,
        )
        headers = {"Content-Type": "application/json"}
        if self.lmstudio_api_key:
            headers["Authorization"] = f"Bearer {self.lmstudio_api_key}"
        raw = None
        last_http_error: tuple[int, str] | None = None
        try:
            for payload in self._lmstudio_request_payloads(prompt=prompt, state=state):
                request = urllib.request.Request(
                    url=f"{self.lmstudio_base_url}/chat/completions",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(request, timeout=self.lmstudio_timeout_seconds) as response:
                        raw = self._read_lmstudio_response(response)
                        break
                except urllib.error.HTTPError as exc:
                    detail = exc.read().decode("utf-8", errors="replace")
                    last_http_error = (exc.code, detail)
                    continue
            if raw is None and last_http_error is not None:
                code, detail = last_http_error
                fallback = self._heuristic_decision(
                    goal=goal,
                    state=state,
                    skill=skill,
                    system_instruction=system_instruction,
                    action_history=action_history,
                    available_tools=available_tools,
                    yolo_mode=yolo_mode,
                )
                fallback.reason = f"LM Studio request failed ({code}); heuristic fallback used. {detail[:180]}"
                self._set_decision_meta(source="lmstudio_http_fallback", detail=detail[:180], status_code=code)
                self._set_decision_context(source="lmstudio_http_fallback", prompt=prompt, response_text=detail[:500])
                return fallback
        except (TimeoutError, socket.timeout) as exc:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = f"LM Studio request timed out; heuristic fallback used. {exc}"
            self._set_decision_meta(source="lmstudio_timeout_fallback", detail=str(exc))
            self._set_decision_context(source="lmstudio_timeout_fallback", prompt=prompt, response_text=str(exc))
            return fallback
        except urllib.error.URLError as exc:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = f"LM Studio request failed; heuristic fallback used. {exc.reason}"
            self._set_decision_meta(source="lmstudio_network_fallback", detail=str(exc.reason))
            self._set_decision_context(source="lmstudio_network_fallback", prompt=prompt, response_text=str(exc.reason))
            return fallback

        text = self._extract_lmstudio_text(raw)
        reasoning_text = self._extract_lmstudio_reasoning_text(raw)
        if not text.strip() and reasoning_text.strip():
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = "LM Studio returned reasoning-only content without a final action; heuristic fallback used."
            self._set_decision_meta(
                source="lmstudio_reasoning_only_fallback",
                detail=reasoning_text[:500],
            )
            self._set_decision_context(
                source="lmstudio_reasoning_only_fallback",
                prompt=prompt,
                response_text=reasoning_text,
                response_payload=raw,
            )
            return fallback
        try:
            decision_payload = json.loads(self._extract_json_object(text))
        except json.JSONDecodeError:
            fallback = self._heuristic_decision(
                goal=goal,
                state=state,
                skill=skill,
                system_instruction=system_instruction,
                action_history=action_history,
                available_tools=available_tools,
                yolo_mode=yolo_mode,
            )
            fallback.reason = "LM Studio returned non-JSON content; heuristic fallback used."
            self._set_decision_meta(source="lmstudio_non_json_fallback", detail=text[:500])
            self._set_decision_context(source="lmstudio_non_json_fallback", prompt=prompt, response_text=text, response_payload=raw)
            return fallback
        self._set_decision_meta(source="lmstudio_model")
        self._set_decision_context(source="lmstudio_model", prompt=prompt, response_text=text, response_payload=raw)
        return self._coerce_decision(decision_payload, state=state, skill=skill)

    def _set_decision_meta(self, *, source: str, **extra: Any) -> None:
        self.last_decision_meta = {
            "provider": self.provider,
            "model": self.model,
            "source": source,
            **extra,
        }

    def _set_decision_context(
        self,
        *,
        source: str,
        prompt: str | None = None,
        response_text: str | None = None,
        response_payload: dict[str, Any] | None = None,
    ) -> None:
        self.last_decision_context = {
            "provider": self.provider,
            "model": self.model,
            "source": source,
            "prompt": prompt,
            "response_text": response_text,
            "response_payload": response_payload,
        }

    def _lmstudio_request_payloads(self, *, prompt: str, state: ScreenState) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        screenshot_path = Path(state.screenshot_path)
        if screenshot_path.exists():
            image_data_url = "data:image/png;base64," + base64.b64encode(screenshot_path.read_bytes()).decode("utf-8")
            payloads.append(
                {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_data_url}},
                            ],
                        }
                    ],
                    "temperature": 0.1,
                    "stream": True,
                    "response_format": {"type": "text"},
                }
            )
        text_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": True,
            "response_format": {"type": "text"},
        }
        bare_text_payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "stream": True,
        }
        payloads.extend([text_payload, bare_text_payload])
        return payloads

    def _heuristic_decision(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        system_instruction: str,
        action_history: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        yolo_mode: bool,
    ) -> VisionDecision:
        text = " ".join(state.visible_text[:60]).casefold()
        clickable = state.clickable_text
        components = state.components
        tool_names = {tool.get("name", "") for tool in available_tools}

        popup_decision = self._approval_required_popup_decision(state, skill, yolo_mode=yolo_mode)
        if popup_decision is not None:
            return popup_decision

        lowered_goal = goal.casefold()
        if "screenshot" in lowered_goal and "capture_state" in tool_names:
            return VisionDecision.tool(
                tool_name="capture_state",
                tool_arguments={},
                reason="Capture a fresh screenshot and UI summary before proceeding.",
                confidence=0.9,
            )
        if any(token in lowered_goal for token in ["read skill", "show skill", "open skill"]) and "read_skill" in tool_names:
            return VisionDecision.tool(
                tool_name="read_skill",
                tool_arguments={"file_name": "SKILL.md"},
                reason="Read the current app skill instructions.",
                confidence=0.88,
            )

        if "password" in text or "verification" in text or (not yolo_mode and "sign in" in text):
            return VisionDecision.stop("Manual login required before automation can proceed.")
        if self._manual_verification_or_restriction_visible(state):
            return VisionDecision.stop("Manual account verification or restriction handling is required before automation can proceed.")

        if "latest order" in goal.casefold() or "delivery" in goal.casefold():
            for label in clickable:
                lowered = label.casefold()
                if "orders" in lowered or "your orders" in lowered:
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label=label,
                        screen_classification="orders_entry",
                        goal_progress="navigating",
                        confidence=0.62,
                        reason="Heuristic found an orders entry point.",
                        risk_level="low",
                    )
                if "track package" in lowered or "track" in lowered:
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label=label,
                        screen_classification="order_detail",
                        goal_progress="nearly_complete",
                        confidence=0.57,
                        reason="Heuristic found a tracking affordance.",
                        risk_level="low",
                    )
            if any(token in text for token in ["delivered", "arriving", "shipped", "out for delivery"]):
                return VisionDecision.stop("Order status text is already visible on screen.")

        if state.package_name == "com.android.settings":
            if (
                "subsettings" in state.activity_name.casefold()
                and any(token in text for token in ["network", "internet", "网络", "互联网"])
            ):
                return VisionDecision.stop("Requested network settings page is already visible.")
            for label in clickable:
                lowered = label.casefold()
                if (
                    "network" in lowered
                    or "internet" in lowered
                    or "网络" in label
                    or "互联网" in label
                ):
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label=label,
                        screen_classification="settings_root",
                        goal_progress="navigating",
                        confidence=0.55,
                        reason="Heuristic found a network settings entry.",
                        risk_level="low",
                    )
            return VisionDecision.stop("Settings screen is open and no stronger heuristic was found.")

        if state.package_name == "com.google.android.deskclock":
            if any(token in text for token in ["alarm", "clock", "timer", "stopwatch", "闹钟", "时钟", "计时器", "秒表"]):
                return VisionDecision.stop("Clock app is visible.")
            return VisionDecision(
                screen_classification="clock_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="Clock app is open but the visible labels are still stabilizing.",
                risk_level="low",
            )

        if state.package_name == "com.android.chrome":
            if state.visible_text or state.clickable_text:
                return VisionDecision.stop("Chrome is visible.")
            return VisionDecision(
                screen_classification="chrome_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="Chrome is open but the page is still stabilizing.",
                risk_level="low",
            )

        if state.package_name == "com.google.android.youtube":
            search_goal = self._extract_search_query(goal)
            subscribe_requested = any(
                token in goal.casefold() for token in ["subscribe", "订阅"]
            )
            if any(token in text for token in ["password", "verification"]) or (
                not yolo_mode and any(token in text for token in ["sign in", "choose an account"])
            ):
                return VisionDecision.stop("Manual login required before YouTube automation can proceed.")
            # Subscribe button requires user approval
            if subscribe_requested:
                for label in clickable:
                    lowered = label.casefold()
                    if "subscribe" in lowered or "订阅" in lowered:
                        return VisionDecision.stop(
                            f"User approval required to subscribe. Available action: {label}.",
                            goal_progress="awaiting_user_approval",
                            requires_user_approval=True,
                        )
            # Search flow
            if search_goal:
                search_input = self._find_component(components, component_type="text_input", search_related=True)
                search_action = self._find_component(components, component_type="search_action", search_related=True)
                if search_input and search_input.get("focused"):
                    return VisionDecision(
                        screen_classification="youtube_search_input",
                        goal_progress="typing_query",
                        next_action="type",
                        target_box=BoundingBox.from_dict(search_input.get("target_box")),
                        confidence=0.8,
                        reason="Type the YouTube search query and submit.",
                        risk_level="low",
                        input_text=search_goal,
                        submit_after_input=True,
                        target_label=search_input.get("label") or "search",
                    )
                if search_input:
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(search_input.get("target_box")),
                        screen_classification="youtube_home",
                        goal_progress="focusing_search",
                        confidence=0.72,
                        reason="Focus the YouTube search field.",
                        risk_level="low",
                        target_label=search_input.get("label") or "search",
                    )
                if search_action:
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(search_action.get("target_box")),
                        screen_classification="youtube_home",
                        goal_progress="opening_search",
                        confidence=0.66,
                        reason="Open the YouTube search UI.",
                        risk_level="low",
                        target_label=search_action.get("label") or "search",
                    )
            # Already showing video content or results
            if any(token in text for token in ["subscribe", "views", "subscribers", "播放", "订阅"]):
                if not any(item.get("action") == "swipe" for item in action_history[-2:]):
                    return VisionDecision(
                        screen_classification="youtube_content",
                        goal_progress="browsing",
                        next_action="swipe",
                        target_box=None,
                        confidence=0.6,
                        reason="Scroll once to inspect more YouTube content.",
                        risk_level="low",
                    )
                return VisionDecision.stop("YouTube content is visible and has been scrolled read-only.")
            if state.visible_text or state.clickable_text:
                return VisionDecision.stop("YouTube is visible.")
            return VisionDecision(
                screen_classification="youtube_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="YouTube is open but the page is still stabilizing.",
                risk_level="low",
            )

        if state.package_name == "com.google.android.gm":
            if any(token in text for token in ["inbox", "primary", "social", "promotions", "更新", "收件箱", "主要", "社交", "推广"]):
                if not any(item.get("action") == "swipe" for item in action_history[-2:]):
                    return VisionDecision(
                        screen_classification="gmail_inbox",
                        goal_progress="browsing",
                        next_action="swipe",
                        target_box=None,
                        confidence=0.66,
                        reason="Scroll the Gmail inbox once to inspect more messages.",
                        risk_level="low",
                    )
                return VisionDecision.stop("Gmail inbox is visible and has been inspected read-only.")
            if any(token in text for token in ["compose", "draft", "reply", "forward", "撰写", "回复", "转发"]):
                return VisionDecision.stop("Gmail is on a compose or reply surface; stopping to avoid editing email.")
            if state.visible_text or state.clickable_text or components:
                return VisionDecision.stop("Gmail is visible.")
            return VisionDecision(
                screen_classification="gmail_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="Gmail is open but the inbox has not stabilized yet.",
                risk_level="low",
            )

        if state.package_name == "com.facebook.katana":
            messaging_goal = self._facebook_goal_allows_marketplace_messaging(goal)
            read_only_message_goal = self._facebook_goal_requests_read_only_message_check(goal)
            explicit_reply_goal = self._facebook_goal_targets_thread_replies(goal)
            listing_message_goal = (
                self._facebook_goal_targets_listing_message(goal)
                and not read_only_message_goal
                and not explicit_reply_goal
            )
            search_goal = self._facebook_goal_targets_search(goal)
            value_scan_goal = self._facebook_goal_targets_value_scan(goal)
            clean_start_goal = self._goal_requests_clean_start(goal)
            heuristic_reply_mode = self._facebook_should_check_inbox(
                goal=goal,
                skill=skill,
                action_history=action_history,
            )
            workflow = self._facebook_workflow_state(skill)
            if explicit_reply_goal or read_only_message_goal:
                facebook_mode = "reply"
            else:
                facebook_mode = str(workflow.get("mode") or ("reply" if heuristic_reply_mode else "hunt"))
            reply_text = self._extract_message_text(goal)
            if not reply_text and listing_message_goal:
                reply_text = self._facebook_skill_guided_message(goal=goal, state=state, skill=skill) or self._facebook_default_marketplace_message(state, goal=goal)
            send_requested = self._facebook_send_requested(goal) and not read_only_message_goal
            message_input = self._find_facebook_message_input(components)
            send_button = self._find_facebook_send_button(components)
            should_check_replies = explicit_reply_goal or read_only_message_goal or heuristic_reply_mode
            if facebook_mode != "reply" and not explicit_reply_goal and not read_only_message_goal:
                should_check_replies = False
            marketplace_start_ok = (
                self._facebook_home_shell_visible(state)
                or self._facebook_home_feed_visible(state)
                or self._facebook_marketplace_feed_visible(state)
                or self._facebook_marketplace_search_visible(state)
                or self._facebook_marketplace_account_visible(state)
                or self._facebook_backup_prompt_visible(state)
                or self._facebook_message_recovery_prompt_visible(state)
                or self._facebook_thread_settings_visible(state)
            )
            if search_goal and self._facebook_listing_detail_visible(state) and (not clean_start_goal or bool(action_history)):
                marketplace_start_ok = True
            if value_scan_goal and self._facebook_listing_detail_visible(state) and action_history:
                marketplace_start_ok = True
            if listing_message_goal and (not clean_start_goal or bool(action_history)) and (
                self._facebook_listing_detail_visible(state)
                or (message_input is not None and send_button is not None and not self._facebook_message_thread_visible(state))
            ):
                marketplace_start_ok = True
            if (
                (value_scan_goal or search_goal or listing_message_goal or clean_start_goal)
                and not any(item.get("tool_name") == "reset_app" or item.get("action") == "reset_app" for item in action_history[-3:])
                and not marketplace_start_ok
            ):
                return VisionDecision.tool(
                    tool_name="reset_app",
                    tool_arguments={"package_name": state.package_name},
                    screen_classification="facebook_recovering",
                    goal_progress="recovering",
                    confidence=0.95,
                    reason="Reset Facebook and start again from the Marketplace entry surface instead of resuming a stale Marketplace screen.",
                    target_label=state.package_name,
                )
            if self._facebook_message_recovery_prompt_visible(state):
                if yolo_mode:
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="YES",
                        screen_classification="facebook_message_recovery_prompt",
                        goal_progress="recovering_messages",
                        confidence=0.9,
                        reason="YOLO mode auto-continues through the Marketplace message recovery prompt.",
                        risk_level="low",
                    )
                return VisionDecision.stop(
                    "Facebook Marketplace messaging recovery prompt is visible and needs approval outside YOLO mode.",
                    goal_progress="awaiting_user_approval",
                    requires_user_approval=True,
                )
            if self._facebook_thread_settings_visible(state):
                return VisionDecision(
                    screen_classification="facebook_thread_settings",
                    goal_progress="recovering_to_thread",
                    next_action="back",
                    target_box=None,
                    confidence=0.9,
                    reason="Back out of Facebook thread settings and return to the conversation or inbox flow.",
                    risk_level="low",
                )
            if facebook_mode == "reply":
                return self._facebook_reply_mode_decision(
                    goal=goal,
                    state=state,
                    skill=skill,
                    action_history=action_history,
                    workflow=workflow,
                    message_input=message_input,
                    send_button=send_button,
                    send_requested=not read_only_message_goal,
                )
            if value_scan_goal or search_goal or clean_start_goal or listing_message_goal:
                if self._facebook_marketplace_help_visible(state):
                    return VisionDecision(
                        screen_classification="facebook_marketplace_help",
                        goal_progress="recovering_to_marketplace",
                        next_action="back",
                        target_box=None,
                        confidence=0.93,
                        reason="Back out of the Marketplace help page and continue the Marketplace workflow.",
                        risk_level="low",
                    )
                if self._facebook_message_inbox_visible(state):
                    return VisionDecision(
                        screen_classification="facebook_message_inbox",
                        goal_progress="recovering_to_marketplace",
                        next_action="back",
                        target_box=None,
                        confidence=0.82,
                        reason="Return to Marketplace instead of stopping in the generic Facebook inbox during an active Marketplace workflow.",
                        risk_level="low",
                    )
                if self._facebook_marketplace_inbox_visible(state):
                    return VisionDecision(
                        screen_classification="facebook_marketplace_inbox",
                        goal_progress="recovering_to_marketplace",
                        next_action="back",
                        target_box=None,
                        confidence=0.83,
                        reason="Return to the Marketplace feed instead of stopping in the Marketplace inbox during an active scan.",
                        risk_level="low",
                    )
                if (value_scan_goal or search_goal or clean_start_goal or listing_message_goal) and self._facebook_message_thread_visible(state):
                    return VisionDecision(
                        screen_classification="facebook_message_thread",
                        goal_progress="recovering_to_marketplace",
                        next_action="back",
                        target_box=None,
                        confidence=0.81,
                        reason="Back out of the Marketplace message thread and continue the broader Marketplace workflow.",
                        risk_level="low",
                    )
            if messaging_goal:
                if self._facebook_marketplace_help_visible(state):
                    return VisionDecision(
                        screen_classification="facebook_marketplace_help",
                        goal_progress="recovering_to_inbox",
                        next_action="back",
                        target_box=None,
                        confidence=0.93,
                        reason="Back out of the Marketplace help page to return to the message inbox and continue checking seller replies.",
                        risk_level="low",
                    )
                if (
                    self._facebook_marketplace_feed_visible(state)
                    or self._facebook_marketplace_search_visible(state)
                ) and not listing_message_goal:
                    account_entry = self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="Tap to view your Marketplace account",
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="opening_marketplace_account",
                        confidence=0.84,
                        reason="Open the Marketplace account entry to reach seller threads and inbox surfaces.",
                        risk_level="low",
                    )
                    if account_entry.next_action == "tap":
                        return account_entry
                messages_entry = self._find_facebook_marketplace_messages_entry(components)
                if messages_entry and not (
                    self._facebook_marketplace_inbox_visible(state)
                    or self._facebook_message_thread_visible(state)
                ):
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(messages_entry.get("target_box")),
                        screen_classification="facebook_marketplace_account",
                        goal_progress="opening_messages",
                        confidence=0.86,
                        reason="Open the Marketplace messages row from the Marketplace account page.",
                        risk_level="low",
                        target_label=messages_entry.get("label") or "messages",
                    )
                if listing_message_goal and self._facebook_listing_detail_visible(state):
                    description_expander = self._find_facebook_listing_description_expander(components)
                    if description_expander and not self._recent_target_label_contains(action_history, "see more") and not self._recent_target_label_contains(action_history, "see details"):
                        return self._tap_decision(
                            target_box=BoundingBox.from_dict(description_expander.get("target_box")),
                            screen_classification="facebook_listing_detail",
                            goal_progress="inspecting_listing",
                            confidence=0.89,
                            reason="Expand the listing details before drafting a seller message so specs and condition can be read first.",
                            risk_level="low",
                            target_label=description_expander.get("label") or "See details",
                        )
                    if self._facebook_should_scroll_listing_details(state, action_history):
                        return VisionDecision(
                            screen_classification="facebook_listing_detail",
                            goal_progress="inspecting_listing",
                            next_action="swipe",
                            target_box=self._facebook_detail_scroll_region(),
                            confidence=0.88,
                            reason="Scroll slightly within the listing detail before drafting a seller message so lower specs and condition notes are visible.",
                            risk_level="low",
                        )
                if message_input and reply_text and not any(item.get("action") == "type" for item in action_history[-2:]):
                    return VisionDecision(
                        screen_classification="facebook_message_composer",
                        goal_progress="drafting_reply",
                        next_action="type",
                        target_box=BoundingBox.from_dict(message_input.get("target_box")),
                        confidence=0.86,
                        reason=(
                            "Replace the default Marketplace message with a custom opener tailored to the current listing."
                            if listing_message_goal and not self._extract_message_text(goal)
                            else "Type the requested Facebook message into the current reply field."
                        ),
                        risk_level="low",
                        input_text=reply_text,
                        submit_after_input=False,
                        target_label=message_input.get("label") or "message input",
                    )
                if send_requested and send_button and any(item.get("action") == "type" for item in action_history[-2:]):
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(send_button.get("target_box")),
                        screen_classification="facebook_message_composer",
                        goal_progress="sending_reply",
                        confidence=0.88,
                        reason="Send the explicitly requested Facebook reply.",
                        risk_level="low",
                        target_label=send_button.get("label") or "Send",
                    )
                if self._facebook_message_inbox_visible(state):
                    thread_entry = self._find_facebook_inbox_thread_entry(components, skill)
                    if thread_entry and not self._recent_target_label_contains(
                        action_history,
                        str(thread_entry.get("label") or ""),
                    ):
                        return self._tap_decision(
                            target_box=BoundingBox.from_dict(thread_entry.get("target_box")),
                            screen_classification="facebook_message_inbox",
                            goal_progress="opening_thread",
                            confidence=0.85,
                            reason="Open the most relevant Marketplace message thread from the inbox using the saved backup context.",
                            risk_level="low",
                            target_label=thread_entry.get("label") or "message thread",
                        )
                    if listing_message_goal and send_requested:
                        return VisionDecision(
                            screen_classification="facebook_message_inbox",
                            goal_progress="recovering_to_marketplace",
                            next_action="back",
                            target_box=None,
                            confidence=0.8,
                            reason="Back out of the generic Facebook inbox and return to Marketplace listing flow.",
                            risk_level="low",
                        )
                    if value_scan_goal or search_goal or (listing_message_goal and not read_only_message_goal) or clean_start_goal:
                        return VisionDecision(
                            screen_classification="facebook_message_inbox",
                            goal_progress="recovering_to_marketplace",
                            next_action="back",
                            target_box=None,
                            confidence=0.82,
                            reason="Return to Marketplace instead of stopping in the generic Facebook inbox during an active Marketplace workflow.",
                            risk_level="low",
                        )
                if self._facebook_marketplace_inbox_visible(state):
                    thread_entry = self._find_facebook_marketplace_thread_entry(components, skill)
                    if thread_entry and not self._recent_target_label_contains(
                        action_history,
                        str(thread_entry.get("label") or ""),
                    ):
                        return self._tap_decision(
                            target_box=BoundingBox.from_dict(thread_entry.get("target_box")),
                            screen_classification="facebook_marketplace_inbox",
                            goal_progress="opening_thread",
                            confidence=0.9,
                            reason="Open the Marketplace thread that best matches the saved backup and latest seller reply.",
                            risk_level="low",
                            target_label=thread_entry.get("label") or "marketplace thread",
                        )
                    if value_scan_goal or search_goal or clean_start_goal:
                        return VisionDecision(
                            screen_classification="facebook_marketplace_inbox",
                            goal_progress="recovering_to_marketplace",
                            next_action="back",
                            target_box=None,
                            confidence=0.83,
                            reason="Return to the Marketplace feed instead of stopping in the Marketplace inbox during an active scan.",
                            risk_level="low",
                        )
                    latest_reply = self._facebook_latest_known_reply(skill)
                    if latest_reply:
                        return VisionDecision.stop(
                            f"Facebook Marketplace inbox is visible. Latest known seller reply: {latest_reply}"
                        )
                    return VisionDecision.stop("Facebook Marketplace inbox is visible for read-only inspection.")
                if self._facebook_listing_detail_visible(state) and listing_message_goal:
                    seller_button = self._find_facebook_seller_contact_button(components)
                    if seller_button and not any(item.get("action") == "tap" for item in action_history[-2:]):
                        return self._tap_decision(
                            target_box=BoundingBox.from_dict(seller_button.get("target_box")),
                            screen_classification="facebook_listing_detail",
                            goal_progress="opening_seller_chat",
                            confidence=0.87,
                            reason="Open the Marketplace seller composer from the current listing detail.",
                            risk_level="low",
                            target_label=seller_button.get("label") or "Message seller",
                        )
                if self._facebook_home_feed_visible(state):
                    if should_check_replies:
                        if self._facebook_fast_function_exists(skill, "open_messages_from_home"):
                            return VisionDecision.tool(
                                tool_name="run_fast_function",
                                tool_arguments={
                                    "app_name": skill.app_name,
                                    "function_name": "open_messages_from_home",
                                    "arguments": {},
                                },
                                screen_classification="facebook_home_feed",
                                goal_progress="checking_replies",
                                confidence=0.9,
                                reason="Use the fast function to open Facebook messages from the home feed before checking Marketplace replies.",
                                target_label="open_messages_from_home",
                            )
                        return self._tap_decision_for_label(
                            state=state,
                            skill=skill,
                            label="Messaging",
                            screen_classification="facebook_home_feed",
                            goal_progress="checking_replies",
                            confidence=0.87,
                            reason="Check Marketplace-related replies after recent seller outreach before scanning more listings.",
                            risk_level="low",
                        )
                    if value_scan_goal or search_goal or clean_start_goal or listing_message_goal:
                        if self._facebook_fast_function_exists(skill, "open_marketplace_feed"):
                            return VisionDecision.tool(
                                tool_name="run_fast_function",
                                tool_arguments={
                                    "app_name": skill.app_name,
                                    "function_name": "open_marketplace_feed",
                                    "arguments": {},
                                },
                                screen_classification="facebook_home_feed",
                                goal_progress="navigating_to_marketplace",
                                confidence=0.9,
                                reason="Use the fast function to normalize back into the Marketplace feed from the Facebook home shell.",
                                target_label="open_marketplace_feed",
                            )
                        labels = [item.casefold() for item in (state.visible_text[:60] + state.clickable_text[:40])]
                        labels.extend(
                            str(component.get("label", "")).casefold()
                            for component in state.components[:60]
                            if component.get("label")
                        )
                        if not any("marketplace, tab 4 of 6" in item for item in labels):
                            return self._tap_decision_for_label(
                                state=state,
                                skill=skill,
                                label="Menu",
                                screen_classification="facebook_home_feed",
                                goal_progress="opening_menu_for_marketplace",
                                confidence=0.83,
                                reason="This home-feed variant does not expose the Marketplace tab directly, so open Menu and continue into Marketplace from there.",
                                risk_level="low",
                            )
                        return self._tap_decision_for_label(
                            state=state,
                            skill=skill,
                            label="Marketplace, tab 4 of 6",
                            screen_classification="facebook_home_feed",
                            goal_progress="navigating_to_marketplace",
                            confidence=0.86,
                            reason="Marketplace workflows should enter Marketplace first before opening any inbox or thread.",
                            risk_level="low",
                        )
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="Messaging",
                        screen_classification="facebook_home_feed",
                        goal_progress="opening_messages",
                        confidence=0.87,
                        reason="Open Facebook messages from the home feed.",
                        risk_level="low",
                    )
                if self._facebook_message_thread_visible(state):
                    if reply_text and message_input:
                        if self._facebook_fast_function_exists(skill, "send_thread_reply"):
                            return VisionDecision.tool(
                                tool_name="run_fast_function",
                                tool_arguments={
                                    "app_name": skill.app_name,
                                    "function_name": "send_thread_reply",
                                    "arguments": {"message": reply_text},
                                },
                                screen_classification="facebook_message_thread",
                                goal_progress="sending_reply",
                                confidence=0.9,
                                reason="Use the fast function to send the reply in the open Marketplace thread with verification.",
                                target_label="send_thread_reply",
                            )
                        return VisionDecision(
                            screen_classification="facebook_message_thread",
                            goal_progress="drafting_reply",
                            next_action="type",
                            target_box=BoundingBox.from_dict(message_input.get("target_box")),
                            confidence=0.84,
                            reason="Type the requested reply into the open Facebook message thread.",
                            risk_level="low",
                            input_text=reply_text,
                            submit_after_input=False,
                            target_label=message_input.get("label") or "message input",
                        )
                    latest_reply = self._facebook_latest_known_reply(skill)
                    if latest_reply:
                        return VisionDecision.stop(
                            f"Facebook message thread is visible for reading or replying. Latest known seller reply: {latest_reply}"
                        )
                    return VisionDecision.stop("Facebook message thread is visible for reading or replying.")
                if self._facebook_message_inbox_visible(state):
                    if value_scan_goal or search_goal or (listing_message_goal and not read_only_message_goal) or clean_start_goal:
                        return VisionDecision(
                            screen_classification="facebook_message_inbox",
                            goal_progress="recovering_to_marketplace",
                            next_action="back",
                            target_box=None,
                            confidence=0.82,
                            reason="Return to Marketplace instead of stopping in the generic Facebook inbox during an active Marketplace workflow.",
                            risk_level="low",
                        )
                    return VisionDecision.stop("Facebook message inbox is visible for read-only inspection.")
            if self._facebook_backup_prompt_visible(state):
                return VisionDecision(
                    screen_classification="facebook_backup_prompt",
                    goal_progress="recovering",
                    next_action="back",
                    target_box=None,
                    confidence=0.94,
                    reason="Dismiss the transient Facebook backup or recovery prompt to return to the main app shell.",
                    risk_level="low",
                )
            if search_goal and self._facebook_marketplace_search_visible(state):
                if self._goal_requests_script_save(goal) and not self._facebook_script_exists(
                    skill, "open_marketplace_search_surface"
                ):
                    return VisionDecision.tool(
                        tool_name="save_script",
                        tool_arguments=self._facebook_open_search_script_arguments(skill),
                        screen_classification="facebook_marketplace_search",
                        goal_progress="recording_script",
                        confidence=0.96,
                        reason="A stable Marketplace search path has been confirmed, so save it as a reusable script.",
                        target_label="open_marketplace_search_surface",
                    )
                return VisionDecision.stop(
                    "Facebook Marketplace search surface is visible.",
                    goal_progress="completed",
                )
            if self._facebook_listing_detail_visible(state):
                if search_goal:
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="Navigate to Search",
                        screen_classification="facebook_listing_detail",
                        goal_progress="opening_search",
                        confidence=0.88,
                        reason="The goal explicitly targets Marketplace search, so jump from listing detail to the search surface.",
                        risk_level="low",
                    )
                see_conversation = self._tap_decision_for_label(
                    state=state,
                    skill=skill,
                    label="See conversation",
                    screen_classification="facebook_listing_detail",
                    goal_progress="capturing_thread",
                    confidence=0.9,
                    reason="Open the conversation after sending so the seller thread is captured and monitored.",
                    risk_level="low",
                )
                if (
                    see_conversation.next_action == "tap"
                    and "message sent to seller" in " ".join(state.visible_text[:40]).casefold()
                    and not self._recent_target_label_contains(action_history, "see conversation")
                ):
                    if self._facebook_fast_function_exists(skill, "capture_conversation"):
                        return VisionDecision.tool(
                            tool_name="run_fast_function",
                            tool_arguments={
                                "app_name": skill.app_name,
                                "function_name": "capture_conversation",
                                "arguments": {},
                            },
                            screen_classification="facebook_listing_detail",
                            goal_progress="capturing_thread",
                            confidence=0.92,
                            reason="Use the fast function to open and capture the seller conversation after the message was sent.",
                            target_label="capture_conversation",
                        )
                    return see_conversation
                description_expander = self._find_facebook_listing_description_expander(components)
                if description_expander and not self._recent_target_label_contains(action_history, "see more"):
                    if self._facebook_fast_function_exists(skill, "expand_listing_details"):
                        return VisionDecision.tool(
                            tool_name="run_fast_function",
                            tool_arguments={
                                "app_name": skill.app_name,
                                "function_name": "expand_listing_details",
                                "arguments": {},
                            },
                            screen_classification="facebook_listing_detail",
                            goal_progress="inspecting_listing",
                            confidence=0.9,
                            reason="Use the fast function to expand the listing details before continuing.",
                            target_label="expand_listing_details",
                        )
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(description_expander.get("target_box")),
                        screen_classification="facebook_listing_detail",
                        goal_progress="inspecting_listing",
                        confidence=0.89,
                        reason=(
                            "Expand the listing description so the agent can inspect the product image, "
                            "description, and seller details before continuing the resale scan."
                        ),
                        risk_level="low",
                        target_label=description_expander.get("label") or "See more",
                    )
                if self._facebook_should_scroll_listing_details(state, action_history):
                    return VisionDecision(
                        screen_classification="facebook_listing_detail",
                        goal_progress="inspecting_listing",
                        next_action="swipe",
                        target_box=self._facebook_detail_scroll_region(),
                        confidence=0.88,
                        reason=(
                            "Scroll slightly within the listing detail so the agent can inspect "
                            "location, condition, and seller-visible details before leaving the item."
                        ),
                        risk_level="low",
                    )
                return VisionDecision(
                    screen_classification="facebook_listing_detail",
                    goal_progress="continuing_scan",
                    next_action="back",
                    target_box=None,
                    confidence=0.91,
                    reason="Back out of the Marketplace listing detail after inspection and continue scanning the feed.",
                    risk_level="low",
                ) if not self._facebook_fast_function_exists(skill, "close_listing_to_feed") else VisionDecision.tool(
                    tool_name="run_fast_function",
                    tool_arguments={
                        "app_name": skill.app_name,
                        "function_name": "close_listing_to_feed",
                        "arguments": {},
                    },
                    screen_classification="facebook_listing_detail",
                    goal_progress="continuing_scan",
                    confidence=0.92,
                    reason="Use the fast function to close the listing and return to the Marketplace feed.",
                    target_label="close_listing_to_feed",
                )
            if self._facebook_marketplace_feed_visible(state):
                if search_goal:
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="What do you want to buy?",
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="opening_search",
                        confidence=0.9,
                        reason="The goal explicitly targets Marketplace search, so open the Marketplace search surface instead of scanning listings.",
                        risk_level="low",
                    )
                if action_history and action_history[-1].get("action") == "back":
                    return VisionDecision(
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="advancing_feed",
                        next_action="swipe",
                        target_box=self._facebook_feed_scroll_region(),
                        confidence=0.82,
                        reason="Advance the Marketplace feed so the next read-only listing inspection reaches a new item.",
                        risk_level="low",
                    )
                listing_component = self._find_facebook_listing_component(components)
                if listing_component and not any(item.get("action") == "tap" for item in action_history[-2:]):
                    label = str(listing_component.get("label") or "Marketplace listing")
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(listing_component.get("target_box")),
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="opening_listing",
                        confidence=0.84,
                        reason="Open a Marketplace listing to inspect its price and condition read-only.",
                        risk_level="low",
                        target_label=label,
                    )
                if not any(item.get("action") == "swipe" for item in action_history[-2:]):
                    return VisionDecision(
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="advancing_feed",
                        next_action="swipe",
                        target_box=self._facebook_feed_scroll_region(),
                        confidence=0.74,
                        reason="Scroll the Marketplace feed to inspect additional local listings.",
                        risk_level="low",
                    )
                return VisionDecision.stop("Facebook Marketplace feed has been scanned and no stronger next listing heuristic was found.")
            if self._facebook_home_feed_visible(state):
                if should_check_replies:
                    if self._facebook_fast_function_exists(skill, "open_messages_from_home"):
                        return VisionDecision.tool(
                            tool_name="run_fast_function",
                            tool_arguments={
                                "app_name": skill.app_name,
                                "function_name": "open_messages_from_home",
                                "arguments": {},
                            },
                            screen_classification="facebook_home_feed",
                            goal_progress="checking_replies",
                            confidence=0.89,
                            reason="Use the fast function to open Messaging before checking Marketplace replies.",
                            target_label="open_messages_from_home",
                        )
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="Messaging",
                        screen_classification="facebook_home_feed",
                        goal_progress="checking_replies",
                        confidence=0.86,
                        reason="Check Marketplace-related replies after recent seller outreach before scanning more listings.",
                        risk_level="low",
                    )
                if self._facebook_fast_function_exists(skill, "open_marketplace_feed"):
                    return VisionDecision.tool(
                        tool_name="run_fast_function",
                        tool_arguments={
                            "app_name": skill.app_name,
                            "function_name": "open_marketplace_feed",
                            "arguments": {},
                        },
                        screen_classification="facebook_home_feed",
                        goal_progress="navigating_to_marketplace",
                        confidence=0.9,
                        reason="Use the fast function to normalize from the Facebook home feed into Marketplace.",
                        target_label="open_marketplace_feed",
                    )
                return self._tap_decision_for_label(
                    state=state,
                    skill=skill,
                    label="Marketplace, tab 4 of 6",
                    screen_classification="facebook_home_feed",
                    goal_progress="navigating_to_marketplace",
                    confidence=0.86,
                    reason="Open Marketplace from the Facebook home feed.",
                    risk_level="low",
                )
            if self._facebook_home_shell_visible(state):
                if should_check_replies:
                    if self._facebook_fast_function_exists(skill, "open_messages_from_home"):
                        return VisionDecision.tool(
                            tool_name="run_fast_function",
                            tool_arguments={
                                "app_name": skill.app_name,
                                "function_name": "open_messages_from_home",
                                "arguments": {},
                            },
                            screen_classification="facebook_home_shell",
                            goal_progress="checking_replies",
                            confidence=0.89,
                            reason="Use the fast function to open Messaging before checking Marketplace replies.",
                            target_label="open_messages_from_home",
                        )
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label="Messaging",
                        screen_classification="facebook_home_shell",
                        goal_progress="checking_replies",
                        confidence=0.86,
                        reason="Check Marketplace-related replies after recent seller outreach before scanning more listings.",
                        risk_level="low",
                    )
                if self._facebook_fast_function_exists(skill, "open_marketplace_feed"):
                    return VisionDecision.tool(
                        tool_name="run_fast_function",
                        tool_arguments={
                            "app_name": skill.app_name,
                            "function_name": "open_marketplace_feed",
                            "arguments": {},
                        },
                        screen_classification="facebook_home_shell",
                        goal_progress="navigating",
                        confidence=0.9,
                        reason="Use the fast function to normalize from the Facebook home shell into Marketplace.",
                        target_label="open_marketplace_feed",
                    )
                return self._tap_decision_for_label(
                    state=state,
                    skill=skill,
                    label="Marketplace, tab 4 of 6",
                    screen_classification="facebook_home_shell",
                    goal_progress="navigating",
                    confidence=0.86,
                    reason="Open Marketplace from the clean Facebook home shell.",
                    risk_level="low",
                )
            if self._goal_requests_clean_start(goal) and not any(
                item.get("tool_name") == "reset_app" or item.get("action") == "reset_app"
                for item in action_history[-3:]
            ):
                return VisionDecision.tool(
                    tool_name="reset_app",
                    tool_arguments={"package_name": state.package_name},
                    screen_classification="facebook_recovering",
                    goal_progress="recovering",
                    confidence=0.94,
                    reason="Reset Facebook to a clean main view before continuing the Marketplace scan.",
                    target_label=state.package_name,
                )
            if state.visible_text or state.clickable_text or components:
                return VisionDecision.stop("Facebook is visible but no stronger Marketplace heuristic was found.")
            return VisionDecision(
                screen_classification="facebook_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="Facebook is open but the UI is still stabilizing.",
                risk_level="low",
            )

        if state.package_name == "com.android.vending":
            search_goal = self._extract_search_query(goal)
            install_goal = self._extract_install_query(goal)
            recent_actions = action_history[-3:]
            for label in state.visible_text:
                lowered = label.casefold()
                if lowered in {"以后再说", "稍后", "not now", "later"}:
                    if self._repeated_label_taps(recent_actions, label):
                        return VisionDecision(
                            screen_classification="playstore_interstitial",
                            goal_progress="recovering",
                            next_action="back",
                            target_box=None,
                            confidence=0.66,
                            reason="Dismiss the stuck Play Store interstitial with Back.",
                            risk_level="low",
                            target_label=label,
                        )
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label=label,
                        component_type="touch_target",
                        screen_classification="playstore_interstitial",
                        goal_progress="dismissing_popup",
                        confidence=0.72,
                        reason="Dismiss the Play Store interstitial before searching.",
                        risk_level="low",
                    )

            search_input = self._find_component(components, component_type="text_input", search_related=True)
            search_action = self._find_component(components, component_type="search_action", search_related=True)
            install_action = self._find_playstore_install_component(components)
            result_action = self._find_playstore_result_component(
                components,
                query=install_goal or search_goal,
            )
            if self._playstore_install_complete(state):
                return VisionDecision.stop("The Play Store app is installed and ready to open.")
            if self._playstore_install_in_progress(state):
                return VisionDecision(
                    screen_classification="playstore_install_progress",
                    goal_progress="waiting_for_install",
                    next_action="wait",
                    target_box=None,
                    confidence=0.86,
                    reason="Wait for the Play Store download or install to finish.",
                    risk_level="low",
                )
            if install_goal and install_action:
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(install_action.get("target_box")),
                    screen_classification="playstore_detail",
                    goal_progress="starting_install",
                    confidence=0.84,
                    reason="Tap the Play Store install button for the requested free app or game.",
                    risk_level="low",
                    target_label=install_action.get("label") or "install",
                )
            if install_goal and result_action:
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(result_action.get("target_box")),
                    screen_classification="playstore_results",
                    goal_progress="opening_result",
                    confidence=0.79,
                    reason="Open the requested app or game from the Play Store search results.",
                    risk_level="low",
                    target_label=result_action.get("label"),
                )
            if "search field" in goal.casefold() and search_input:
                return VisionDecision.stop("The Play Store search field is visible.")
            if search_goal and self._playstore_results_visible(state, search_goal):
                return VisionDecision.stop("The Play Store search results are visible.")
            if (search_goal or install_goal) and search_input:
                query = install_goal or search_goal
                if search_input.get("focused"):
                    return VisionDecision(
                        screen_classification="playstore_search_input",
                        goal_progress="typing_query",
                        next_action="type",
                        target_box=BoundingBox.from_dict(search_input.get("target_box")),
                        confidence=0.82,
                        reason="Enter the Play Store search query and submit it.",
                        risk_level="low",
                        input_text=query,
                        submit_after_input=True,
                        target_label=search_input.get("label") or "search",
                    )
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(search_input.get("target_box")),
                    screen_classification="playstore_home",
                    goal_progress="focusing_search",
                    confidence=0.74,
                    reason="Focus the Play Store search field.",
                    risk_level="low",
                    target_label=search_input.get("label") or "search",
                )
            if ("search field" in goal.casefold() or search_goal or install_goal) and search_action:
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(search_action.get("target_box")),
                    screen_classification="playstore_home",
                    goal_progress="opening_search",
                    confidence=0.68,
                    reason="Open the Play Store search UI.",
                    risk_level="low",
                    target_label=search_action.get("label") or "search",
                )
            if state.visible_text or state.clickable_text or components:
                return VisionDecision.stop("Play Store is visible.")
            return VisionDecision(
                screen_classification="playstore_unknown",
                goal_progress="researching",
                next_action="wait",
                target_box=None,
                confidence=0.4,
                reason="Play Store is open but the page is still stabilizing.",
                risk_level="low",
            )

        return VisionDecision(
            screen_classification="unknown",
            goal_progress="researching",
            next_action="wait",
            target_box=None,
            confidence=0.40,
            reason="Fallback heuristic is waiting for a more stable screen.",
            risk_level="low",
        )

    def _tap_decision(
        self,
        *,
        target_box: BoundingBox | None,
        screen_classification: str,
        goal_progress: str,
        confidence: float,
        reason: str,
        risk_level: str,
        target_label: str | None = None,
    ) -> VisionDecision:
        if target_box is None:
            target_name = target_label or screen_classification
            return VisionDecision.stop(
                f"Target '{target_name}' matched the goal, but no stable target box was available on the current screen.",
                goal_progress="blocked",
            )
        return VisionDecision(
            screen_classification=screen_classification,
            goal_progress=goal_progress,
            next_action="tap",
            target_box=target_box,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            target_label=target_label,
        )

    def _tap_decision_for_label(
        self,
        *,
        state: ScreenState,
        skill: SkillBundle,
        label: str,
        screen_classification: str,
        goal_progress: str,
        confidence: float,
        reason: str,
        risk_level: str,
        component_type: str | None = None,
    ) -> VisionDecision:
        return self._tap_decision(
            target_box=self._lookup_target_box(skill, state, label, component_type=component_type),
            screen_classification=screen_classification,
            goal_progress=goal_progress,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            target_label=label,
        )

    def _lookup_selector_box(self, skill: SkillBundle, state: ScreenState, label: str) -> BoundingBox | None:
        requested_label = label.casefold().strip()
        screen_text = self._selector_screen_text(state)
        current_screen_id = self._screen_id(state)
        scored: list[tuple[int, float, BoundingBox]] = []
        for selector in skill.selectors.get("selectors", []):
            selector_label = str(selector.get("label", "")).strip()
            if not self._labels_match(requested_label, selector_label.casefold()):
                continue
            if selector.get("package_name") not in {None, "", state.package_name}:
                continue
            if selector.get("activity_name") not in {None, "", state.activity_name}:
                continue
            target_box = BoundingBox.from_dict(selector.get("target_box"))
            if target_box is None:
                continue
            score = 0
            if selector_label.casefold() == requested_label:
                score += 4
            else:
                score += 2
            if selector.get("screen_id") == current_screen_id:
                score += 4
            anchor_text = selector.get("anchor_text") or []
            anchor_match = any(str(anchor).casefold() in screen_text for anchor in anchor_text)
            if anchor_text and anchor_match:
                score += 2
            elif anchor_text and selector.get("screen_id") != current_screen_id:
                continue
            scored.append((score, target_box.width * target_box.height, target_box))
        if not scored:
            return None
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[0][2]

    @staticmethod
    def _labels_match(requested_label: str, selector_label: str) -> bool:
        if requested_label == selector_label:
            return True
        if requested_label in selector_label or selector_label in requested_label:
            return True
        requested_tokens = {token for token in re.split(r"[^a-z0-9]+", requested_label) if token}
        selector_tokens = {token for token in re.split(r"[^a-z0-9]+", selector_label) if token}
        if not requested_tokens or not selector_tokens:
            return False
        overlap = requested_tokens & selector_tokens
        return len(overlap) >= min(2, len(requested_tokens), len(selector_tokens))

    @staticmethod
    def _selector_screen_text(state: ScreenState) -> str:
        component_labels = [
            str(component.get("label", ""))
            for component in state.components[:20]
            if component.get("label")
        ]
        return " ".join(state.visible_text[:24] + state.clickable_text[:24] + component_labels).casefold()

    @staticmethod
    def _screen_id(state: ScreenState) -> str:
        signature = describe_state_signature(state)
        return slugify(
            f"{signature['package_name']}-{signature['activity_name']}-{signature['text_digest']}"
        )

    def _build_prompt(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        system_instruction: str,
        action_history: list[dict[str, Any]],
        available_tools: list[dict[str, Any]],
        yolo_mode: bool,
    ) -> str:
        login_policy = (
            "- YOLO mode is enabled. Do not ask for approval on onboarding, permission, or consent prompts. "
            "Pick the safest viable action and continue autonomously.\n"
            "- Never invent credentials. If a password or verification code is required, stop."
            if yolo_mode
            else "- Stop if login or verification is required.\n"
            "- If a popup, dialog, permission prompt, onboarding card, or system surface requires user approval, "
            "stop and ask for approval instead of acting automatically."
        )
        return f"""
You are controlling an Android app in low-risk exploration mode.

Goal:
- {goal}

Safety policy:
- Never purchase, confirm payment, submit an irreversible form, message support, or edit account settings.
- Prefer reading status/details and navigating low-risk tabs or order pages.
{login_policy}

Current app:
- package: {state.package_name}
- activity: {state.activity_name}
- visible_text: {state.visible_text[:40]}
- clickable_text: {state.clickable_text[:20]}
- components: {json.dumps(state.components[:12], ensure_ascii=False)}
- device_size: {state.device.width}x{state.device.height}

Skill instructions:
{skill.instructions[:2500]}

System navigation skill:
{system_instruction[:2500]}

Known screens:
{json.dumps(skill.screens, indent=2)[:2500]}

Known selectors:
{json.dumps(skill.selectors, indent=2)[:2500]}

Known app backup:
{skill.backup_summary[:2500]}

Recent action history:
{json.dumps(action_history[-6:], indent=2)}

Available tools:
{json.dumps(available_tools, indent=2)}

Return a single JSON object only.
Use normalized coordinates in target_box with values in the 0..1 range.
If you type into a search box and the query should be submitted immediately, set submit_after_input=true.
If you need an explicit tool, return next_action="tool", set tool_name, and set tool_arguments_json to a JSON object string.
Before replaying or saving a reusable script, prefer normalizing the app to a clean main view. If the app can resume stale or deep-linked screens, use tool_name="reset_app" with tool_arguments_json containing package_name and optional activity. If reset reveals a transient onboarding, backup, or recovery prompt, use back navigation until the main app view is visible before continuing.
To save a reusable automation script, use tool_name="save_script" with tool_arguments_json containing script_name, description, and steps.
To replay a saved script, use tool_name="run_script" with tool_arguments_json containing script_name.
To list available scripts, use tool_name="list_scripts".
Use the app backup summary to avoid rereading long conversations or revisiting already-contacted items from the beginning when the backup already contains the needed context.
If you cannot proceed safely, return next_action="stop".
""".strip()

    def _extract_text(self, payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini response contained no candidates.")
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            raise ValueError("Gemini response contained no parts.")
        return parts[0].get("text", "")

    def _extract_lmstudio_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not choices:
            raise ValueError("LM Studio response contained no choices.")
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content)

    def _read_lmstudio_response(self, response: Any) -> dict[str, Any]:
        body = response.read()
        text = body.decode("utf-8", errors="replace")
        content_type = ""
        headers = getattr(response, "headers", None)
        if headers is not None:
            content_type = str(headers.get("Content-Type", ""))
        if "text/event-stream" in content_type.casefold() or text.lstrip().startswith("data:"):
            return self._parse_lmstudio_sse_payload(text)
        return json.loads(text)

    def _parse_lmstudio_sse_payload(self, text: str) -> dict[str, Any]:
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        last_chunk: dict[str, Any] | None = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload_text = line[5:].strip()
            if not payload_text or payload_text == "[DONE]":
                continue
            try:
                chunk = json.loads(payload_text)
            except json.JSONDecodeError:
                continue
            last_chunk = chunk
            choices = chunk.get("choices", [])
            if not choices:
                continue
            choice = choices[0]
            delta = choice.get("delta", {})
            message = choice.get("message", {})
            content_parts.extend(self._lmstudio_text_parts(delta.get("content")))
            content_parts.extend(self._lmstudio_text_parts(message.get("content")))
            reasoning_parts.extend(self._lmstudio_text_parts(delta.get("reasoning_content")))
            reasoning_parts.extend(self._lmstudio_text_parts(message.get("reasoning_content")))
        return {
            "choices": [
                {
                    "message": {
                        "content": "".join(content_parts),
                        "reasoning_content": "".join(reasoning_parts),
                    }
                }
            ],
            "streamed": True,
            "last_chunk": last_chunk,
        }

    def _lmstudio_text_parts(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    if item.get("type") == "text" or "text" in item:
                        parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return [part for part in parts if part]
        if isinstance(value, dict) and "text" in value:
            return [str(value.get("text", ""))]
        return [str(value)]

    def _extract_lmstudio_reasoning_text(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices", [])
        if not choices:
            return ""
        message = choices[0].get("message", {})
        reasoning = message.get("reasoning_content", "")
        if isinstance(reasoning, str):
            return reasoning
        if isinstance(reasoning, list):
            parts: list[str] = []
            for item in reasoning:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                    elif "text" in item:
                        parts.append(str(item.get("text", "")))
                elif isinstance(item, str):
                    parts.append(item)
            return "\n".join(part for part in parts if part)
        return str(reasoning)

    def _extract_json_object(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]
        return stripped

    def _resolve_lmstudio_timeout_seconds(self) -> float:
        raw = os.getenv("LMSTUDIO_TIMEOUT_SECONDS", "").strip()
        if not raw:
            return float(self.LMSTUDIO_TIMEOUT_SECONDS)
        try:
            value = float(raw)
        except ValueError:
            return float(self.LMSTUDIO_TIMEOUT_SECONDS)
        return value if value > 0 else float(self.LMSTUDIO_TIMEOUT_SECONDS)

    def _resolve_gemini_timeout_seconds(self) -> float:
        raw = os.getenv("GEMINI_TIMEOUT_SECONDS", "").strip()
        if not raw:
            return float(self.GEMINI_TIMEOUT_SECONDS)
        try:
            value = float(raw)
        except ValueError:
            return float(self.GEMINI_TIMEOUT_SECONDS)
        return value if value > 0 else float(self.GEMINI_TIMEOUT_SECONDS)

    def _coerce_decision(
        self,
        payload: dict[str, Any],
        *,
        state: ScreenState | None = None,
        skill: SkillBundle | None = None,
    ) -> VisionDecision:
        box = BoundingBox.from_dict(payload.get("target_box"))
        raw_action = str(payload.get("next_action", "stop")).strip().lower().replace(" ", "_")
        next_action = self.ACTION_ALIASES.get(raw_action, raw_action)
        tool_arguments = self._parse_tool_arguments(payload.get("tool_arguments_json"))
        target_label = payload.get("target_label")
        if box is None and target_label and state is not None and skill is not None:
            component_type = None
            if next_action == "type":
                component_type = "text_input"
            box = self._lookup_target_box(skill, state, target_label, component_type=component_type)
        if box is None and next_action == "swipe" and state is not None:
            box = self._default_swipe_box_for_state(state)
        return VisionDecision(
            screen_classification=payload.get("screen_classification", "unknown"),
            goal_progress=payload.get("goal_progress", "researching"),
            next_action=next_action,
            target_box=box,
            confidence=float(payload.get("confidence", 0.0)),
            reason=payload.get("reason", ""),
            risk_level=payload.get("risk_level", "medium"),
            input_text=payload.get("input_text"),
            submit_after_input=bool(payload.get("submit_after_input", False)),
            target_label=target_label,
            tool_name=payload.get("tool_name"),
            tool_arguments=tool_arguments,
            requires_user_approval=bool(payload.get("requires_user_approval", False)),
        )

    def _parse_tool_arguments(self, raw_value: Any) -> dict[str, Any]:
        if raw_value is None:
            return {}
        if isinstance(raw_value, dict):
            return raw_value
        if not isinstance(raw_value, str) or not raw_value.strip():
            return {}
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _should_bypass_model(
        self,
        goal: str,
        state: ScreenState,
        heuristic: VisionDecision,
        *,
        yolo_mode: bool,
    ) -> bool:
        if heuristic.requires_user_approval:
            return True
        if yolo_mode and heuristic.next_action == "stop" and "manual login required" in heuristic.reason.casefold():
            return False
        if (
            state.package_name == "com.facebook.katana"
            and self._facebook_goal_targets_value_scan(goal)
            and (
                self._facebook_marketplace_feed_visible(state)
                or self._facebook_listing_detail_visible(state)
            )
        ):
            return False
        # Only bypass when the heuristic has a concrete, high-confidence action
        if (
            heuristic.confidence >= 0.95
            and heuristic.next_action == "tool"
            and (heuristic.tool_name or "").casefold() == "save_script"
        ):
            return True
        if (
            heuristic.confidence >= 0.90
            and heuristic.next_action == "tool"
            and (heuristic.tool_name or "").casefold() == "reset_app"
        ):
            return True
        if heuristic.confidence >= 0.80 and heuristic.next_action in {"tap", "type", "back", "swipe"}:
            return True
        if heuristic.confidence >= 0.85 and heuristic.next_action == "stop":
            return True
        return False

    def _approval_required_popup_decision(
        self,
        state: ScreenState,
        skill: SkillBundle,
        *,
        yolo_mode: bool,
    ) -> VisionDecision | None:
        if state.package_name == "com.facebook.katana" and (
            self._facebook_home_feed_visible(state)
            or self._facebook_home_shell_visible(state)
            or self._facebook_marketplace_feed_visible(state)
            or self._facebook_marketplace_search_visible(state)
        ):
            return None
        text = " ".join(state.visible_text[:60]).casefold()
        clickable = state.clickable_text[:6]
        resource_ids = " ".join(
            component.get("resource_id", "")
            for component in state.components[:20]
        ).casefold()
        activity = state.activity_name.casefold()
        xml_lower = state.xml_source.casefold()

        is_permission_surface = (
            "permissioncontroller" in state.package_name.casefold()
            or "permission" in activity
            or "grantpermissions" in activity
        )
        has_permission_tokens = any(
            token in text
            for token in [
                "allow",
                "don’t allow",
                "don't allow",
                "deny",
                "permission",
                "允许",
                "不允许",
                "访问",
            ]
        )
        has_modal_tokens = any(
            token in (resource_ids + " " + activity + " " + xml_lower)
            for token in [
                "dialog",
                "onboarding",
                "welcome",
                "setup_addresses",
                "welcome_tour",
                "pane-title",
            ]
        )
        has_onboarding_actions = any(
            token in text
            for token in [
                "google meet",
                "知道了",
                "转至 gmail",
                "welcome",
            ]
        ) and has_modal_tokens
        has_consent_actions = any(
            self._text_contains_action_token(text, token)
            for token in [
                "agree",
                "accept",
                "continue",
                "user agreement",
                "privacy policy",
                "用户须知",
                "同意",
                "继续",
                "隐私政策",
            ]
        )
        if not (is_permission_surface or has_permission_tokens or has_onboarding_actions or has_consent_actions):
            return None
        action_labels = ", ".join(clickable) if clickable else "no explicit action labels detected"
        summary = "; ".join(state.visible_text[:4]) or state.activity_name or state.package_name
        if yolo_mode:
            auto_decision = self._auto_approval_popup_decision(state=state, skill=skill, summary=summary)
            if auto_decision is not None:
                return auto_decision
            return VisionDecision.stop(
                f"YOLO mode detected an approval surface but no stable action was available: {summary}.",
                goal_progress="blocked",
            )
        return VisionDecision.stop(
            f"User approval required for popup or system surface: {summary}. Available actions: {action_labels}.",
            goal_progress="awaiting_user_approval",
            requires_user_approval=True,
        )

    def _apply_yolo_overrides(
        self,
        *,
        state: ScreenState,
        skill: SkillBundle,
        decision: VisionDecision,
    ) -> VisionDecision:
        if not decision.requires_user_approval:
            return decision
        if decision.next_action != "stop":
            decision.requires_user_approval = False
            return decision
        auto_decision = self._auto_approval_popup_decision(
            state=state,
            skill=skill,
            summary=decision.reason or state.activity_name,
        )
        if auto_decision is not None:
            return auto_decision
        return VisionDecision.stop(
            f"YOLO mode bypassed approval prompts, but no stable action was found. {decision.reason}",
            goal_progress="blocked",
        )

    def _apply_post_decision_overrides(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        action_history: list[dict[str, Any]],
        decision: VisionDecision,
    ) -> VisionDecision:
        if state.package_name != "com.facebook.katana":
            return decision
        read_only_message_goal = self._facebook_goal_requests_read_only_message_check(goal)
        listing_message_goal = self._facebook_goal_targets_listing_message(goal) and not read_only_message_goal
        message_input = self._find_facebook_message_input(state.components)
        if listing_message_goal and self._facebook_listing_detail_visible(state):
            description_expander = self._find_facebook_listing_description_expander(state.components)
            if description_expander and not self._recent_target_label_contains(action_history, "see more") and not self._recent_target_label_contains(action_history, "see details"):
                if self._facebook_fast_function_exists(skill, "expand_listing_details"):
                    return VisionDecision.tool(
                        tool_name="run_fast_function",
                        tool_arguments={
                            "app_name": skill.app_name,
                            "function_name": "expand_listing_details",
                            "arguments": {},
                        },
                        screen_classification=decision.screen_classification or "facebook_listing_detail",
                        goal_progress="inspecting_listing",
                        confidence=max(decision.confidence, 0.9),
                        reason="Use the fast function to expand listing details before drafting a seller message.",
                        target_label="expand_listing_details",
                    )
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(description_expander.get("target_box")),
                    screen_classification=decision.screen_classification or "facebook_listing_detail",
                    goal_progress="inspecting_listing",
                    confidence=max(decision.confidence, 0.9),
                    reason="Expand the listing details before drafting a seller message so the description is read first.",
                    risk_level="low",
                    target_label=description_expander.get("label") or "See details",
                )
            if self._facebook_should_scroll_listing_details(state, action_history):
                return VisionDecision(
                    screen_classification=decision.screen_classification or "facebook_listing_detail",
                    goal_progress="inspecting_listing",
                    next_action="swipe",
                    target_box=self._facebook_detail_scroll_region(),
                    confidence=max(decision.confidence, 0.88),
                    reason="Scroll slightly within the listing detail before drafting a seller message so lower notes are visible.",
                    risk_level="low",
                )
        if decision.next_action == "type" and listing_message_goal and message_input:
            rewritten = self._facebook_finalize_marketplace_message(
                decision.input_text,
                state=state,
                goal=goal,
            )
            if rewritten and self._facebook_fast_function_exists(skill, "send_initial_message"):
                return VisionDecision.tool(
                    tool_name="run_fast_function",
                    tool_arguments={
                        "app_name": skill.app_name,
                        "function_name": "send_initial_message",
                        "arguments": {"message": rewritten},
                    },
                    screen_classification=decision.screen_classification or "facebook_message_composer",
                    goal_progress="sending_reply",
                    confidence=max(decision.confidence, 0.9),
                    reason="Use the fast function to replace the default Marketplace message and send it with verification.",
                    target_label="send_initial_message",
                )
            if rewritten and rewritten != decision.input_text:
                return VisionDecision(
                    screen_classification=decision.screen_classification or "facebook_message_composer",
                    goal_progress="drafting_reply",
                    next_action="type",
                    target_box=decision.target_box or BoundingBox.from_dict(message_input.get("target_box")),
                    confidence=max(decision.confidence, 0.9),
                    reason="Rewrite the Marketplace opener to a human-quality message before sending.",
                    risk_level="low",
                    input_text=rewritten,
                    submit_after_input=False,
                    target_label=message_input.get("label") or decision.target_label or "message input",
                    )
        if decision.next_action == "tap" and str(decision.target_label or "").casefold() == "send":
            if listing_message_goal and message_input and not any(item.get("action") == "type" for item in action_history[-2:]):
                reply_text = (
                    self._extract_message_text(goal)
                    or self._facebook_skill_guided_message(goal=goal, state=state, skill=skill)
                    or self._facebook_default_marketplace_message(state, goal=goal)
                )
                if reply_text:
                    if self._facebook_fast_function_exists(skill, "send_initial_message"):
                        return VisionDecision.tool(
                            tool_name="run_fast_function",
                            tool_arguments={
                                "app_name": skill.app_name,
                                "function_name": "send_initial_message",
                                "arguments": {"message": reply_text},
                            },
                            screen_classification=decision.screen_classification or "facebook_message_composer",
                            goal_progress="sending_reply",
                            confidence=max(decision.confidence, 0.9),
                            reason="Use the fast function to replace the default Marketplace message and send it with verification.",
                            target_label="send_initial_message",
                        )
                    return VisionDecision(
                        screen_classification=decision.screen_classification or "facebook_message_composer",
                        goal_progress="drafting_reply",
                        next_action="type",
                        target_box=BoundingBox.from_dict(message_input.get("target_box")),
                        confidence=max(decision.confidence, 0.9),
                        reason="Replace the default Marketplace message with the derived custom opener before sending.",
                        risk_level="low",
                        input_text=reply_text,
                        submit_after_input=False,
                        target_label=message_input.get("label") or "message input",
                    )
        if (
            decision.next_action == "tool"
            and decision.tool_name == "run_fast_function"
            and listing_message_goal
            and str(decision.tool_arguments.get("function_name") or "") == "send_initial_message"
        ):
            arguments = dict(decision.tool_arguments.get("arguments") or {})
            rewritten = self._facebook_finalize_marketplace_message(
                arguments.get("message"),
                state=state,
                goal=goal,
            )
            if rewritten and rewritten != arguments.get("message"):
                arguments["message"] = rewritten
                updated_tool_arguments = dict(decision.tool_arguments)
                updated_tool_arguments["arguments"] = arguments
                return VisionDecision.tool(
                    tool_name="run_fast_function",
                    tool_arguments=updated_tool_arguments,
                    screen_classification=decision.screen_classification or "facebook_message_composer",
                    goal_progress=decision.goal_progress or "sending_reply",
                    confidence=max(decision.confidence, 0.9),
                    reason="Rewrite the Marketplace opener to a verified human-quality message before executing the fast send function.",
                    target_label=decision.target_label or "send_initial_message",
                )
        return decision

    def _auto_approval_popup_decision(
        self,
        *,
        state: ScreenState,
        skill: SkillBundle,
        summary: str,
    ) -> VisionDecision | None:
        if state.package_name == "com.facebook.katana" and (
            self._facebook_home_feed_visible(state)
            or self._facebook_home_shell_visible(state)
            or self._facebook_marketplace_feed_visible(state)
            or self._facebook_marketplace_search_visible(state)
        ):
            return None
        for tokens in (self.YOLO_PRIMARY_ACTION_TOKENS, self.YOLO_SECONDARY_ACTION_TOKENS):
            for token in tokens:
                for component in state.components[:20]:
                    label = str(component.get("label", "")).strip()
                    if not label or component.get("enabled") is False:
                        continue
                    if len(label) > 80 or "\n" in label:
                        continue
                    if token not in label.casefold():
                        continue
                    return self._tap_decision(
                        target_box=BoundingBox.from_dict(component.get("target_box")),
                        screen_classification="approval_surface",
                        goal_progress="yolo_auto_approval",
                        confidence=0.96,
                        reason="YOLO mode auto-continued through an approval surface.",
                        risk_level="low",
                        target_label=label,
                    )
                for label in state.clickable_text[:8]:
                    if token not in label.casefold():
                        continue
                    return self._tap_decision_for_label(
                        state=state,
                        skill=skill,
                        label=label,
                        screen_classification="approval_surface",
                        goal_progress="yolo_auto_approval",
                        confidence=0.94,
                        reason="YOLO mode auto-continued through an approval surface.",
                        risk_level="low",
                    )
        return None

    @staticmethod
    def _text_contains_action_token(text: str, token: str) -> bool:
        if not token:
            return False
        if re.search(r"[a-z0-9]", token, flags=re.IGNORECASE):
            if " " in token:
                return token in text
            return re.search(rf"\b{re.escape(token)}\b", text) is not None
        return token in text

    def _extract_search_query(self, goal: str) -> str | None:
        lowered = goal.strip()
        patterns = [
            r"search for ['\"](?P<query>[^'\"]+)['\"]",
            r"search for (?P<query>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered, flags=re.IGNORECASE)
            if match:
                query = match.group("query").strip().rstrip(".")
                if query:
                    return query
        return None

    def _extract_install_query(self, goal: str) -> str | None:
        cleaned = goal.strip()
        patterns = [
            r"(?:install|download|get)\s+['\"](?P<query>[^'\"]+)['\"]",
            r"(?:install|download|get)\s+(?P<query>.+?)(?:\s+from\s+play\s+store)?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned, flags=re.IGNORECASE)
            if not match:
                continue
            query = match.group("query").strip().rstrip(".")
            query = re.sub(r"\s+from\s+play\s+store$", "", query, flags=re.IGNORECASE).strip()
            if query and query.casefold() not in {"a game", "the game", "a free game", "game", "app"}:
                return query
        return None

    def _find_component(
        self,
        components: list[dict[str, Any]],
        *,
        component_type: str,
        search_related: bool = False,
    ) -> dict[str, Any] | None:
        for component in components:
            if component.get("component_type") != component_type:
                continue
            if search_related and not component.get("search_related"):
                continue
            if component.get("enabled") is False and component_type != "touch_target":
                continue
            return component
        return None

    def _lookup_target_box(
        self,
        skill: SkillBundle,
        state: ScreenState,
        label: str,
        *,
        component_type: str | None = None,
    ) -> BoundingBox | None:
        for component in state.components:
            component_label = str(component.get("label", ""))
            if component_label.casefold() != label.casefold():
                continue
            if component_type and component.get("component_type") != component_type:
                continue
            return BoundingBox.from_dict(component.get("target_box"))
        return self._lookup_selector_box(skill, state, label)

    def _playstore_results_visible(self, state: ScreenState, query: str) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        query_lower = query.casefold()
        result_tokens = ["结果", "results", "install", "评分", "rating"]
        return query_lower in text and any(token in text for token in result_tokens)

    def _find_playstore_install_component(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        for component in components:
            label = str(component.get("label", "")).casefold()
            if "安装" in label or label.startswith("install"):
                return component
        return None

    def _find_playstore_result_component(
        self,
        components: list[dict[str, Any]],
        *,
        query: str | None,
    ) -> dict[str, Any] | None:
        if not query:
            return None
        query_lower = query.casefold()
        best: dict[str, Any] | None = None
        for component in components:
            label = str(component.get("label", ""))
            lowered = label.casefold()
            if "展开" in label or "expand" in lowered:
                continue
            if query_lower in lowered:
                best = component
                if "\n" in label:
                    return component
        return best

    def _playstore_install_in_progress(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        if any(token in text for token in ["等待中", "正在安装", "cancel", "取消", "下载进度"]):
            return True
        if re.search(r"\b\d+%\b", text):
            return True
        return bool(re.search(r"\b\d+(?:\.\d+)?\s*mb\b", text))

    def _playstore_install_complete(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return any(token in text for token in ["打开", "open", "开始游戏", "play", "卸载"])

    def _manual_verification_or_restriction_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:100]).casefold()
        if not text:
            return False
        restriction_tokens = [
            "confirm your identity",
            "verify your identity",
            "identity verification",
            "unusual activity",
            "suspicious activity",
            "limited the number",
            "try again tomorrow",
            "temporarily restricted",
            "temporarily locked",
            "account restricted",
            "your account has been restricted",
            "appeal this decision",
        ]
        return any(token in text for token in restriction_tokens)

    def _facebook_backup_prompt_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        activity = state.activity_name.casefold()
        return (
            "cloudbackup" in activity
            or "restore chat history on this device" in text
            or "restore now" in text
        )

    def _facebook_listing_detail_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return any(
            token in text
            for token in [
                "message seller",
                "contact seller",
                "send offer",
                "hello, is this still available?",
                "buy now",
                "ships for",
                "payments are processed securely",
                "message sent to seller",
                "see conversation",
            ]
        )

    def _facebook_marketplace_feed_visible(self, state: ScreenState) -> bool:
        if self._facebook_marketplace_search_visible(state):
            return False
        text_items = [item.casefold() for item in (state.visible_text[:60] + state.clickable_text[:40])]
        has_marketplace = any("marketplace" in item for item in text_items)
        has_feed_anchor = any(
            item == "for you"
            or item.startswith("for you, tab")
            or item == "local"
            or item.startswith("local, tab")
            or "location:" in item
            or "what do you want to buy?" in item
            for item in text_items
        )
        return has_marketplace and has_feed_anchor

    def _facebook_marketplace_search_visible(self, state: ScreenState) -> bool:
        text_items = [item.casefold() for item in state.visible_text[:60]]
        clickable_items = [item.casefold() for item in state.clickable_text[:30]]
        text = " ".join(text_items)
        clickable = " ".join(clickable_items)
        if "what do you want to buy?" not in text:
            return False
        if any(token in text for token in ["recent searches", "saved searches", "recent, tab 1 of 2"]):
            return True
        if "back" in clickable and (
            "get help on marketplace" in text
            or any(component.get("component_type") == "text_input" for component in state.components[:10])
        ):
            return True
        return False

    def _facebook_home_feed_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        clickable = " ".join(state.clickable_text[:30]).casefold()
        return "what's on your mind?" in text and "messaging" in clickable

    def _facebook_home_shell_visible(self, state: ScreenState) -> bool:
        if self._facebook_marketplace_feed_visible(state):
            return False
        labels = [item.casefold() for item in (state.visible_text[:60] + state.clickable_text[:40])]
        labels.extend(
            str(component.get("label", "")).casefold()
            for component in state.components[:40]
            if component.get("label")
        )
        return any("marketplace, tab 4 of 6" in item for item in labels)

    def _facebook_message_recovery_prompt_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return "are you sure?" in text and "end-to-end encrypted messages" in text

    def _facebook_message_thread_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        activity = state.activity_name.casefold()
        if "msysthreadviewactivity" in activity or "thread" in activity:
            return True
        has_message_surface = any(
            token in text
            for token in ["type a message", "write a message", "reply", "marketplace listing", "additional attachment options"]
        )
        return has_message_surface and "send" in text

    def _facebook_message_inbox_visible(self, state: ScreenState) -> bool:
        if self._facebook_message_thread_visible(state) or self._facebook_thread_settings_visible(state):
            return False
        text = " ".join(state.visible_text[:60]).casefold()
        return any(token in text for token in ["messenger", "messages", "chats", "search messenger"])

    def _facebook_marketplace_account_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:80]).casefold()
        return "view marketplace profile" in text and any(
            token in text
            for token in [
                "saved items",
                "message",
                "messages",
                "recently viewed",
                "marketplace access",
            ]
        )

    def _facebook_thread_settings_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:80]).casefold()
        activity = state.activity_name.casefold()
        if "threadsettingssurfaceactivity" in activity or "threadsettings" in activity:
            return True
        return all(token in text for token in ["mute notifications", "chat info"]) and any(
            token in text for token in ["leave chat", "search in conversation", "read receipts"]
        )

    def _facebook_marketplace_inbox_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:80]).casefold()
        if "marketplace inbox" in text:
            return True
        return "marketplace seller inbox" in text and "marketplace buyer inbox" in text and any(
            token in text for token in ["buying", "selling", "accepted offers", "pending offers", "inbox"]
        )

    def _facebook_marketplace_help_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:40]).casefold()
        return "get help on marketplace" in text and any(
            token in text for token in ["safety tips", "block someone", "mark an item as sold"]
        )

    def _find_facebook_message_input(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        for component in components:
            component_type = str(component.get("component_type") or "")
            label = str(component.get("label", "")).casefold()
            resource_id = str(component.get("resource_id", "")).casefold()
            if component_type not in {"text_input", "touch_target"}:
                continue
            if resource_id == "marketplace_pdp_message_cta_input":
                return component
            if any(
                token in label
                for token in [
                    "message",
                    "still available",
                    "is this available",
                    "type a message",
                    "write a message",
                    "reply",
                ]
            ):
                return component
        return None

    def _find_facebook_marketplace_messages_entry(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        for component in components:
            if component.get("enabled") is False:
                continue
            label = str(component.get("label", "")).casefold()
            resource_id = str(component.get("resource_id", "")).casefold()
            if (
                (
                    "messages" in label
                    or re.search(r"\b\d+\s+message\b", label)
                    or label.strip().startswith("message")
                )
                and "view marketplace profile" not in label
            ) or "inbox_grid_cell" in resource_id:
                return component
        return None

    def _find_facebook_send_button(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        for component in components:
            label = str(component.get("label", "")).strip().casefold()
            if label == "send":
                return component
        return None

    def _find_facebook_seller_contact_button(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for component in components:
            if component.get("enabled") is False:
                continue
            label = str(component.get("label", "")).strip().casefold()
            if not label:
                continue
            if label in {"message seller", "contact seller"}:
                return component
            if label == "hello, is this still available?":
                best = component
        return best

    @staticmethod
    def _facebook_workflow_state(skill: SkillBundle) -> dict[str, Any]:
        generic = skill.state.get("workflow_state")
        if isinstance(generic, dict) and generic:
            queue = list(generic.get("queue") or [])
            if queue or generic.get("mode") or generic.get("active_thread_key") or generic.get("active_item_key"):
                return {
                    "mode": generic.get("mode") or "hunt",
                    "mode_reason": generic.get("mode_reason"),
                    "reply_queue": queue,
                    "active_thread_key": generic.get("active_thread_key"),
                    "active_listing_key": generic.get("active_item_key"),
                    "last_mode_switch_at": generic.get("last_mode_switch_at"),
                    "last_reply_check_at": generic.get("last_observed_at"),
                }
        facebook = skill.backup_data.get("facebook_marketplace", {})
        workflow = facebook.get("workflow")
        if isinstance(workflow, dict):
            return workflow
        fallback = skill.state.get("facebook_workflow")
        return fallback if isinstance(fallback, dict) else {}

    def _facebook_reply_queue(self, skill: SkillBundle) -> list[dict[str, Any]]:
        workflow = self._facebook_workflow_state(skill)
        queue = workflow.get("reply_queue")
        return list(queue) if isinstance(queue, list) else []

    def _facebook_active_thread_record(self, skill: SkillBundle, state: ScreenState | None = None) -> dict[str, Any] | None:
        facebook = skill.backup_data.get("facebook_marketplace", {})
        workflow = self._facebook_workflow_state(skill)
        active_thread_key = str(workflow.get("active_thread_key") or "")
        threads = list(facebook.get("threads") or [])
        contacts = list(facebook.get("contacted_items") or [])
        if state is not None:
            header = next(
                (
                    text
                    for text in state.visible_text
                    if " · " in text and "marketplace listing" not in text.casefold() and "reviews of " not in text.casefold()
                ),
                None,
            )
            if header:
                for thread in threads:
                    if str(thread.get("thread_title") or "") == header:
                        return self._facebook_enrich_thread_with_contact(thread, contacts)
        if active_thread_key:
            for thread in threads:
                if str(thread.get("thread_key") or "") == active_thread_key:
                    return self._facebook_enrich_thread_with_contact(thread, contacts)
        queue = self._facebook_reply_queue(skill)
        if queue:
            queue_key = str(queue[0].get("thread_key") or "")
            for thread in threads:
                if str(thread.get("thread_key") or "") == queue_key:
                    return self._facebook_enrich_thread_with_contact(thread, contacts)
        return self._facebook_enrich_thread_with_contact(threads[0], contacts) if threads else None

    @staticmethod
    def _facebook_enrich_thread_with_contact(thread: dict[str, Any], contacts: list[dict[str, Any]]) -> dict[str, Any]:
        thread_key = str(thread.get("thread_key") or "")
        item_title = str(thread.get("item_title") or "")
        match = next(
            (
                item
                for item in contacts
                if (thread_key and str(item.get("thread_key") or "") == thread_key)
                or (item_title and str(item.get("item_title") or "") == item_title)
            ),
            None,
        )
        if not match:
            return thread
        enriched = dict(match)
        enriched.update(thread)
        return enriched

    def _find_facebook_marketplace_entry_from_message_inbox(
        self,
        components: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = float("-inf")
        for component in components:
            if component.get("enabled") is False:
                continue
            label = str(component.get("label") or "").strip()
            lowered = label.casefold()
            if not label:
                continue
            if any(
                token in lowered
                for token in [
                    "chat profile",
                    "marketplace listing",
                    "mute notifications",
                    "read receipts",
                    "back |",
                ]
            ):
                continue
            score = 0.0
            if "marketplace" in lowered:
                score += 5.0
            if "unread" in lowered or "new message" in lowered or "new messages" in lowered:
                score += 4.0
            if "chat" in lowered or "message" in lowered:
                score += 1.0
            if score > best_score:
                best_score = score
                best = component
        return best if best_score > 0 else None

    def _facebook_reply_mode_decision(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        action_history: list[dict[str, Any]],
        workflow: dict[str, Any],
        message_input: dict[str, Any] | None,
        send_button: dict[str, Any] | None,
        send_requested: bool,
    ) -> VisionDecision:
        if self._facebook_marketplace_help_visible(state) or self._facebook_thread_settings_visible(state):
            return VisionDecision(
                screen_classification="facebook_reply_recovery",
                goal_progress="recovering_to_replies",
                next_action="back",
                target_box=None,
                confidence=0.9,
                reason="Return from a stale Facebook surface and continue the Marketplace reply workflow.",
                risk_level="low",
            )
        if self._facebook_backup_prompt_visible(state) or self._facebook_message_recovery_prompt_visible(state):
            return VisionDecision(
                screen_classification="facebook_reply_recovery",
                goal_progress="recovering_to_replies",
                next_action="back",
                target_box=None,
                confidence=0.88,
                reason="Dismiss the transient Facebook prompt and continue the Marketplace reply workflow.",
                risk_level="low",
            )
        if self._facebook_listing_detail_visible(state):
            return VisionDecision(
                screen_classification="facebook_listing_detail",
                goal_progress="switching_to_replies",
                next_action="back",
                target_box=None,
                confidence=0.86,
                reason="Finish the current listing surface and recover into Marketplace replies before opening any new listing.",
                risk_level="low",
            )
        has_home_shell_actions = any(
            str(component.get("label") or "") in {"Messaging", "Marketplace, tab 4 of 6"}
            for component in state.components
        )
        if self._facebook_home_feed_visible(state) or has_home_shell_actions:
            if self._facebook_fast_function_exists(skill, "open_messages_from_home"):
                return VisionDecision.tool(
                    tool_name="run_fast_function",
                    tool_arguments={
                        "app_name": skill.app_name,
                        "function_name": "open_messages_from_home",
                        "arguments": {},
                    },
                    screen_classification="facebook_home_feed",
                    goal_progress="checking_replies",
                    confidence=0.89,
                    reason="Use the fast function to open Messaging before draining actionable Marketplace replies.",
                    target_label="open_messages_from_home",
                )
            messaging_entry = self._tap_decision_for_label(
                state=state,
                skill=skill,
                label="Messaging",
                screen_classification="facebook_home_feed",
                goal_progress="checking_replies",
                confidence=0.85,
                reason="Open Messaging first so the agent can reach actionable Marketplace seller replies.",
                risk_level="low",
            )
            if messaging_entry.next_action == "tap":
                return messaging_entry
            return self._tap_decision_for_label(
                state=state,
                skill=skill,
                label="Marketplace, tab 4 of 6",
                screen_classification="facebook_home_feed",
                goal_progress="navigating_to_replies",
                confidence=0.85,
                reason="Reply mode first re-enters Marketplace before opening seller messages.",
                risk_level="low",
            )
        if self._facebook_marketplace_feed_visible(state) or self._facebook_marketplace_search_visible(state):
            return self._tap_decision_for_label(
                state=state,
                skill=skill,
                label="Tap to view your Marketplace account",
                screen_classification="facebook_marketplace_feed",
                goal_progress="opening_marketplace_account",
                confidence=0.84,
                reason="Open the Marketplace account page to reach seller messages in reply mode.",
                risk_level="low",
            )
        messages_entry = self._find_facebook_marketplace_messages_entry(state.components)
        if messages_entry and not (
            self._facebook_marketplace_inbox_visible(state) or self._facebook_message_thread_visible(state)
        ):
            return self._tap_decision(
                target_box=BoundingBox.from_dict(messages_entry.get("target_box")),
                screen_classification="facebook_marketplace_account",
                goal_progress="opening_messages",
                confidence=0.87,
                reason="Open the Marketplace messages row and drain actionable seller replies.",
                risk_level="low",
                target_label=messages_entry.get("label") or "messages",
            )
        if self._facebook_message_inbox_visible(state):
            thread_entry = self._find_facebook_inbox_thread_entry(state.components, skill)
            if thread_entry is not None and not self._recent_target_label_contains(
                action_history,
                str(thread_entry.get("label") or ""),
            ):
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(thread_entry.get("target_box")),
                    screen_classification="facebook_message_inbox",
                    goal_progress="opening_reply_thread",
                    confidence=0.85,
                    reason="Open the actionable Marketplace seller thread directly from the generic Facebook inbox.",
                    risk_level="low",
                    target_label=thread_entry.get("label") or "message thread",
                )
            marketplace_entry = self._find_facebook_marketplace_entry_from_message_inbox(state.components)
            if marketplace_entry is not None:
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(marketplace_entry.get("target_box")),
                    screen_classification="facebook_message_inbox",
                    goal_progress="opening_marketplace_inbox",
                    confidence=0.86,
                    reason="Open the Marketplace conversation hub from the broader Facebook inbox.",
                    risk_level="low",
                    target_label=marketplace_entry.get("label") or "Marketplace",
                )
            return VisionDecision(
                screen_classification="facebook_message_inbox",
                goal_progress="recovering_to_replies",
                next_action="back",
                target_box=None,
                confidence=0.8,
                reason="Back out of the generic inbox and re-enter the Marketplace reply path.",
                risk_level="low",
            )
        if self._facebook_marketplace_inbox_visible(state):
            reply_queue = self._facebook_reply_queue(skill)
            if workflow.get("mode") == "reply" and not reply_queue:
                return VisionDecision(
                    screen_classification="facebook_marketplace_inbox",
                    goal_progress="returning_to_hunt",
                    next_action="back",
                    target_box=None,
                    confidence=0.82,
                    reason="No actionable Marketplace replies remain, so return to the hunt flow.",
                    risk_level="low",
                )
            thread_entry = self._find_facebook_marketplace_thread_entry(state.components, skill)
            if thread_entry is not None and not self._recent_target_label_contains(
                action_history,
                str(thread_entry.get("label") or ""),
            ):
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(thread_entry.get("target_box")),
                    screen_classification="facebook_marketplace_inbox",
                    goal_progress="opening_reply_thread",
                    confidence=0.9,
                    reason="Open the highest-priority Marketplace seller thread from the actionable reply queue.",
                    risk_level="low",
                    target_label=thread_entry.get("label") or "marketplace thread",
                )
        if self._facebook_message_thread_visible(state):
            thread = self._facebook_active_thread_record(skill, state)
            reply_text = self._extract_message_text(goal)
            if not reply_text:
                reply_text = self._facebook_skill_guided_thread_reply(goal=goal, state=state, skill=skill, thread=thread)
            if not reply_text and thread is not None:
                reply_text = self._facebook_default_thread_reply(thread)
            if not send_requested:
                latest_reply = ""
                if thread is not None:
                    latest_reply = str(thread.get("last_inbound_message") or "").strip()
                if latest_reply:
                    return VisionDecision.stop(
                        f"Facebook message thread is visible for reading. Latest known seller reply: {latest_reply}"
                    )
                return VisionDecision.stop("Facebook message thread is visible for reading.")
            if message_input and reply_text and not any(item.get("action") == "type" for item in action_history[-2:]):
                if self._facebook_fast_function_exists(skill, "send_thread_reply"):
                    return VisionDecision.tool(
                        tool_name="run_fast_function",
                        tool_arguments={
                            "app_name": skill.app_name,
                            "function_name": "send_thread_reply",
                            "arguments": {"message": reply_text},
                        },
                        screen_classification="facebook_message_thread",
                        goal_progress="sending_reply",
                        confidence=0.9,
                        reason="Use the fast function to send the seller reply with immediate verification.",
                        target_label="send_thread_reply",
                    )
                return VisionDecision(
                    screen_classification="facebook_message_thread",
                    goal_progress="drafting_reply",
                    next_action="type",
                    target_box=BoundingBox.from_dict(message_input.get("target_box")),
                    confidence=0.86,
                    reason="Draft a seller reply using the Facebook skill policy and current thread context.",
                    risk_level="low",
                    input_text=reply_text,
                    submit_after_input=False,
                    target_label=message_input.get("label") or "message input",
                )
            if send_requested and send_button and any(item.get("action") == "type" for item in action_history[-2:]):
                return self._tap_decision(
                    target_box=BoundingBox.from_dict(send_button.get("target_box")),
                    screen_classification="facebook_message_thread",
                    goal_progress="sending_reply",
                    confidence=0.9,
                    reason="Send the Marketplace seller reply and then return to product hunting.",
                    risk_level="low",
                    target_label=send_button.get("label") or "Send",
                )
            if thread and not thread.get("needs_reply"):
                return VisionDecision(
                    screen_classification="facebook_message_thread",
                    goal_progress="returning_to_hunt",
                    next_action="back",
                    target_box=None,
                    confidence=0.84,
                    reason="This seller thread no longer needs a reply, so return to the Marketplace hunt flow.",
                    risk_level="low",
                )
        return VisionDecision(
            screen_classification="facebook_reply_recovery",
            goal_progress="recovering_to_replies",
            next_action="back",
            target_box=None,
            confidence=0.74,
            reason="Recover the Facebook reply workflow toward Marketplace messages.",
            risk_level="low",
        )

    def _find_facebook_inbox_thread_entry(
        self,
        components: list[dict[str, Any]],
        skill: SkillBundle,
    ) -> dict[str, Any] | None:
        threads = list(skill.backup_data.get("facebook_marketplace", {}).get("threads", []))
        contacted = list(skill.backup_data.get("facebook_marketplace", {}).get("contacted_items", []))
        queued = {
            str(item.get("thread_key") or ""): item
            for item in self._facebook_reply_queue(skill)
            if str(item.get("thread_key") or "")
        }
        candidates: list[tuple[int, float, dict[str, Any]]] = []
        for component in components:
            if component.get("enabled") is False:
                continue
            if component.get("component_type") not in {"touch_target", "button"}:
                continue
            label = str(component.get("label", "")).strip()
            target_box = BoundingBox.from_dict(component.get("target_box"))
            if not label or target_box is None:
                continue
            lowered = label.casefold()
            if lowered in {"messenger", "messages", "chats", "search messenger", "back"}:
                continue
            if any(
                token in lowered
                for token in [
                    "get help on marketplace",
                    "safety tips",
                    "see more",
                    "marketplace seller inbox",
                    "marketplace buyer inbox",
                    "pending offers",
                    "accepted offers",
                    "pending door drop plans",
                ]
            ):
                continue
            score = 0
            if "unread" in lowered:
                score += 20
            if ": " in label and any(token in lowered for token in ["yes", "available", "interested", "pickup", "still"]):
                score += 2
            for thread in threads:
                thread_title = str(thread.get("thread_title") or "")
                item_title = str(thread.get("item_title") or "")
                seller_name = str(thread.get("seller_name") or "")
                thread_key = str(thread.get("thread_key") or "")
                if thread_title and self._labels_match(thread_title.casefold(), lowered):
                    score += 8
                if item_title and item_title.casefold() in lowered:
                    score += 5
                if seller_name and seller_name.casefold() in lowered:
                    score += 3
                if thread_key and thread_key in queued:
                    score += 10
            for item in contacted:
                item_title = str(item.get("item_title") or "")
                seller_name = str(item.get("seller_name") or "")
                if item_title and item_title.casefold() in lowered:
                    score += 4
                if seller_name and seller_name.casefold() in lowered:
                    score += 2
            if "marketplace" in lowered and any(
                token in lowered for token in ["unread", "new message", "new messages", "inbox"]
            ):
                score += 1
            if score <= 0:
                continue
            candidates.append((score, target_box.width * target_box.height, component))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (-item[0], item[1]))
        return candidates[0][2]

    def _find_facebook_marketplace_thread_entry(
        self,
        components: list[dict[str, Any]],
        skill: SkillBundle,
    ) -> dict[str, Any] | None:
        matched = self._find_facebook_inbox_thread_entry(components, skill)
        if matched is not None:
            return matched
        candidates: list[tuple[float, dict[str, Any]]] = []
        for component in components:
            if component.get("enabled") is False:
                continue
            if component.get("component_type") not in {"touch_target", "button"}:
                continue
            label = str(component.get("label", "")).strip()
            target_box = BoundingBox.from_dict(component.get("target_box"))
            if not label or target_box is None:
                continue
            lowered = label.casefold()
            if any(
                token in lowered
                for token in [
                    "marketplace seller inbox",
                    "marketplace buyer inbox",
                    "pending offers",
                    "accepted offers",
                    "pending door drop plans",
                    "get help on marketplace",
                    "safety tips",
                    "mark an item as sold",
                    "see more",
                    "all",
                    "buying",
                    "selling",
                ]
            ):
                continue
            score = 0.0
            if " · " in label:
                score += 4.0
            if any(token in lowered for token in ["available", "pickup", "offer sent", "sold "]):
                score += 1.0
            score += max(0.0, 0.2 - (target_box.y * 0.1))
            if score <= 0:
                continue
            candidates.append((score, component))
        if not candidates:
            return None
        candidates.sort(key=lambda item: -item[0])
        return candidates[0][1]

    @staticmethod
    def _facebook_latest_known_reply(skill: SkillBundle) -> str | None:
        facebook = skill.backup_data.get("facebook_marketplace", {})
        for thread in facebook.get("threads", []):
            reply = str(thread.get("last_inbound_message") or "").strip()
            if reply:
                return reply
        for item in facebook.get("contacted_items", []):
            reply = str(item.get("last_inbound_message") or "").strip()
            if reply:
                return reply
        return None

    def _find_facebook_listing_component(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        best_score = float("-inf")
        best_component: dict[str, Any] | None = None
        for component in components:
            label = str(component.get("label", ""))
            lowered = label.casefold()
            if not label.strip():
                continue
            if component.get("enabled") is False:
                continue
            if component.get("component_type") not in {"touch_target", "button"}:
                continue
            score = self._facebook_listing_score(component)
            if component.get("resource_id") == "mp_top_picks_clickable_item":
                score += 3
            if score > best_score:
                best_score = score
                best_component = component
        return best_component if best_score > 0 else None

    def _facebook_listing_score(self, component: dict[str, Any]) -> float:
        label = str(component.get("label", ""))
        lowered = label.casefold()
        if not label.strip():
            return float("-inf")
        prices = [float(value.replace(",", "")) for value in re.findall(r"\$([\d,]+(?:\.\d+)?)", label)]
        primary_price = prices[0] if prices else None
        desirable_tokens = {
            "iphone": 6,
            "ipad": 5,
            "macbook": 6,
            "imac": 5,
            "mac mini": 5,
            "mac studio": 6,
            "surface": 4,
            "thinkpad": 4,
            "monitor": 4,
            "ultrawide": 4,
            "oled": 5,
            "gaming pc": 6,
            "rtx": 6,
            "graphics card": 5,
            "camera": 4,
            "canon": 4,
            "sony": 4,
            "nikon": 4,
            "herman miller": 5,
            "steelcase": 4,
            "ultra": 2,
            "dumbbells": 2,
        }
        undesirable_tokens = {
            "case": -8,
            "screen protector": -8,
            "charger": -5,
            "cable": -5,
            "cover": -5,
            "phone case": -9,
            "mouse pad": -5,
            "sticker": -6,
            "icloud locked": -8,
            "parts only": -7,
            "broken": -7,
            "cracked": -6,
            "tv": -7,
            "television": -7,
            "smart tv": -8,
            "led tv": -7,
            "budget gaming pc": -8,
            "gtx 770": -9,
            "ddr3": -8,
            "fortnite": -3,
            "roblox": -3,
        }
        score = 0.0
        for token, weight in desirable_tokens.items():
            if token in lowered:
                score += weight
        for token, weight in undesirable_tokens.items():
            if token in lowered:
                score += weight
        if "just listed" in lowered:
            score += 1.5
        if "marked down from" in lowered:
            score += 1.0
        if primary_price is not None:
            if primary_price < 20:
                score -= 7
            elif primary_price < 50:
                score -= 3
            elif primary_price <= 2500:
                score += 2
            else:
                score -= 2
            score += min(primary_price / 250.0, 4.0)
        if "$" not in label and "£" not in label:
            score -= 2
        return score

    def _find_facebook_listing_description_expander(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for component in components:
            if component.get("enabled") is False:
                continue
            label = str(component.get("label", "")).casefold()
            if "see more" in label or "see details" in label:
                if best is None or len(label) > len(str(best.get("label", ""))):
                    best = component
        return best

    def _facebook_should_scroll_listing_details(
        self,
        state: ScreenState,
        action_history: list[dict[str, Any]],
    ) -> bool:
        if any(item.get("action") == "swipe" for item in action_history[-2:]):
            return False
        if self._facebook_listing_lower_details_visible(state):
            return False
        if self._recent_target_label_contains(action_history, "see more"):
            return True
        clickable = " ".join(state.clickable_text[:20]).casefold()
        return "see less" in clickable or "description" in " ".join(state.visible_text[:30]).casefold()

    def _facebook_listing_lower_details_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:80] + state.clickable_text[:40]).casefold()
        strong_tokens = ["seller", "listed in", "nearby", "location:", "meet up"]
        supportive_tokens = ["pickup", "condition", "facebook marketplace", "ships from", "local pickup"]
        if any(token in text for token in strong_tokens):
            return True
        return sum(token in text for token in supportive_tokens) >= 2

    @staticmethod
    def _facebook_feed_scroll_region() -> BoundingBox:
        return BoundingBox(x=0.08, y=0.28, width=0.84, height=0.34)

    @staticmethod
    def _facebook_detail_scroll_region() -> BoundingBox:
        return BoundingBox(x=0.08, y=0.62, width=0.84, height=0.22)

    def _default_swipe_box_for_state(self, state: ScreenState) -> BoundingBox | None:
        if state.package_name == "com.facebook.katana":
            if self._facebook_marketplace_feed_visible(state):
                return self._facebook_feed_scroll_region()
            if self._facebook_listing_detail_visible(state):
                return self._facebook_detail_scroll_region()
        return None

    @staticmethod
    def _recent_target_label_contains(action_history: list[dict[str, Any]], token: str, *, limit: int = 4) -> bool:
        token_lower = token.casefold()
        for item in action_history[-limit:]:
            label = str(item.get("target_label") or "").casefold()
            if token_lower in label:
                return True
        return False

    def _repeated_label_taps(self, action_history: list[dict[str, Any]], label: str) -> bool:
        if len(action_history) < 2:
            return False
        recent = action_history[-2:]
        return all(
            item.get("action") == "tap" and label.casefold() in item.get("reason", "").casefold()
            for item in recent
        )

    def _facebook_goal_allows_marketplace_messaging(self, goal: str) -> bool:
        lowered = goal.casefold()
        return "marketplace" in lowered and any(
            token in lowered
            for token in ["message ", "messages", "reply", "respond", "conversation", "chat", "inbox", "seller"]
        )

    def _facebook_goal_targets_listing_message(self, goal: str) -> bool:
        lowered = goal.casefold()
        return self._facebook_goal_allows_marketplace_messaging(goal) and any(
            token in lowered
            for token in [
                "message seller",
                "contact seller",
                "send",
                "send buyer messages",
                "send messages",
                "buyer message",
                "buyer messages",
                "reply to",
                "respond to",
                "draft",
                "ask seller",
            ]
        )

    def _facebook_send_requested(self, goal: str) -> bool:
        lowered = goal.casefold()
        return any(
            token in lowered
            for token in ["send", "reply to", "respond to", "write back", "contact seller", "message seller"]
        )

    def _facebook_goal_requests_read_only_message_check(self, goal: str) -> bool:
        lowered = goal.casefold()
        explicit_tokens = [
            "check for new seller replies",
            "check for seller replies",
            "check marketplace messages",
            "check messages",
            "read the latest seller response",
            "read latest seller response",
            "read the latest thread",
            "read latest thread",
            "latest seller response",
            "latest seller reply",
            "without sending",
            "without sending anything",
        ]
        if any(token in lowered for token in explicit_tokens):
            return True
        if "read-only" in lowered:
            if "read-only scanning" in lowered or "read-only scan" in lowered:
                return False
            message_context_tokens = ["message", "messages", "thread", "reply", "replies", "seller response", "inbox"]
            return any(token in lowered for token in message_context_tokens)
        return False

    def _facebook_goal_targets_thread_replies(self, goal: str) -> bool:
        lowered = goal.casefold()
        if not self._facebook_goal_allows_marketplace_messaging(goal):
            return False
        explicit_tokens = [
            "check facebook marketplace seller replies",
            "check seller replies",
            "check for seller replies",
            "check marketplace messages",
            "follow-up replies",
            "follow up replies",
            "reply to sellers",
            "reply to seller",
            "send follow-up replies",
            "send follow up replies",
            "respond to sellers",
            "respond to seller",
            "check messages and reply",
            "check messages then continue hunting",
        ]
        return any(token in lowered for token in explicit_tokens)

    def _facebook_goal_targets_search(self, goal: str) -> bool:
        lowered = goal.casefold()
        return "marketplace" in lowered and any(
            token in lowered
            for token in ["search", "find ", "look up", "query", "browse search", "open search"]
        )

    def _facebook_goal_targets_value_scan(self, goal: str) -> bool:
        lowered = goal.casefold()
        if "marketplace" not in lowered:
            return False
        return any(
            token in lowered
            for token in [
                "valuable",
                "resell",
                "resale",
                "flip",
                "deal",
                "inspect",
                "description",
                "product image",
                "seller-visible details",
                "price and condition",
            ]
        )

    def _facebook_goal_targets_profit_bargain(self, goal: str) -> bool:
        lowered = goal.casefold()
        if "marketplace" not in lowered:
            return False
        return any(
            token in lowered
            for token in [
                "profitable",
                "profit",
                "resell",
                "resale",
                "flip",
                "valuable",
                "bargain",
                "negotiate",
                "low offer",
                "target price",
            ]
        )

    def _facebook_goal_requires_marketplace_entry(self, goal: str) -> bool:
        lowered = goal.casefold()
        if "marketplace" not in lowered:
            return False
        if self._facebook_goal_requests_read_only_message_check(goal):
            return False
        return any(
            token in lowered
            for token in [
                "inspect",
                "scan",
                "valuable",
                "resell",
                "resale",
                "flip",
                "listing",
                "seller",
                "message the seller",
                "contact seller",
                "open marketplace",
                "search",
            ]
        )

    def _goal_requests_script_save(self, goal: str) -> bool:
        lowered = goal.casefold()
        return any(
            token in lowered
            for token in [
                "save a reusable script",
                "save reusable script",
                "save script",
                "record a reusable script",
                "record script",
            ]
        )

    @staticmethod
    def _goal_requests_clean_start(goal: str) -> bool:
        lowered = goal.casefold()
        return any(
            token in lowered
            for token in [
                "reset facebook",
                "reset to a clean main view",
                "clean main view",
                "clean home view",
                "from a clean main view",
            ]
        )

    def _facebook_script_exists(self, skill: SkillBundle, script_name: str) -> bool:
        return (skill.app_dir / "scripts" / f"{script_name}.json").exists()

    def _facebook_fast_function_exists(self, skill: SkillBundle, function_name: str) -> bool:
        return (skill.app_dir / "functions" / f"{function_name}.json").exists()

    def _facebook_open_search_script_arguments(self, skill: SkillBundle) -> dict[str, Any]:
        return {
            "app_name": skill.app_name,
            "script_name": "open_marketplace_search_surface",
            "description": (
                "Reset Facebook to a clean state, dismiss backup or recovery prompts if they appear, "
                "open Marketplace, and open the Marketplace search surface."
            ),
            "steps": [
                {
                    "action": "reset_app",
                    "package_name": "com.facebook.katana",
                },
                {
                    "action": "wait",
                    "wait_seconds": 5,
                },
                {
                    "action": "back",
                    "only_if_visible_text": "backup",
                },
                {
                    "action": "back",
                    "only_if_visible_text": "recovery",
                },
                {
                    "action": "tap",
                    "target_label": "Marketplace, tab 4 of 6",
                },
                {
                    "action": "wait",
                    "wait_seconds": 3,
                },
                {
                    "action": "tap",
                    "target_label": "What do you want to buy?",
                },
                {
                    "action": "wait",
                    "wait_seconds": 2,
                },
            ],
        }

    def _extract_message_text(self, goal: str) -> str | None:
        cleaned = goal.strip()
        patterns = [
            r"(?:send|reply|respond)(?:\s+to\s+.+?)?(?:\s+with)?\s+['\"](?P<message>[^'\"]+)['\"]",
            r"(?:send|reply|respond)(?:\s+with)?\s+['\"](?P<message>[^'\"]+)['\"]",
            r"(?:send|reply|respond)(?:\s+with)?\s+(?P<message>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, cleaned, flags=re.IGNORECASE)
            if not match:
                continue
            message = match.group("message").strip()
            if pattern.endswith("(?P<message>.+)$") and self._looks_like_instruction_text(message):
                continue
            if message:
                return message
        return None

    @staticmethod
    def _looks_like_instruction_text(message: str) -> bool:
        lowered = message.casefold()
        instruction_tokens = [
            "marketplace",
            "seller",
            "listing",
            "item",
            "message",
            "asking",
            "find a",
            "good resale",
            "promising item",
        ]
        return any(token in lowered for token in instruction_tokens)

    def _facebook_default_marketplace_message(self, state: ScreenState, *, goal: str | None = None) -> str | None:
        title = self._facebook_listing_title(state)
        item_ref = self._facebook_message_item_reference(title)
        ask_price = self._facebook_listing_price(state)
        candidate: str | None = None
        if goal and (self._facebook_goal_targets_value_scan(goal) or self._facebook_goal_targets_profit_bargain(goal)):
            missing_details = self._facebook_missing_listing_details(state)
            if missing_details:
                candidate = self._facebook_missing_details_message(item_ref=item_ref, missing_details=missing_details)
                return self._facebook_finalize_marketplace_message(
                    candidate,
                    state=state,
                    goal=goal,
                    allow_default_fallback=False,
                )
        if goal and self._facebook_goal_targets_profit_bargain(goal):
            target_offer = self._facebook_profitable_offer_price(title=title, ask_price=ask_price)
            if target_offer is not None and ask_price is not None and target_offer < ask_price:
                candidate = self._facebook_bargain_message(item_ref=item_ref, offer_price=target_offer)
                return self._facebook_finalize_marketplace_message(candidate, state=state, goal=goal)
        if item_ref:
            candidate = f"Hey, is your {item_ref} still available?"
            return self._facebook_finalize_marketplace_message(candidate, state=state, goal=goal)
        if self._facebook_listing_detail_visible(state):
            candidate = "Hey, interested in this. Still available?"
            return self._facebook_finalize_marketplace_message(candidate, state=state, goal=goal)
        return candidate

    def _facebook_default_thread_reply(self, thread: dict[str, Any]) -> str | None:
        inbound = str(thread.get("last_inbound_message") or "").strip()
        item_ref = self._facebook_message_item_reference(thread.get("item_title"))
        lowered = inbound.casefold()
        ask_price = self._coerce_price(thread.get("price"))
        target_offer = self._facebook_profitable_offer_price(title=thread.get("item_title"), ask_price=ask_price)
        outbound = str(thread.get("last_outbound_message") or "").strip().casefold()
        if not inbound:
            return None
        if "pickup only" in lowered:
            return "Hey, what’s the pickup address or nearest cross streets?"
        if any(token in lowered for token in ["don't have a car", "dont have a car", "can't meet", "cant meet", "cannot meet"]):
            return "Where are you located?"
        if "available" in lowered or lowered in {"yes", "yep", "still available", "it js", "it is"}:
            if target_offer is not None and "$" not in outbound:
                return self._facebook_direct_counter_message(offer_price=target_offer)
            return "Can we meet in Bothell?"
        if "$" in lowered or any(token in lowered for token in ["can do", "could do", "lowest", "best price"]):
            return "Can we meet in Bothell?"
        if "where" in lowered and ("meet" in lowered or "pickup" in lowered):
            return "Bothell works best for me."
        return "Where are you located?"

    def _facebook_skill_guided_message(self, *, goal: str, state: ScreenState, skill: SkillBundle) -> str | None:
        if self.provider == "gemini" and not self.api_key:
            return None
        if self.provider == "lmstudio" and not (self.lmstudio_base_url and self.model):
            return None
        title = self._facebook_listing_title(state) or ""
        price = self._facebook_listing_price(state)
        visible = [text for text in state.visible_text[:20] if text]
        prompt = (
            "Draft one short human Facebook Marketplace buyer message.\n"
            "Use the app skill instructions as the policy source.\n"
            "Do not paste the full listing title. Use a short natural item reference.\n"
            "If the ask is too high for a profitable flip, make a direct offer first.\n"
            "If specs or condition are still unclear, ask about them instead of guessing.\n"
            "After price agreement, default to asking 'Can we meet in Bothell?' before asking for location details.\n"
            "Use one concrete offer number when bargaining. Avoid robotic phrasing and avoid 'pick it up today' unless timing is already established.\n"
            "Keep it to one sentence, plain text only, under 22 words, no quotes, no extra commentary.\n\n"
            f"Goal:\n{goal}\n\n"
            f"Skill instructions:\n{skill.instructions[:5000]}\n\n"
            f"Listing title:\n{title or '(unknown)'}\n\n"
            f"Visible price:\n{price if price is not None else '(unknown)'}\n\n"
            f"Visible screen text:\n{json.dumps(visible, ensure_ascii=True)}\n"
        )
        if self.provider == "lmstudio":
            raw = self._lmstudio_text_message(prompt)
        else:
            raw = self._gemini_text_message(prompt)
        return self._facebook_finalize_marketplace_message(raw, state=state, goal=goal)

    def _facebook_skill_guided_thread_reply(
        self,
        *,
        goal: str,
        state: ScreenState,
        skill: SkillBundle,
        thread: dict[str, Any] | None,
    ) -> str | None:
        if thread is None:
            return None
        if self.provider == "gemini" and not self.api_key:
            return None
        if self.provider == "lmstudio" and not (self.lmstudio_base_url and self.model):
            return None
        visible = [text for text in state.visible_text[:20] if text]
        prompt = (
            "Draft one short human Facebook Marketplace seller reply.\n"
            "Use the app skill instructions as the policy source.\n"
            "Keep it to one sentence, plain text only, under 22 words, no quotes.\n"
            "Do not paste the full listing title. Use a short natural item reference.\n"
            "If the seller confirmed availability, continue with a direct counteroffer or 'Can we meet in Bothell?' according to the skill.\n"
            "If they say pickup only, ask for the address or nearest cross streets.\n\n"
            f"Goal:\n{goal}\n\n"
            f"Skill instructions:\n{skill.instructions[:5000]}\n\n"
            f"Thread title:\n{thread.get('thread_title') or '(unknown)'}\n\n"
            f"Item title:\n{thread.get('item_title') or '(unknown)'}\n\n"
            f"Latest outbound:\n{thread.get('last_outbound_message') or '(none)'}\n\n"
            f"Latest inbound:\n{thread.get('last_inbound_message') or '(none)'}\n\n"
            f"Visible thread text:\n{json.dumps(visible, ensure_ascii=True)}\n"
        )
        if self.provider == "lmstudio":
            raw = self._lmstudio_text_message(prompt)
        else:
            raw = self._gemini_text_message(prompt)
        cleaned = self._facebook_clean_message(raw)
        return cleaned if cleaned else self._facebook_default_thread_reply(thread)

    def _facebook_should_check_inbox(
        self,
        *,
        goal: str,
        skill: SkillBundle,
        action_history: list[dict[str, Any]],
    ) -> bool:
        if not self._facebook_goal_allows_marketplace_messaging(goal):
            return False
        marketplace_backup = skill.backup_data.get("facebook_marketplace", {})
        if not marketplace_backup.get("threads") and not marketplace_backup.get("contacted_items"):
            return False
        recent = action_history[-8:]
        recently_sent = any(
            str(item.get("target_label") or "").casefold() == "send"
            or (str(item.get("action") or "").casefold() == "tap" and "send" in str(item.get("reason") or "").casefold())
            for item in recent
        )
        if not recently_sent:
            return False
        return not any(
            str(item.get("screen_classification") or "") in {
                "facebook_message_inbox",
                "facebook_marketplace_inbox",
                "facebook_message_thread",
            }
            for item in recent
        )

    def _gemini_text_message(self, prompt: str) -> str | None:
        request = urllib.request.Request(
            url=(
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model}:generateContent?key={self.api_key}"
            ),
            data=json.dumps(
                {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.3},
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None
        text = self._extract_text(raw).strip()
        text = re.sub(r"\s+", " ", text).strip().strip('"').strip("'")
        return text or None

    def _lmstudio_text_message(self, prompt: str) -> str | None:
        headers = {"Content-Type": "application/json"}
        if self.lmstudio_api_key:
            headers["Authorization"] = f"Bearer {self.lmstudio_api_key}"
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "stream": True,
        }
        request = urllib.request.Request(
            url=f"{self.lmstudio_base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=min(self.lmstudio_timeout_seconds, 30)) as response:
                raw = self._read_lmstudio_response(response)
        except Exception:
            return None
        text = self._extract_lmstudio_text(raw).strip()
        text = re.sub(r"\s+", " ", text).strip().strip('"').strip("'")
        return text or None

    @staticmethod
    def _facebook_bargain_message(*, item_ref: str | None, offer_price: int) -> str:
        if item_ref:
            return f"Hey, if it's in good shape, would you take ${offer_price} for your {item_ref}? Thanks"
        return f"Hey, if it's in good shape, would you take ${offer_price}? Thanks"

    @staticmethod
    def _facebook_direct_counter_message(*, offer_price: int) -> str:
        return f"Can you do ${offer_price}? Thanks"

    def _facebook_finalize_marketplace_message(
        self,
        candidate: str | None,
        *,
        state: ScreenState,
        goal: str | None,
        allow_default_fallback: bool = True,
    ) -> str | None:
        cleaned = self._facebook_clean_message(candidate)
        if self._facebook_message_quality_ok(cleaned, state=state):
            return cleaned
        if not allow_default_fallback:
            return cleaned
        title = self._facebook_listing_title(state)
        item_ref = self._facebook_message_item_reference(title)
        ask_price = self._facebook_listing_price(state)
        missing_details = self._facebook_missing_listing_details(state)
        if missing_details:
            fallback = self._facebook_clean_message(
                self._facebook_missing_details_message(item_ref=item_ref, missing_details=missing_details)
            )
            if self._facebook_message_quality_ok(fallback, state=state):
                return fallback
        if goal and self._facebook_goal_targets_profit_bargain(goal):
            target_offer = self._facebook_profitable_offer_price(title=title, ask_price=ask_price)
            if target_offer is not None:
                fallback = self._facebook_bargain_message(item_ref=item_ref, offer_price=target_offer)
                fallback = self._facebook_clean_message(fallback)
                if self._facebook_message_quality_ok(fallback, state=state):
                    return fallback
        if item_ref:
            fallback = self._facebook_clean_message(f"Hey, is your {item_ref} still available?")
            if self._facebook_message_quality_ok(fallback, state=state):
                return fallback
        fallback = self._facebook_clean_message("Hey, interested in this. Still available?")
        return fallback if self._facebook_message_quality_ok(fallback, state=state) else None

    @staticmethod
    def _facebook_clean_message(message: str | None) -> str | None:
        if not message:
            return None
        cleaned = re.sub(r"\s+", " ", str(message)).strip().strip('"').strip("'")
        if not cleaned:
            return None
        cleaned = VisionAgent._facebook_normalize_message_casing(cleaned)
        return cleaned or None

    @staticmethod
    def _facebook_normalize_message_casing(message: str) -> str:
        needs_normalization = any(
            pattern.search(message)
            for pattern in (
                re.compile(r"[A-Z]{4,}"),
                re.compile(r"\b[a-z]+[A-Z][a-z]+\b"),
                re.compile(r"\b[A-Z][a-z]+[A-Z]+\b"),
            )
        )
        if not needs_normalization:
            return message

        normalized = message.lower()
        replacements = {
            r"\biphone\b": "iPhone",
            r"\bipad\b": "iPad",
            r"\bimac\b": "iMac",
            r"\bmacbook\b": "MacBook",
            r"\bmac mini\b": "Mac mini",
            r"\bmac studio\b": "Mac Studio",
            r"\bair\b": "Air",
            r"\bpro\b": "Pro",
            r"\bram\b": "RAM",
            r"\bssd\b": "SSD",
            r"\bgpu\b": "GPU",
            r"\bcpu\b": "CPU",
            r"\brtc\b": "RTC",
            r"\brtx\b": "RTX",
            r"\bgtx\b": "GTX",
            r"\boled\b": "OLED",
            r"\buhd\b": "UHD",
            r"\bpc\b": "PC",
            r"\bm1\b": "M1",
            r"\bm2\b": "M2",
            r"\bm3\b": "M3",
            r"\bm4\b": "M4",
        }
        for pattern, replacement in replacements.items():
            normalized = re.sub(pattern, replacement, normalized)
        normalized = normalized[:1].upper() + normalized[1:] if normalized else normalized
        normalized = re.sub(r"(?<=\?\s)thanks\b", "Thanks", normalized, flags=re.IGNORECASE)
        return normalized

    def _facebook_message_quality_ok(self, message: str | None, *, state: ScreenState) -> bool:
        if not message:
            return False
        lowered = message.casefold().strip()
        if lowered in {"hi, is this available?", "hello, is this still available?", "is this still available?"}:
            return False
        if any(
            token in lowered
            for token in [
                "pick up today",
                "pickup today",
                "pick it up today",
                "pick this up today",
                "i can pick up",
                "i can pick this up",
                "meet up today",
            ]
        ):
            return False
        if len(lowered.split()) < 3:
            return False
        if len(lowered) < 10:
            return False
        title = (self._facebook_listing_title(state) or "").strip()
        title_lower = title.casefold()
        if title_lower and lowered == title_lower:
            return False
        item_ref = (self._facebook_message_item_reference(title) or "").casefold()
        if item_ref and lowered in {item_ref, f"hey, {item_ref}", f"hi, {item_ref}"}:
            return False
        if title_lower and lowered in title_lower:
            return False
        if lowered.replace("$", "").strip() in {"i7", "m1", "m2", "m3", "m4", "rtx", "ryzen"}:
            return False
        if len(lowered) > 90:
            return False
        return True

    @staticmethod
    def _coerce_price(value: Any) -> int | None:
        if value is None:
            return None
        text = str(value)
        match = re.search(r"\$?([\d,]+)", text)
        if not match:
            return None
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            return None

    def _facebook_missing_listing_details(self, state: ScreenState) -> list[str]:
        missing: list[str] = []
        if not self._facebook_listing_has_visible_specs(state):
            missing.append("specs")
        if not self._facebook_listing_has_visible_condition(state) and not self._facebook_product_image_visible(state):
            missing.append("condition")
        return missing

    @staticmethod
    def _facebook_missing_details_message(*, item_ref: str | None, missing_details: list[str]) -> str:
        target = item_ref or "the item"
        if missing_details == ["specs"]:
            return f"Hey, can you share the full specs for your {target}?"
        if missing_details == ["condition"]:
            return f"Hey, what kind of condition is your {target} in? Any scratches, dents, or issues?"
        return f"Hey, can you share the specs and current condition for your {target}?"

    def _facebook_message_item_reference(self, title: str | None) -> str | None:
        if not title:
            return None
        compact = re.sub(r"\s+", " ", title).strip().rstrip(" .")
        lowered = compact.casefold()

        if any(token in lowered for token in ["gaming pc", " rx ", " rtx", " ryzen ", " intel i", "[full pc]", "full pc"]):
            return "gaming PC"
        if "motherboard combo" in lowered:
            return "motherboard combo"

        patterns = [
            r"(iphone\s+\d{1,2}(?:\s+(?:pro\s+max|pro|max|plus|mini))?)",
            r"(ipad(?:\s+pro|\s+air|\s+mini)?(?:\s+\d{1,2}(?:\.\d)?(?:-inch|\"))?)",
            r"(macbook\s+(?:air|pro)(?:\s+m[1-4](?:\s+(?:pro|max))?)?)",
            r"(imac(?:\s+\d{1,2}(?:\"|-inch))?)",
            r"(mac\s+mini)",
            r"(mac\s+studio)",
            r"(surface\s+laptop(?:\s+\d+)?)",
            r"(alienware\s+m\d+\s+r\d+)",
            r"(hp\s+omen(?:\s+max)?\s+\d+)",
            r"(rtx\s*\d{3,4}\s+gaming\s+pc)",
            r"(motherboard\s+combo)",
            r"(monitor(?:\s+\d{1,2}(?:\"|-inch))?)",
            r"(sony\s+lens)",
            r"(canon\s+rf\s+\d+mm(?:\s+f\/[\d.]+)?)",
            r"(camera)",
        ]
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if match:
                return self._facebook_title_case_reference(match.group(1))

        split = re.split(r"\s+[|/]|[|/]| – | — | - ", compact, maxsplit=1)[0].strip()
        words = split.split()
        if len(words) > 5:
            split = " ".join(words[:5])
        if split:
            return split
        return compact

    @staticmethod
    def _facebook_title_case_reference(value: str) -> str:
        small = {"and", "or", "of", "the", "for"}
        parts = re.split(r"(\s+)", value)
        out: list[str] = []
        for part in parts:
            if not part or part.isspace():
                out.append(part)
                continue
            lowered = part.casefold()
            if lowered in {"iphone", "ipad", "imac"}:
                out.append(part[0].lower() + part[1:] if part.startswith("i") else part.capitalize())
            elif lowered == "macbook":
                out.append("MacBook")
            elif lowered == "air":
                out.append("Air")
            elif lowered == "pro":
                out.append("Pro")
            elif lowered == "macbookpro":
                out.append("MacBook Pro")
            elif lowered == "macbookair":
                out.append("MacBook Air")
            elif lowered == "rf":
                out.append("RF")
            elif lowered == "rtx":
                out.append("RTX")
            elif lowered in {"m1", "m2", "m3", "m4"}:
                out.append(lowered.upper())
            elif lowered == "pc":
                out.append("PC")
            elif any(char.isdigit() for char in part):
                out.append(part.upper() if part.isalpha() and len(part) <= 3 else part)
            elif lowered in small:
                out.append(lowered)
            else:
                out.append(part.capitalize())
        return "".join(out)

    @staticmethod
    def _facebook_listing_price(state: ScreenState) -> int | None:
        for item in state.visible_text[:30]:
            text = str(item).strip()
            match = re.search(r"\$([\d,]+(?:\.\d+)?)", text)
            if not match:
                continue
            try:
                return int(round(float(match.group(1).replace(",", ""))))
            except ValueError:
                continue
        return None

    def _facebook_profitable_offer_price(self, *, title: str | None, ask_price: int | None) -> int | None:
        if not title or ask_price is None:
            return None
        lowered = title.casefold().replace("-", " ")
        compact = re.sub(r"\s+", " ", lowered)
        specific_rules: list[tuple[tuple[str, ...], int]] = [
            (("macbook air", "m1", "8gb", "256gb"), 230),
            (("macbook air", "m2", "8gb", "256gb"), 325),
            (("macbook air", "m2", "13", "16gb", "256gb"), 425),
            (("macbook air", "m2", "13-inch", "16gb", "256gb"), 425),
        ]
        for tokens, ceiling in specific_rules:
            if all(token in compact for token in tokens):
                return ceiling if ask_price > ceiling else None

        category_rules: list[tuple[tuple[str, ...], int, float]] = [
            (("macbook air", "macbook pro"), 300, 0.58),
            (("iphone",), 250, 0.58),
            (("imac", "mac mini"), 300, 0.62),
            (("rtx", "gaming pc", "gaming laptop", "laptop"), 350, 0.60),
            (("camera", "canon", "sony", "nikon", "lens"), 400, 0.65),
            (("monitor", "oled", "ultrawide"), 200, 0.55),
        ]
        for tokens, min_ask, ratio in category_rules:
            if ask_price < min_ask or not any(token in compact for token in tokens):
                continue
            candidate = self._round_offer_price(ask_price * ratio)
            if candidate <= ask_price - 50:
                return candidate
        return None

    @staticmethod
    def _facebook_listing_has_visible_specs(state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:40]).casefold()
        if any(token in text for token in ["macbook", "imac", "mac mini", "mac studio"]):
            capacity_matches = re.findall(r"\b\d{1,4}\s?gb\b|\b\d(?:\.\d+)?\s?tb\b", text)
            return len(capacity_matches) >= 2
        spec_patterns = [
            r"\b\d{1,3}\s?gb\b",
            r"\b\d(?:\.\d+)?\s?(?:tb|inch|in)\b",
            r"\bm[1-4]\b",
            r"\brtx\s?\d{3,4}\b",
            r"\bi(?:phone|pad|mac)\b",
            r"\ba7\s?(?:ii|iii|iv|v)\b",
            r"\b35mm\b",
            r"\bf/[\d.]+\b",
        ]
        return any(re.search(pattern, text) for pattern in spec_patterns)

    @staticmethod
    def _facebook_listing_has_visible_condition(state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:40]).casefold()
        return any(
            token in text
            for token in [
                "like new",
                "excellent condition",
                "good condition",
                "fair condition",
                "mint condition",
                "flawless",
                "clean",
                "pristine",
                "no scratches",
                "no issues",
                "works perfectly",
                "scratches",
                "dent",
                "crack",
                "damage",
                "used",
            ]
        )

    @staticmethod
    def _facebook_product_image_visible(state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:40]).casefold()
        return "product image" in text or re.search(r"\bphoto\s+\d+\s+of\s+\d+\b", text) is not None

    @staticmethod
    def _round_offer_price(value: float) -> int:
        return max(25, int(round(value / 25.0) * 25))

    def _facebook_listing_title(self, state: ScreenState) -> str | None:
        ignored_exact = {
            "close",
            "navigate to search",
            "more actions",
            "like",
            "save",
            "share",
            "message seller",
            "send",
            "description",
            "seller",
            "seller \ufffc",
        }
        ignored_substrings = (
            "product image",
            "is this available",
            "still available",
            "loading conversation",
            "message sent to seller",
            "see more",
            "see less",
            "buy now",
            "send offer",
            "listed ",
            "location:",
        )
        for item in state.visible_text[:30]:
            text = str(item).strip()
            lowered = text.casefold()
            if not text or lowered in ignored_exact:
                continue
            if any(token in lowered for token in ignored_substrings):
                continue
            if text.startswith("$") or re.fullmatch(r"\$?[\d,]+(?:\.\d+)?", text):
                continue
            if len(text) < 6:
                continue
            return text.rstrip(" .")
        return None
