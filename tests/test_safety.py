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


def facebook_app() -> AppConfig:
    return AppConfig(
        name="facebook",
        package_name="com.facebook.katana",
        launch_activity=".activity.FbMainTabActivity",
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["buy now", "message seller", "send"],
        high_risk_signatures=["buy now", "checkout"],
        manual_login_tokens=["log in", "login", "password", "verification", "checkpoint", "code"],
        default_goal_hint="inspect marketplace",
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


def test_facebook_email_confirmation_overlay_is_recoverable() -> None:
    state = make_state(
        visible_text=[
            "You're One Click Away From Confirming user@example.com",
            "Confirm Email",
            "Add Another Email",
            "Close",
            "What's on your mind?",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".LoginActivity"

    reason = detect_manual_intervention_reason(facebook_app(), state, yolo_mode=True)

    assert reason is None


def test_facebook_logged_in_feed_is_not_treated_as_manual_login_required() -> None:
    state = make_state(
        visible_text=[
            "Go to profile",
            "What's on your mind?",
            "Stories",
            "Messaging",
            "Marketplace, tab 4 of 6",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".LoginActivity"

    assert detect_manual_login_required(facebook_app(), state) is False


def test_facebook_listing_with_windows_code_text_is_not_treated_as_manual_login_required() -> None:
    state = make_state(
        visible_text=[
            "Close",
            "Product Image,1 of 4",
            "High end gaming pc, RTX 5080 intel ultra 9 285k",
            "$2,000",
            "Message seller",
            "Hi, is this available?",
            "Description",
            "It does need a new windows code to activate windows, doesn't affect anything.",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    assert detect_manual_login_required(facebook_app(), state) is False


def test_facebook_description_expander_with_factory_reset_text_is_allowed() -> None:
    verdict = evaluate_decision(
        facebook_app(),
        make_state(
            visible_text=[
                "Nintendo Switch OLED in White",
                "Description",
                "Well kept Nintendo Switch OLED Screen for sale. Comes with all original parts. Factory reset.",
                "See more",
            ]
        ),
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="reading_description",
            next_action="tap",
            target_box=BoundingBox(0.03, 0.90, 0.18, 0.02),
            confidence=0.9,
            reason="Expand the listing description before deciding whether to message the seller.",
            risk_level="low",
            target_label="Well kept Nintendo Switch OLED Screen for sale. Comes with all original parts. Factory reset. | See more",
        ),
        goal="Open Facebook Marketplace, inspect listings, read the description, and send a buyer message only after reviewing details.",
    )

    assert verdict.allowed is True


def test_facebook_listing_payment_text_does_not_block_message_focus() -> None:
    verdict = evaluate_decision(
        facebook_app(),
        make_state(
            visible_text=[
                "Close",
                "Product Image,1 of 3",
                "Lenovo G34w 34\" Ultrawide Curved Gaming Monitor",
                "$160",
                "Hi, is this available?",
                "Send",
                "Cash or Venmo. Local pickup only — no shipping, no holding without payment.",
            ]
        ),
        VisionDecision(
            screen_classification="marketplace_listing_detail",
            goal_progress="Expanded listing details to read the description. The item is a Lenovo G34w monitor for $160, local pickup, cash/Venmo, broken stand but VESA compatible. It's a good deal. Proceeding to draft a custom buyer message.",
            next_action="tap",
            target_box=BoundingBox(0.06, 0.77, 0.70, 0.04),
            confidence=0.95,
            reason="Tapping the message input field to focus it so we can type a custom buyer message.",
            risk_level="low",
            target_label="Hi, is this available?",
        ),
        goal="Resume the Facebook Marketplace hunting workflow. Inspect valuable local resale listings and send short human buyer messages when profitable.",
    )

    assert verdict.allowed is True


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


def test_tool_type_action_accepts_input_text_alias() -> None:
    app = amazon_app()
    app.allowed_actions.append("tool")
    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Enter year"]),
        VisionDecision(
            screen_classification="qualification",
            goal_progress="typing",
            next_action="tool",
            target_box=None,
            confidence=0.1,
            reason="",
            risk_level="low",
            tool_name="type",
            tool_arguments={"input_text": "1990", "submit_after_input": False},
        ),
    )

    assert verdict.allowed is True


def test_tool_type_submit_flag_name_does_not_trigger_submit_risk_token() -> None:
    app = AppConfig(
        name="surveyapp",
        package_name="com.example.survey",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=["submit"],
        high_risk_signatures=[],
        manual_login_tokens=[],
        default_goal_hint="fill a form",
    )

    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Enter year"]),
        VisionDecision(
            screen_classification="qualification",
            goal_progress="typing",
            next_action="tool",
            target_box=None,
            confidence=0.1,
            reason="",
            risk_level="low",
            tool_name="type",
            tool_arguments={"input_text": "1985", "submit_after_input": False},
        ),
    )

    assert verdict.allowed is True


def test_run_fast_function_tool_is_allowed() -> None:
    app = facebook_app()

    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Description", "See more"]),
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="inspecting_listing",
            next_action="tool",
            target_box=None,
            confidence=0.9,
            reason="Use the fast function to expand listing details before drafting a seller message.",
            risk_level="low",
            tool_name="run_fast_function",
            tool_arguments={
                "app_name": "facebook",
                "function_name": "expand_listing_details",
                "arguments": {},
            },
        ),
        goal="Resume the Facebook Marketplace hunting workflow and continue scanning listings.",
    )

    assert verdict.allowed is True


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


def test_facebook_listing_tap_is_not_blocked_by_purchase_word_in_reason() -> None:
    state = make_state(
        visible_text=[
            "Just listed, $200 · Dell UltraSharp 27\" Monitor + Razer RGB Gaming Keyboard",
            "Location: Bothell, WA",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".LoginActivity"

    verdict = evaluate_decision(
        facebook_app(),
        state,
        VisionDecision(
            screen_classification="Marketplace Feed",
            goal_progress="Inspecting a potentially profitable listing.",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.2, 0.3, 0.2),
            confidence=0.95,
            reason="Tap the listing to inspect it and determine if it's a profitable purchase.",
            risk_level="low",
            target_label='Just listed, $200 · Dell UltraSharp 27" Monitor + Razer RGB Gaming Keyboard',
        ),
        goal="Inspect valuable Marketplace listings and send messages when profitable.",
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


def test_high_risk_surface_allows_safe_navigation_target_tap() -> None:
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
    state = make_state(visible_text=["Message seller", "Navigate to Search", "Share"])
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="opening_search",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.1, 0.2, 0.1),
            confidence=0.9,
            reason="Open Marketplace search from the current listing detail.",
            risk_level="low",
            target_label="Navigate to Search",
        ),
    )

    assert verdict.allowed is True


def test_buy_now_surface_allows_safe_description_expander_tap() -> None:
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
    state = make_state(
        visible_text=[
            "Apple MacBook Air Space Gray",
            "$450",
            "Buy now",
            "Payments are processed securely",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="inspecting_listing",
            next_action="tap",
            target_box=BoundingBox(0.03, 0.9, 0.94, 0.07),
            confidence=0.95,
            reason="Expand the description so the listing can be inspected read-only.",
            risk_level="low",
            target_label="See more",
        ),
    )

    assert verdict.allowed is True


def test_buy_now_surface_allows_read_only_swipe_inspection() -> None:
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
    state = make_state(
        visible_text=[
            "Apple MacBook Air Space Gray",
            "$450",
            "Buy now",
            "Payments are processed securely",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="inspecting_listing",
            next_action="swipe",
            target_box=None,
            confidence=1.0,
            reason="Scroll down to inspect seller-visible details on the listing read-only.",
            risk_level="low",
        ),
    )

    assert verdict.allowed is True


def test_buy_now_surface_allows_read_only_tool_swipe_inspection() -> None:
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
    state = make_state(
        visible_text=[
            "Apple MacBook Air Space Gray",
            "$450",
            "Buy now",
            "Payments are processed securely",
        ]
    )
    state.package_name = "com.facebook.katana"
    state.activity_name = ".activity.react.ImmersiveReactActivity"

    verdict = evaluate_decision(
        facebook,
        state,
        VisionDecision(
            screen_classification="listing_detail",
            goal_progress="inspecting_listing",
            next_action="tool",
            target_box=None,
            confidence=1.0,
            reason="Scroll down to inspect seller-visible details on the listing read-only.",
            risk_level="low",
            tool_name="swipe",
            tool_arguments={"direction": "up"},
        ),
    )

    assert verdict.allowed is True


def test_low_confidence_structurally_valid_tap_is_allowed() -> None:
    verdict = evaluate_decision(
        amazon_app(),
        make_state(visible_text=["Settings", "Network & internet"]),
        VisionDecision(
            screen_classification="settings_home",
            goal_progress="navigating",
            next_action="tap",
            target_box=BoundingBox(0.1, 0.2, 0.3, 0.1),
            confidence=0.0,
            reason="Open Network & internet.",
            risk_level="low",
            target_label="Network & internet",
        ),
    )

    assert verdict.allowed is True


def test_unknown_tool_action_is_rejected() -> None:
    app = AppConfig(
        name="settings",
        package_name="com.android.settings",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[],
        high_risk_signatures=[],
        manual_login_tokens=[],
        default_goal_hint="inspect settings",
    )

    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Settings"]),
        VisionDecision.tool(
            tool_name="definitely_not_a_real_tool",
            tool_arguments={},
            reason="Do something invalid.",
            confidence=0.0,
        ),
    )

    assert verdict.allowed is False
    assert "unknown tool action" in verdict.reason.casefold()


