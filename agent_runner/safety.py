from __future__ import annotations

from agent_runner.models import AppConfig, SafetyVerdict, ScreenState, VisionDecision


DEFAULT_BLOCKED_TOKENS = [
    "buy",
    "order",
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


def evaluate_decision(
    app: AppConfig, state: ScreenState, decision: VisionDecision
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
    screen_text = " ".join(state.visible_text[:60]).casefold()
    combined = " ".join([decision_text, screen_text])

    if app.name == "playstore":
        for token in PLAYSTORE_PURCHASE_TOKENS:
            if token.casefold() in combined:
                return SafetyVerdict(False, f"Blocked Play Store purchase token '{token}'.")

    blocked_tokens = DEFAULT_BLOCKED_TOKENS + app.blocked_keywords + app.high_risk_signatures
    for token in blocked_tokens:
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
