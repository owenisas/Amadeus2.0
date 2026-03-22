from __future__ import annotations

from agent_runner.models import AppConfig, SafetyVerdict, ScreenState, VisionDecision


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

    if decision.next_action not in app.allowed_actions:
        return SafetyVerdict(False, f"Action '{decision.next_action}' is not allowed for {app.name}.")

    decision_text = " ".join(
        filter(
            None,
            [
                decision.reason,
                decision.target_label,
                decision.input_text,
                decision.screen_classification,
                decision.goal_progress,
                decision.tool_name,
                " ".join(f"{key}={value}" for key, value in sorted(decision.tool_arguments.items())),
            ],
        )
    ).casefold()
    screen_text = "" if decision.screen_classification == "approval_surface" else " ".join(state.visible_text[:60]).casefold()
    combined = " ".join([decision_text, screen_text]).strip()

    if app.name == "playstore":
        for token in PLAYSTORE_PURCHASE_TOKENS:
            if token.casefold() in combined:
                return SafetyVerdict(False, f"Blocked Play Store purchase token '{token}'.")

    for token in DEFAULT_BLOCKED_TOKENS:
        if token.casefold() in decision_text:
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

    for token in high_risk_signatures:
        if token.casefold() in combined:
            return SafetyVerdict(False, f"Blocked by risk token '{token}'.")

    if decision.risk_level.casefold() in {"high", "critical"}:
        return SafetyVerdict(False, f"Blocked by model risk level '{decision.risk_level}'.")

    if decision.confidence < 0.30:
        return SafetyVerdict(False, "Decision confidence below 0.30.")

    return SafetyVerdict(True, "Decision passed local safety checks.")


def detect_manual_login_required(app: AppConfig, state: ScreenState) -> bool:
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


def _facebook_goal_allows_marketplace_messaging(goal: str | None) -> bool:
    if not goal:
        return False
    lowered = goal.casefold()
    return "marketplace" in lowered and any(
        token in lowered
        for token in ["message ", "messages", "reply", "respond", "conversation", "chat", "inbox", "seller"]
    )
