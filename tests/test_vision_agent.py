from pathlib import Path

from agent_runner.config import APP_REGISTRY
from agent_runner.models import DeviceInfo, ScreenState
from agent_runner.skill_manager import SkillManager
from agent_runner.vision_agent import VisionAgent


def make_playstore_state(*, visible_text: list[str], clickable_text: list[str], components: list[dict]) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.android.vending",
        activity_name=".AssetBrowserActivity",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=visible_text,
        clickable_text=clickable_text,
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=components,
    )


def make_amazon_state(*, visible_text: list[str], clickable_text: list[str], components: list[dict]) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.amazon.mShop.android.shopping",
        activity_name=".OrdersActivity",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=visible_text,
        clickable_text=clickable_text,
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=components,
    )


def make_gmail_state(
    *,
    visible_text: list[str],
    clickable_text: list[str],
    components: list[dict],
    xml_source: str = "<hierarchy />",
) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.google.android.gm",
        activity_name=".ConversationListActivityGmail",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source=xml_source,
        visible_text=visible_text,
        clickable_text=clickable_text,
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=components,
    )


def test_playstore_interstitial_is_dismissed(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["playstore"])
    state = make_playstore_state(
        visible_text=["以后再说", "加入"],
        clickable_text=["以后再说", "加入"],
        components=[
            {
                "component_type": "touch_target",
                "label": "以后再说",
                "enabled": False,
                "search_related": False,
                "target_box": {"x": 0.05, "y": 0.9, "width": 0.4, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(goal="open the Play Store and stop only when the search field is visible", state=state, skill=bundle, action_history=[])

    assert decision.next_action == "tap"
    assert decision.target_label == "以后再说"


def test_playstore_search_query_types_and_submits(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["playstore"])
    state = make_playstore_state(
        visible_text=["搜索应用和游戏"],
        clickable_text=[],
        components=[
            {
                "component_type": "text_input",
                "label": "搜索应用和游戏",
                "enabled": True,
                "focused": True,
                "search_related": True,
                "target_box": {"x": 0.1, "y": 0.05, "width": 0.8, "height": 0.08},
            }
        ],
    )

    decision = agent.decide(goal="search for maps", state=state, skill=bundle, action_history=[])

    assert decision.next_action == "type"
    assert decision.input_text == "maps"
    assert decision.submit_after_input is True


def test_playstore_install_goal_opens_matching_result(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["playstore"])
    state = make_playstore_state(
        visible_text=["2048 game", "Number Charm: 2048 Games"],
        clickable_text=["Number Charm: 2048 Games\nHDuo Fun Games"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Number Charm: 2048 Games\nHDuo Fun Games",
                "enabled": True,
                "focused": False,
                "search_related": False,
                "target_box": {"x": 0.05, "y": 0.22, "width": 0.76, "height": 0.07},
            }
        ],
    )

    decision = agent.decide(
        goal="install Number Charm: 2048 Games from Play Store",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Number Charm" in (decision.target_label or "")


def test_playstore_install_progress_waits(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["playstore"])
    state = make_playstore_state(
        visible_text=["Number Charm: 2048 Games", "等待中...", "取消", "11% (共 8.60 MB)"],
        clickable_text=["取消"],
        components=[],
    )

    decision = agent.decide(
        goal="install Number Charm: 2048 Games from Play Store",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "wait"


def test_goal_requesting_screenshot_uses_capture_tool(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["playstore"])
    state = make_playstore_state(
        visible_text=["Play Store"],
        clickable_text=[],
        components=[],
    )

    decision = agent.decide(
        goal="capture a screenshot of the current Play Store screen",
        state=state,
        skill=bundle,
        action_history=[],
        available_tools=[{"name": "capture_state", "description": "Capture state"}],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "capture_state"


def test_amazon_orders_stops_when_no_target_box_can_be_resolved(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["amazon"])
    state = make_amazon_state(
        visible_text=["Your Orders"],
        clickable_text=["Your Orders"],
        components=[],
    )

    decision = agent.decide(
        goal="check delivery status for my latest order",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert "no stable target box" in decision.reason


def test_amazon_orders_uses_component_target_box_without_selector(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["amazon"])
    state = make_amazon_state(
        visible_text=["Your Orders"],
        clickable_text=["Your Orders"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Your Orders",
                "enabled": True,
                "focused": False,
                "search_related": False,
                "target_box": {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1},
            }
        ],
    )

    decision = agent.decide(
        goal="check delivery status for my latest order",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_box is not None
    assert decision.target_box.to_dict() == {"x": 0.1, "y": 0.2, "width": 0.5, "height": 0.1}


def test_gmail_inbox_scrolls_once_then_stops(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["gmail"])
    state = make_gmail_state(
        visible_text=["Inbox", "Primary", "Social"],
        clickable_text=["Primary", "Social"],
        components=[],
    )

    first = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
    )
    second = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[{"action": "swipe"}],
    )

    assert first.next_action == "swipe"
    assert second.next_action == "stop"


def test_gmail_welcome_requires_user_approval(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["gmail"])
    state = make_gmail_state(
        visible_text=["Gmail 换新颜", "知道了"],
        clickable_text=["知道了"],
        components=[
            {
                "component_type": "touch_target",
                "label": "知道了",
                "resource_id": "com.google.android.gm:id/welcome_tour_got_it",
                "enabled": True,
                "search_related": False,
                "target_box": {"x": 0.0, "y": 0.93, "width": 1.0, "height": 0.06},
            }
        ],
        xml_source='<hierarchy><node resource-id="com.google.android.gm:id/welcome_tour_got_it" /></hierarchy>',
    )

    decision = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert decision.requires_user_approval is True


def test_gmail_setup_addresses_requires_user_approval(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["gmail"])
    state = make_gmail_state(
        visible_text=["现在，您可以添加您所有的电子邮件地址。了解详情", "转至 GMAIL"],
        clickable_text=["转至 GMAIL"],
        components=[
            {
                "component_type": "touch_target",
                "label": "转至 GMAIL",
                "resource_id": "com.google.android.gm:id/action_done",
                "enabled": True,
                "search_related": False,
                "target_box": {"x": 0.0, "y": 0.91, "width": 1.0, "height": 0.06},
            }
        ],
        xml_source='<hierarchy><node resource-id="com.google.android.gm:id/setup_addresses_fragment" /></hierarchy>',
    )

    decision = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert decision.requires_user_approval is True


def test_gmail_notification_permission_requires_user_approval(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["gmail"])
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.google.android.permissioncontroller",
        activity_name="com.android.permissioncontroller.permission.ui.GrantPermissionsActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["要允许“Gmail”向您发送通知吗？", "允许", "不允许"],
        clickable_text=["允许", "不允许"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "button",
                "label": "不允许",
                "enabled": True,
                "search_related": False,
                "target_box": {"x": 0.12, "y": 0.56, "width": 0.75, "height": 0.06},
            }
        ],
    )

    decision = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert decision.requires_user_approval is True


def test_gmail_meet_overlay_requires_user_approval(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["gmail"])
    state = make_gmail_state(
        visible_text=["关闭", "Google Meet 现在可以在 Gmail 中直接使用", "知道了"],
        clickable_text=["关闭", "知道了"],
        components=[
            {
                "component_type": "button",
                "label": "关闭",
                "resource_id": "com.google.android.gm:id/dismiss_button",
                "enabled": True,
                "search_related": False,
                "target_box": {"x": 0.8, "y": 0.42, "width": 0.12, "height": 0.07},
            }
        ],
        xml_source='<hierarchy><node resource-id="com.google.android.gm:id/dialog_wrapper" pane-title="Google Meet" /></hierarchy>',
    )

    decision = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert decision.requires_user_approval is True