def test_tool_tap_requires_target_box_argument() -> None:
    app = AppConfig(
        name="settings",
        package_name="com.android.settings",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[],
        high_risk_signatures=[],
        manual_login_tokens=[],
        default_goal_hint="inspect settings",
    )

    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Settings"]),
        VisionDecision.tool(
            tool_name="tap",
            tool_arguments={},
            reason="Tap the settings row.",
            confidence=0.0,
        ),
    )

    assert verdict.allowed is False
    assert "target_box" in verdict.reason


def test_tool_tap_requires_valid_target_box_shape() -> None:
    app = AppConfig(
        name="settings",
        package_name="com.android.settings",
        launch_activity=None,
        allowed_actions=["tap", "back", "home", "wait", "swipe", "type", "tool", "stop"],
        blocked_keywords=[],
        high_risk_signatures=[],
        manual_login_tokens=[],
        default_goal_hint="inspect settings",
    )

    verdict = evaluate_decision(
        app,
        make_state(visible_text=["Settings"]),
        VisionDecision.tool(
            tool_name="tap",
            tool_arguments={"target_box": {"x": 0.5, "y": 0.5}},
            reason="Tap the settings row.",
            confidence=0.0,
        ),
    )

    assert verdict.allowed is False
    assert "valid" in verdict.reason.casefold()
