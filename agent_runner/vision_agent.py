from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from agent_runner.models import BoundingBox, ScreenState, SkillBundle, VisionDecision


class VisionAgent:
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

    def __init__(self, api_key: str | None, model: str) -> None:
        self.api_key = api_key
        self.model = model

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
        heuristic = self._heuristic_decision(
            goal=goal,
            state=state,
            skill=skill,
            system_instruction=system_instruction,
            action_history=action_history,
            available_tools=available_tools or [],
            yolo_mode=yolo_mode,
        )
        if self._should_bypass_model(state, heuristic, yolo_mode=yolo_mode):
            return heuristic
        if not self.api_key:
            return heuristic
        decision = self._gemini_decision(
            goal=goal,
            state=state,
            skill=skill,
            system_instruction=system_instruction,
            action_history=action_history,
            available_tools=available_tools or [],
            yolo_mode=yolo_mode,
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
            with urllib.request.urlopen(request, timeout=60) as response:
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
            return fallback
        return self._coerce_decision(decision_payload)

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
            listing_message_goal = self._facebook_goal_targets_listing_message(goal)
            reply_text = self._extract_message_text(goal)
            send_requested = self._facebook_send_requested(goal)
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
            if messaging_goal:
                message_input = self._find_facebook_message_input(components)
                send_button = self._find_facebook_send_button(components)
                if message_input and reply_text and not any(item.get("action") == "type" for item in action_history[-2:]):
                    return VisionDecision(
                        screen_classification="facebook_message_composer",
                        goal_progress="drafting_reply",
                        next_action="type",
                        target_box=BoundingBox.from_dict(message_input.get("target_box")),
                        confidence=0.86,
                        reason="Type the requested Facebook message into the current reply field.",
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
                if self._facebook_message_inbox_visible(state) and listing_message_goal:
                    return VisionDecision(
                        screen_classification="facebook_message_inbox",
                        goal_progress="recovering_to_marketplace",
                        next_action="back",
                        target_box=None,
                        confidence=0.8,
                        reason="Back out of the generic Facebook inbox and return to Marketplace listing flow.",
                        risk_level="low",
                    )
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
                    if listing_message_goal:
                        return self._tap_decision_for_label(
                            state=state,
                            skill=skill,
                            label="Marketplace, tab 4 of 6",
                            screen_classification="facebook_home_feed",
                            goal_progress="navigating_to_marketplace",
                            confidence=0.86,
                            reason="Seller-message goals should enter Marketplace first before opening any message thread.",
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
                    return VisionDecision.stop("Facebook message thread is visible for reading or replying.")
                if self._facebook_message_inbox_visible(state):
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
            if self._facebook_listing_detail_visible(state):
                return VisionDecision(
                    screen_classification="facebook_listing_detail",
                    goal_progress="continuing_scan",
                    next_action="back",
                    target_box=None,
                    confidence=0.91,
                    reason="Back out of the Marketplace listing detail after inspection and continue scanning the feed.",
                    risk_level="low",
                )
            if self._facebook_marketplace_feed_visible(state):
                if action_history and action_history[-1].get("action") == "back":
                    return VisionDecision(
                        screen_classification="facebook_marketplace_feed",
                        goal_progress="advancing_feed",
                        next_action="swipe",
                        target_box=None,
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
                        target_box=None,
                        confidence=0.74,
                        reason="Scroll the Marketplace feed to inspect additional local listings.",
                        risk_level="low",
                    )
                return VisionDecision.stop("Facebook Marketplace feed has been scanned and no stronger next listing heuristic was found.")
            if self._facebook_home_shell_visible(state):
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
        screen_text = " ".join(state.visible_text[:12]).casefold()
        for selector in skill.selectors.get("selectors", []):
            if selector.get("label", "").casefold() == label.casefold():
                if selector.get("package_name") not in {None, "", state.package_name}:
                    continue
                if selector.get("activity_name") not in {None, "", state.activity_name}:
                    continue
                anchor_text = selector.get("anchor_text") or []
                if anchor_text and not any(str(anchor).casefold() in screen_text for anchor in anchor_text):
                    continue
                return BoundingBox.from_dict(selector.get("target_box"))
        return None

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

    def _coerce_decision(self, payload: dict[str, Any]) -> VisionDecision:
        box = BoundingBox.from_dict(payload.get("target_box"))
        raw_action = str(payload.get("next_action", "stop")).strip().lower().replace(" ", "_")
        next_action = self.ACTION_ALIASES.get(raw_action, raw_action)
        tool_arguments = self._parse_tool_arguments(payload.get("tool_arguments_json"))
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
            target_label=payload.get("target_label"),
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
        state: ScreenState,
        heuristic: VisionDecision,
        *,
        yolo_mode: bool,
    ) -> bool:
        if heuristic.requires_user_approval:
            return True
        if yolo_mode and heuristic.next_action == "stop" and "manual login required" in heuristic.reason.casefold():
            return False
        # Only bypass when the heuristic has a concrete, high-confidence action
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
            token in text
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

    def _auto_approval_popup_decision(
        self,
        *,
        state: ScreenState,
        skill: SkillBundle,
        summary: str,
    ) -> VisionDecision | None:
        for tokens in (self.YOLO_PRIMARY_ACTION_TOKENS, self.YOLO_SECONDARY_ACTION_TOKENS):
            for token in tokens:
                for component in state.components[:20]:
                    label = str(component.get("label", "")).strip()
                    if not label or component.get("enabled") is False:
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
            for token in ["message seller", "contact seller", "send offer", "hello, is this still available?"]
        )

    def _facebook_marketplace_feed_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return "marketplace" in text and any(
            token in text for token in ["for you", "local", "location:", "what do you want to buy?"]
        )

    def _facebook_home_feed_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        clickable = " ".join(state.clickable_text[:30]).casefold()
        return "what's on your mind?" in text and "messaging" in clickable

    def _facebook_home_shell_visible(self, state: ScreenState) -> bool:
        clickable = " ".join(state.clickable_text[:20]).casefold()
        return "marketplace, tab 4 of 6" in clickable and not self._facebook_marketplace_feed_visible(state)

    def _facebook_message_recovery_prompt_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return "are you sure?" in text and "end-to-end encrypted messages" in text

    def _facebook_message_thread_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return any(token in text for token in ["type a message", "write a message", "reply"]) and "send" in text

    def _facebook_message_inbox_visible(self, state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:60]).casefold()
        return any(token in text for token in ["messenger", "messages", "chats", "search messenger"])

    def _find_facebook_message_input(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        for component in components:
            if component.get("component_type") != "text_input":
                continue
            label = str(component.get("label", "")).casefold()
            if any(token in label for token in ["still available", "type a message", "write a message", "reply"]):
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

    def _find_facebook_listing_component(self, components: list[dict[str, Any]]) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        for component in components:
            label = str(component.get("label", ""))
            lowered = label.casefold()
            if not label.strip():
                continue
            if component.get("enabled") is False:
                continue
            if component.get("component_type") not in {"touch_target", "button"}:
                continue
            if component.get("resource_id") == "mp_top_picks_clickable_item":
                return component
            if "just listed" in lowered or "$" in label or "£" in label:
                best = component
        return best

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
            for token in ["seller", "listing", "item", "still available", "send", "reply", "respond"]
        )

    def _facebook_send_requested(self, goal: str) -> bool:
        lowered = goal.casefold()
        return any(token in lowered for token in ["send", "reply", "respond"])

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
            if message:
                return message
        return None
