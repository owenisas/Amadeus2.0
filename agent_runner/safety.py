from __future__ import annotations

from agent_runner.models import AppConfig, BoundingBox, SafetyVerdict, ScreenState, VisionDecision


DEFAULT_BLOCKED_TOKENS = [
    "purchase",
    "payment",
    "pay now",
    "delete",
    "factory reset",
    "erase all data",
]

PLAYSTORE_PURCHASE_TOKENS = [
    "buy",
    "purchase",
    "subscribe",
    "price",
    "paid",
    "付费",
    "购买",
    "订阅",
    "$",
    "usd",
    "hk$",
]

SAFE_ESCAPE_ACTIONS = {"back", "home", "stop", "wait"}
SAFE_ESCAPE_TOOLS = {"reset_app", "launch_app", "capture_state", "list_scripts", "read_skill"}
SAFE_READONLY_ACTIONS = {"swipe"}
SAFE_NAVIGATION_TARGET_TOKENS = {
    "search",
    "navigate",
    "close",
    "dismiss",
    "menu",
    "home",
    "local",
    "for you",
    "jobs",
    "categories",
    "back",
    "see more",
    "read more",
    "description",
    "details",
}
KNOWN_TOOL_ACTIONS = {
    "capture_state",
    "launch_app",
    "reset_app",
    "tap",
    "type",
    "swipe",
    "back",
    "home",
    "wait",
    "adb_shell",
    "read_skill",
    "write_skill_file",
    "bootstrap_skill",
    "save_script",
    "run_script",
    "run_fast_function",
    "list_scripts",
}
GENERIC_ACCOUNT_RESTRICTION_TOKENS = [
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
    "we've limited",
    "we have limited",
    "confirm your account",
    "appeal this decision",
]


def evaluate_decision(
    app: AppConfig, state: ScreenState, decision: VisionDecision, *, goal: str | None = None
) -> SafetyVerdict:
    if decision.next_action == "stop":
        return SafetyVerdict(True, "Stop actions are always allowed.")
    if decision.next_action == "tap" and decision.target_box is None:
        return SafetyVerdict(False, "Tap actions require a target_box.")
    if decision.next_action == "type" and not decision.input_text:
        return SafetyVerdict(False, "Type actions require input_text.")
    if decision.next_action == "tool" and not decision.tool_name:
        return SafetyVerdict(False, "Tool actions require a tool_name.")
    if decision.next_action == "tool":
        tool_name = (decision.tool_name or "").casefold()
        if tool_name not in KNOWN_TOOL_ACTIONS:
            return SafetyVerdict(False, f"Unknown tool action '{decision.tool_name}'.")
        if tool_name == "tap":
            tool_box = BoundingBox.from_dict(decision.tool_arguments.get("target_box"))
            if tool_box is None:
                return SafetyVerdict(False, "Tool tap actions require a valid tool_arguments.target_box.")
        if tool_name == "type" and not (
            decision.tool_arguments.get("text") or decision.tool_arguments.get("input_text")
        ):
            return SafetyVerdict(False, "Tool type actions require tool_arguments.text or tool_arguments.input_text.")

    if decision.next_action not in app.allowed_actions:
        return SafetyVerdict(False, f"Action '{decision.next_action}' is not allowed for {app.name}.")

    tool_argument_text = " ".join(_flatten_tool_argument_values(decision.tool_arguments))
    reason_text = (decision.reason or "").casefold()
    action_payload_text = " ".join(
        filter(
            None,
            [
                decision.target_label,
                decision.input_text,
                decision.tool_name,
                tool_argument_text,
            ],
        )
    ).casefold()
    action_text = " ".join(
        filter(
            None,
            [
                action_payload_text,
                decision.screen_classification,
                decision.goal_progress,
            ],
        )
    ).casefold()
    decision_text = " ".join(
        filter(
            None,
            [
                reason_text,
                action_text,
            ],
        )
    ).strip()
    screen_text = "" if decision.screen_classification == "approval_surface" else " ".join(state.visible_text[:60]).casefold()
    combined = " ".join([decision_text, screen_text]).strip()

    if app.name == "playstore":
        for token in PLAYSTORE_PURCHASE_TOKENS:
            if token.casefold() in combined:
                return SafetyVerdict(False, f"Blocked Play Store purchase token '{token}'.")

    for token in DEFAULT_BLOCKED_TOKENS:
        if token.casefold() not in action_payload_text:
            continue
        if _is_safe_navigation_target(decision):
            continue
        return SafetyVerdict(False, f"Blocked by risk token '{token}'.")

    blocked_keywords = app.blocked_keywords
    high_risk_signatures = app.high_risk_signatures
    if app.name == "facebook" and _facebook_goal_allows_marketplace_messaging(goal):
        messaging_tokens = {"contact seller", "message seller", "send"}
        blocked_keywords = [token for token in blocked_keywords if token.casefold() not in messaging_tokens]
        high_risk_signatures = [token for token in high_risk_signatures if token.casefold() not in messaging_tokens]

    for token in blocked_keywords:
        if token.casefold() in decision_text:
            return SafetyVerdict(False, f"Blocked by risk token '{token}'.")

    if _is_safe_escape(decision):
        return SafetyVerdict(True, "Escape action allowed on high-risk surface.")
    if _is_safe_readonly_action(decision):
        return SafetyVerdict(True, "Read-only navigation action allowed on high-risk surface.")

    for token in high_risk_signatures:
        token_lower = token.casefold()
        if token_lower in decision_text:
            return SafetyVerdict(False, f"Blocked by risk token '{token}'.")
        if token_lower in screen_text and not _is_safe_navigation_target(decision):
            return SafetyVerdict(False, f"Blocked by risk token '{token}'.")

    if decision.risk_level.casefold() in {"high", "critical"}:
        return SafetyVerdict(False, f"Blocked by model risk level '{decision.risk_level}'.")

    return SafetyVerdict(True, "Decision passed local safety checks.")


