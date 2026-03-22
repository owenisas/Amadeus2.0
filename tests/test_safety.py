from pathlib import Path

from agent_runner.models import AppConfig, BoundingBox, DeviceInfo, ScreenState, VisionDecision
from agent_runner.safety import detect_account_restriction_reason, detect_manual_intervention_reason, detect_manual_login_required, evaluate_decision


def make_state(*, visible_text: list[str]) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.amazon.mShop.android.shopping",
        activity_name=".MainActivity",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=visible_text,
        clickable_text=visible_text,
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
    )


def amazon_app() -> AppConfig:
    return AppConfig(
        name="amazon",
        package_name="com.amazon.mShop.android.shopping",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "stop"],
        blocked_keywords=["buy now", "place your order"],
        high_risk_signatures=["payment method"],
        manual_login_tokens=["sign in", "password"],
        default_goal_hint="check status",
    )


def test_blocked_keyword_is_rejected() -> None:
    verdict = evaluate_decision(
        amazon_app(),
        make_state(visible_text=["Buy now"]),
        VisionDecision(
            screen_classification="checkout",
            goal_progress="wrong_page",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            confidence=0.8,
            reason="Tap Buy now button.",
            risk_level="low",
        ),
    )
    assert verdict.allowed is False
    assert "Blocked" in verdict.reason


def test_login_required_detection() -> None:
    state = make_state(visible_text=["Sign in", "Enter password"])
    assert detect_manual_login_required(amazon_app(), state) is True


def test_account_restriction_reason_detection() -> None:
    state = make_state(
        visible_text=[
            "Confirm Your Identity on Marketplace",
            "We detected unusual activity on your account",
            "You can try again tomorrow.",
        ]
    )

    reason = detect_account_restriction_reason(state)

    assert reason is not None
    assert "verification" in reason.casefold() or "restriction" in reason.casefold()


def test_manual_intervention_reason_prefers_restriction_even_in_yolo_mode() -> None:
    state = make_state(
        visible_text=[
            "Confirm Your Identity on Marketplace",
            "We detected unusual activity on your account",
            "We've limited the number of sellers you can contact.",
        ]
    )

    reason = detect_manual_intervention_reason(amazon_app(), state, yolo_mode=True)

    assert reason is not None
    assert "automation can continue" in reason.casefold()


def test_manual_intervention_reason_still_blocks_login_in_yolo_mode() -> None:
    state = make_state(visible_text=["Sign in", "Enter password", "Continue"])

    reason = detect_manual_intervention_reason(amazon_app(), state, yolo_mode=True)

    assert reason == "Manual login required before automation can continue."


def test_type_action_without_input_text_is_rejected() -> None:
    verdict = evaluate_decision(
        amazon_app(),
        make_state(visible_text=["Search"]),
        VisionDecision(
            screen_classification="search",
            goal_progress="typing",
            next_action="type",
            target_box=None,
            confidence=0.8,
            reason="Type into the search box.",
            risk_level="low",
            input_text=None,
        ),
    )

    assert verdict.allowed is False
    assert "input_text" in verdict.reason


def test_playstore_install_allowed_for_free_app() -> None:
    playstore = AppConfig(
        name="playstore",
        package_name="com.android.vending",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "stop"],
        blocked_keywords=["buy", "purchase", "subscribe"],
        high_risk_signatures=["purchase", "subscribe"],
        manual_login_tokens=[],
        default_goal_hint="install free app",
    )
    state = make_state(visible_text=["安装", "在更多设备上安装"])
    state.package_name = "com.android.vending"
    state.activity_name = ".AssetBrowserActivity"

    verdict = evaluate_decision(
        playstore,
        state,
        VisionDecision(
            screen_classification="playstore_detail",
            goal_progress="starting_install",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            confidence=0.9,
            reason="Tap the Play Store install button for the requested free app or game.",
            risk_level="low",
            target_label="安装 | 在更多设备上安装",
        ),
    )

    assert verdict.allowed is True


def test_generic_purchase_text_on_screen_does_not_block_read_only_decision() -> None:
    facebook = AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "stop"],
        blocked_keywords=["buy now", "message seller"],
        high_risk_signatures=["buy now", "message seller"],
        manual_login_tokens=[],
        default_goal_hint="inspect marketplace",
    )
    state = make_state(
        visible_text=[
            "Great condition monitor",
            "If you purchase the monitor with my pc you get 30 dollars off.",
            "Share",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="inspecting",
            next_action="back",
            target_box=None,
            confidence=0.91,
            reason="Back out after finishing the read-only listing inspection.",
            risk_level="low",
        ),
    )

    assert verdict.allowed is True


def test_high_risk_surface_allows_safe_escape_action() -> None:
    facebook = AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["buy now", "message seller"],
        high_risk_signatures=["buy now", "message seller"],
        manual_login_tokens=[],
        default_goal_hint="inspect marketplace",
    )
    state = make_state(visible_text=["Message seller", "Send offer", "Share"])
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="backing_out",
            next_action="back",
            target_box=None,
            confidence=0.9,
            reason="Leave the seller-contact surface and return to the main Marketplace feed.",
            risk_level="low",
        ),
    )

    assert verdict.allowed is True


def test_high_risk_surface_blocks_risky_action() -> None:
    facebook = AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["buy now", "message seller"],
        high_risk_signatures=["buy now", "message seller"],
        manual_login_tokens=[],
        default_goal_hint="inspect marketplace",
    )
    state = make_state(visible_text=["Message seller", "Send offer", "Share"])
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="acting",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.2, 0.3, 0.1),
            confidence=0.9,
            reason="Tap Message seller to contact the seller.",
            risk_level="low",
            target_label="Message seller",
        ),
    )

    assert verdict.allowed is False
    assert "message seller" in verdict.reason.casefold()


def test_facebook_send_allowed_when_goal_explicitly_requests_reply() -> None:
    facebook = AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["buy now", "message seller", "send"],
        high_risk_signatures=["buy now", "message seller", "send"],
        manual_login_tokens=[],
        default_goal_hint="reply to messages",
    )
    state = make_state(visible_text=["Message seller", "Send"])
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="facebook_message_composer",
            goal_progress="sending_reply",
            next_action="tap",
            target_box=BoundingBox(0.7, 0.7, 0.1, 0.05),
            confidence=0.9,
            reason="Send the explicitly requested Facebook reply.",
            risk_level="low",
            target_label="Send",
        ),
        goal="Reply to the marketplace seller with 'Yes, I can pick it up today.'",
    )

    assert verdict.allowed is True


def test_facebook_send_stays_blocked_without_marketplace_goal() -> None:
    facebook = AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["buy now", "message seller", "send"],
        high_risk_signatures=["buy now", "message seller", "send"],
        manual_login_tokens=[],
        default_goal_hint="reply to messages",
    )
    state = make_state(visible_text=["Message seller", "Send"])
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="facebook_message_composer",
            goal_progress="sending_reply",
            next_action="tap",
            target_box=BoundingBox(0.7, 0.7, 0.1, 0.05),
            confidence=0.9,
            reason="Send the explicitly requested Facebook reply.",
            risk_level="low",
            target_label="Send",
        ),
        goal="Reply to the seller with 'Yes, I can pick it up today.'",
    )

    assert verdict.allowed is False
