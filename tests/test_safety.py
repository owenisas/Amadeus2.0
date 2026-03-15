from pathlib import Path

from agent_runner.models import AppConfig, BoundingBox, DeviceInfo, ScreenState, VisionDecision
from agent_runner.safety import detect_manual_login_required, evaluate_decision


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