def detect_manual_login_required(app: AppConfig, state: ScreenState) -> bool:
    if app.name == "facebook":
        return _facebook_login_prompt_visible(state)
    text = " ".join(state.visible_text[:80]).casefold()
    return any(token.casefold() in text for token in app.manual_login_tokens)


def detect_manual_intervention_reason(
    app: AppConfig,
    state: ScreenState,
    *,
    yolo_mode: bool = False,
) -> str | None:
    restriction_reason = detect_account_restriction_reason(state)
    if restriction_reason:
        return restriction_reason
    if app.name == "facebook" and _facebook_recoverable_confirmation_visible(state):
        return None
    if detect_manual_login_required(app, state):
        return "Manual login required before automation can continue."
    return None


def detect_account_restriction_reason(state: ScreenState) -> str | None:
    text = " ".join(state.visible_text[:100]).casefold()
    if not text:
        return None
    if ("confirm your identity" in text or "verify your identity" in text) and (
        "unusual activity" in text or "limited" in text or "restriction" in text
    ):
        return "Manual account verification required before automation can continue."
    if any(token in text for token in ["try again tomorrow", "limited the number", "we've limited", "we have limited"]):
        return "Account rate limit or contact restriction detected before automation can continue."
    if any(token in text for token in GENERIC_ACCOUNT_RESTRICTION_TOKENS):
        return "Account restriction or verification is required before automation can continue."
    return None


def _is_safe_escape(decision: VisionDecision) -> bool:
    if decision.next_action in SAFE_ESCAPE_ACTIONS:
        return True
    if decision.next_action != "tool":
        return False
    return (decision.tool_name or "").casefold() in SAFE_ESCAPE_TOOLS


def _is_safe_readonly_action(decision: VisionDecision) -> bool:
    if decision.risk_level.casefold() in {"high", "critical"}:
        return False
    if decision.next_action in SAFE_READONLY_ACTIONS:
        return True
    return decision.next_action == "tool" and (decision.tool_name or "").casefold() in SAFE_READONLY_ACTIONS


def _facebook_goal_allows_marketplace_messaging(goal: str | None) -> bool:
    if not goal:
        return False
    lowered = goal.casefold()
    return "marketplace" in lowered and any(
        token in lowered
        for token in ["message ", "messages", "reply", "respond", "conversation", "chat", "inbox", "seller"]
    )


def _facebook_logged_in_home_visible(state: ScreenState) -> bool:
    text = " ".join(state.visible_text[:40]).casefold()
    if "log in" in text or "password" in text or "checkpoint" in text:
        return False
    return any(
        token in text
        for token in [
            "what's on your mind?",
            "stories",
            "create story",
            "marketplace, tab 4 of 6",
            "messaging",
            "reels, tab 2 of 6",
        ]
    )


def _facebook_logged_in_surface_visible(state: ScreenState) -> bool:
    text = " ".join(state.visible_text[:80]).casefold()
    clickable = " ".join(state.clickable_text[:40]).casefold()
    if _facebook_logged_in_home_visible(state):
        return True
    return any(
        token in text or token in clickable
        for token in [
            "marketplace inbox",
            "view marketplace profile",
            "tap to view your marketplace account",
            "product image",
            "message seller",
            "see conversation",
            "you started this chat",
            "rate seller",
            "close navigate to search",
        ]
    )


def _facebook_login_prompt_visible(state: ScreenState) -> bool:
    if _facebook_logged_in_surface_visible(state):
        return False
    text = " ".join(state.visible_text[:80]).casefold()
    explicit_tokens = ["log in", "login", "password", "checkpoint", "enter password", "forgot password"]
    if any(token in text for token in explicit_tokens):
        return True
    return any(
        token in text
        for token in [
            "verification code",
            "enter code",
            "confirmation code",
            "enter the code",
        ]
    )


def _is_safe_navigation_target(decision: VisionDecision) -> bool:
    if decision.next_action == "tap":
        label = (decision.target_label or "").casefold()
        return any(token in label for token in SAFE_NAVIGATION_TARGET_TOKENS)
    if decision.next_action == "tool" and (decision.tool_name or "").casefold() == "tap":
        label = str(decision.tool_arguments.get("target_label") or "").casefold()
        return any(token in label for token in SAFE_NAVIGATION_TARGET_TOKENS)
    return False


def _flatten_tool_argument_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        flattened: list[str] = []
        for nested in value.values():
            flattened.extend(_flatten_tool_argument_values(nested))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened: list[str] = []
        for nested in value:
            flattened.extend(_flatten_tool_argument_values(nested))
        return flattened
    if isinstance(value, bool):
        return [str(value).casefold()]
    return [str(value)]


def _facebook_recoverable_confirmation_visible(state: ScreenState) -> bool:
    text_items = [item.casefold() for item in state.visible_text[:60]]
    clickable_items = [item.casefold() for item in state.clickable_text[:30]]
    text = " ".join(text_items)
    clickable = " ".join(clickable_items)
    return (
        "confirm email" in text
        and "add another email" in text
        and "close" in clickable
        and "what's on your mind?" in text
    )
