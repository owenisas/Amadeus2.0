import json
import io
import socket
from pathlib import Path
import urllib.error

from agent_runner.config import APP_REGISTRY
from agent_runner.models import BoundingBox, DeviceInfo, ScreenState, VisionDecision
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


def make_facebook_state(
    *,
    activity_name: str,
    visible_text: list[str],
    clickable_text: list[str],
    components: list[dict],
) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.facebook.katana",
        activity_name=activity_name,
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


def make_facebook_marketplace_inbox_state() -> ScreenState:
    return make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Marketplace Seller Inbox",
            "Selling",
            "Marketplace Buyer Inbox",
            "Buying",
            "All",
            "Pending Offers",
            "Accepted Offers",
            "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
            "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
        ],
        clickable_text=[
            "Marketplace Seller Inbox",
            "Marketplace Buyer Inbox",
            "All",
            "Pending Offers",
            "Accepted Offers",
            "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
            "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
        ],
        components=[
            {
                "component_type": "button",
                "label": "Marketplace Seller Inbox",
                "enabled": True,
                "target_box": {"x": 0.26, "y": 0.12, "width": 0.45, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Marketplace Buyer Inbox",
                "enabled": True,
                "target_box": {"x": 0.74, "y": 0.12, "width": 0.45, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Accepted Offers",
                "enabled": True,
                "target_box": {"x": 0.48, "y": 0.19, "width": 0.18, "height": 0.04},
            },
            {
                "component_type": "touch_target",
                "label": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "enabled": True,
                "target_box": {"x": 0.56, "y": 0.41, "width": 0.62, "height": 0.08},
            },
            {
                "component_type": "touch_target",
                "label": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
                "enabled": True,
                "target_box": {"x": 0.56, "y": 0.46, "width": 0.62, "height": 0.05},
            },
        ],
    )


def make_facebook_marketplace_inbox_without_backup_match_state() -> ScreenState:
    return make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Marketplace Seller Inbox",
            "Selling",
            "Marketplace Buyer Inbox",
            "Buying",
            "All",
            "Pending Offers",
            "Accepted Offers",
            "Pending Door Drop Plans",
            "Ariel · iphone 15 pro",
            "Ariel sold iphone 15 pro.",
        ],
        clickable_text=[
            "Marketplace Seller Inbox",
            "Marketplace Buyer Inbox",
            "All",
            "Pending Offers",
            "Accepted Offers",
            "Pending Door Drop Plans",
            "Ariel · iphone 15 pro",
            "Ariel sold iphone 15 pro.",
            "Get help on Marketplace",
        ],
        components=[
            {
                "component_type": "button",
                "label": "Marketplace Seller Inbox",
                "enabled": True,
                "target_box": {"x": 0.26, "y": 0.12, "width": 0.45, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Marketplace Buyer Inbox",
                "enabled": True,
                "target_box": {"x": 0.74, "y": 0.12, "width": 0.45, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Accepted Offers",
                "enabled": True,
                "target_box": {"x": 0.48, "y": 0.19, "width": 0.18, "height": 0.04},
            },
            {
                "component_type": "touch_target",
                "label": "Ariel · iphone 15 pro",
                "enabled": True,
                "target_box": {"x": 0.56, "y": 0.41, "width": 0.62, "height": 0.08},
            },
            {
                "component_type": "touch_target",
                "label": "Ariel sold iphone 15 pro.",
                "enabled": True,
                "target_box": {"x": 0.56, "y": 0.46, "width": 0.62, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Get help on Marketplace",
                "enabled": True,
                "target_box": {"x": 0.88, "y": 0.06, "width": 0.12, "height": 0.05},
            },
        ],
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


def test_selector_lookup_prefers_matching_screen_and_anchor_text(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    bundle.selectors["selectors"] = [
        {
            "screen_id": "com-android-settings-settings-correct",
            "label": "Continue",
            "target_box": {"x": 0.42, "y": 0.92, "width": 0.14, "height": 0.06},
            "activity_name": ".Settings",
            "package_name": "com.android.settings",
            "anchor_text": ["Enter your birthday", "Qualification"],
        },
        {
            "screen_id": "com-android-settings-settings-wrong",
            "label": "Continue",
            "target_box": {"x": 0.05, "y": 0.2, "width": 0.2, "height": 0.05},
            "activity_name": ".Settings",
            "package_name": "com.android.settings",
            "anchor_text": ["Battery", "Storage"],
        },
    ]
    state = make_amazon_state(
        visible_text=["Qualification", "Enter your birthday", "January", "15"],
        clickable_text=["Continue"],
        components=[{"label": "Continue", "component_type": "button", "target_box": {"x": 0.42, "y": 0.92, "width": 0.14, "height": 0.06}}],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"

    result = agent._lookup_selector_box(bundle, state, "Continue")

    assert result is not None
    assert round(result.x, 2) == 0.42


def test_model_decision_hydrates_missing_target_box_from_current_screen(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Marketplace",
            "Just listed, $500 · Samsung M8 Smart Monitor",
        ],
        clickable_text=["Just listed, $500 · Samsung M8 Smart Monitor"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Just listed, $500 · Samsung M8 Smart Monitor",
                "enabled": True,
                "target_box": {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26},
            }
        ],
    )

    decision = agent._coerce_decision(
        {
            "screen_classification": "facebook_marketplace_feed",
            "goal_progress": "opening_listing",
            "next_action": "tap",
            "target_box": None,
            "confidence": 0.95,
            "reason": "Open the high-value listing.",
            "risk_level": "low",
            "target_label": "Just listed, $500 · Samsung M8 Smart Monitor",
        },
        state=state,
        skill=bundle,
    )

    assert decision.next_action == "tap"
    assert decision.target_box is not None
    assert decision.target_box.to_dict() == {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26}


def test_facebook_marketplace_search_goal_opens_search_from_feed(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Marketplace",
            "Sell",
            "For you, Tab, 1 of 3",
            "Local, Tab, 2 of 3",
            "What do you want to buy?",
        ],
        clickable_text=["Sell", "For you", "Local", "What do you want to buy?"],
        components=[
            {
                "component_type": "button",
                "label": "What do you want to buy?",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.88, "y": 0.08, "width": 0.11, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Marketplace search and confirm the search surface is visible.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "What do you want to buy?"


def test_facebook_marketplace_search_goal_prefers_search_from_listing_detail(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Message seller",
            "Marketplace",
        ],
        clickable_text=["Close", "Navigate to Search", "More actions", "Message seller"],
        components=[
            {
                "component_type": "button",
                "label": "Navigate to Search",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.14, "y": 0.04, "width": 0.14, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace search for laptops and stop on the search UI.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Navigate to Search"


def test_facebook_marketplace_search_surface_saves_reusable_script_when_requested(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".immersiveactivity.ImmersiveActivity",
        visible_text=[
            "Recent, tab 1 of 2",
            "Recent",
            "Saved searches, tab 2 of 2",
            "Saved searches",
            "Recent searches",
            "rtx 3080",
            "What do you want to buy?",
        ],
        clickable_text=[
            "Recent, tab 1 of 2",
            "Saved searches, tab 2 of 2",
            "rtx 3080",
            "Back",
            "What do you want to buy?",
        ],
        components=[
            {
                "component_type": "text_input",
                "label": "What do you want to buy?",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.15, "y": 0.03, "width": 0.7, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace search, confirm it is visible, save a reusable script only if you discover a new stable path, and stop read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "save_script"
    assert decision.tool_arguments["script_name"] == "open_marketplace_search_surface"


def test_facebook_marketplace_search_surface_stops_when_script_already_exists(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    scripts_dir = bundle.app_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "open_marketplace_search_surface.json").write_text(
        json.dumps({"name": "open_marketplace_search_surface", "description": "", "steps": []}),
        encoding="utf-8",
    )
    state = make_facebook_state(
        activity_name=".immersiveactivity.ImmersiveActivity",
        visible_text=[
            "Recent, tab 1 of 2",
            "Saved searches, tab 2 of 2",
            "Recent searches",
            "What do you want to buy?",
        ],
        clickable_text=["Back", "What do you want to buy?"],
        components=[
            {
                "component_type": "text_input",
                "label": "What do you want to buy?",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.15, "y": 0.03, "width": 0.7, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace search, confirm it is visible, save a reusable script only if you discover a new stable path, and stop read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"


def test_facebook_home_feed_prefers_fast_function_for_marketplace_entry(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    manager.save_fast_function(
        "facebook",
        "open_marketplace_feed",
        {
            "name": "open_marketplace_feed",
            "description": "",
            "script_name": "open_marketplace_direct",
            "preconditions": [{"predicate": "facebook_home_feed_visible"}],
            "postconditions": [{"predicate": "facebook_marketplace_feed_visible"}],
            "fallback_policy": "fallback_to_slow_path",
        },
    )
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=["What's on your mind?", "Home", "Reels", "Marketplace, tab 4 of 6"],
        clickable_text=["Messaging", "Marketplace, tab 4 of 6", "Home, tab 1 of 6"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.03, "width": 0.16, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Resume the Facebook Marketplace hunting workflow and continue scanning listings.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "run_fast_function"
    assert decision.tool_arguments["function_name"] == "open_marketplace_feed"


def test_facebook_reply_mode_uses_send_thread_reply_fast_function(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    manager.save_fast_function(
        "facebook",
        "send_thread_reply",
        {
            "name": "send_thread_reply",
            "description": "",
            "args": [{"name": "message", "required": True}],
            "steps": [{"action": "type", "input_text": "{{message}}"}, {"action": "tap", "target_label": "Send"}],
            "preconditions": [{"predicate": "facebook_message_thread_visible"}],
            "postconditions": [{"predicate": "facebook_thread_reply_sent"}],
            "fallback_policy": "fallback_to_slow_path",
        },
    )
    state = make_facebook_state(
        activity_name=".ThreadActivity",
        visible_text=[
            "Joshua · PC",
            "Marketplace listing",
            "You started this chat.",
            "Joshua, Yes",
            "Message",
            "Send",
        ],
        clickable_text=["Joshua · PC", "Message", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Message",
                "enabled": True,
                "target_box": {"x": 0.1, "y": 0.9, "width": 0.6, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.8, "y": 0.9, "width": 0.15, "height": 0.03},
            },
        ],
    )
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_key": "joshua-pc",
                "thread_title": "Joshua · PC",
                "seller_name": "Joshua",
                "item_title": "PC",
                "last_inbound_message": "Yes",
                "last_outbound_message": "Hi",
                "needs_reply": True,
                "last_updated": "2026-03-27T10:00:00-07:00",
            }
        ],
        "workflow": {
            "mode": "reply",
            "mode_reason": "actionable_seller_replies",
            "reply_queue": [{"thread_key": "joshua-pc", "thread_title": "Joshua · PC"}],
            "active_thread_key": "joshua-pc",
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    bundle.state["facebook_workflow"] = {
        "mode": "reply",
        "mode_reason": "actionable_seller_replies",
        "reply_queue": [{"thread_key": "joshua-pc", "thread_title": "Joshua · PC"}],
        "active_thread_key": "joshua-pc",
        "active_listing_key": None,
        "last_mode_switch_at": None,
        "last_reply_check_at": None,
        "handled_thread_keys": [],
    }

    decision = agent.decide(
        goal="Check Facebook Marketplace replies and send follow-ups using the Facebook skill rules.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.screen_classification == "facebook_message_thread"
    assert decision.next_action in {"tool", "type"}
    if decision.next_action == "tool":
        assert decision.tool_name == "run_fast_function"
        assert decision.tool_arguments["function_name"] == "send_thread_reply"


def test_facebook_home_feed_with_marketplace_tab_is_not_misclassified_as_marketplace_feed(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Go to profile",
            "What's on your mind?",
            "Select photos or videos for your post",
            "Menu",
            "Search",
            "Messaging",
            "Home, tab 1 of 6",
            "Marketplace, tab 4 of 6",
        ],
        clickable_text=[
            "Go to profile",
            "What's on your mind?",
            "Select photos or videos for your post",
            "Menu",
            "Search",
            "Messaging",
            "Home, tab 1 of 6",
            "Marketplace, tab 4 of 6",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.5, "y": 0.08, "width": 0.16, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, open the Marketplace search surface, confirm the search UI is visible, and stop read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Marketplace, tab 4 of 6"


def test_lmstudio_decision_parses_openai_style_json_response(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings", "Network & internet"],
        clickable_text=["Network & internet"],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "screen_classification": "settings_home",
                                        "goal_progress": "navigating",
                                        "next_action": "wait",
                                        "target_box": None,
                                        "confidence": 0.76,
                                        "reason": "Wait for the settings surface to finish rendering.",
                                        "risk_level": "low",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    decision = agent._lmstudio_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action == "wait"
    assert "settings surface" in decision.reason.casefold()


def test_gemini_timeout_falls_back_to_heuristic(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent("fake-api-key", "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings", "Network & internet"],
        clickable_text=["Network & internet"],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"
    state.screenshot_path.write_bytes(b"fake-image")

    def fake_urlopen(*args, **kwargs):
        raise socket.timeout("The read operation timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    decision = agent._gemini_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action == "stop"
    assert "timed out" in decision.reason.casefold()
    assert agent.last_decision_meta["source"] == "gemini_timeout_fallback"


def test_gemini_http_429_falls_back_to_nvidia_model(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        "fake-api-key",
        "gemini-3.1-pro-preview",
        provider="gemini",
        nvidia_api_key="nvidia-key",
        nvidia_model="qwen/qwen3.5-397b-a17b",
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings", "Network & internet"],
        clickable_text=["Network & internet"],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"
    state.screenshot_path.write_bytes(b"fake-image")

    class FakeNvidiaResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "screen_classification": "settings_home",
                                        "goal_progress": "navigating",
                                        "next_action": "wait",
                                        "target_box": None,
                                        "confidence": 0.77,
                                        "reason": "Wait for the Settings screen to settle.",
                                        "risk_level": "low",
                                    }
                                )
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=60):
        if "generativelanguage.googleapis.com" in request.full_url:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"code":429,"message":"quota"}}'),
            )
        assert "integrate.api.nvidia.com" in request.full_url
        return FakeNvidiaResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    decision = agent._gemini_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action == "wait"
    assert agent.last_decision_meta["source"] == "nvidia_fallback_model"
    assert agent.last_decision_meta["provider"] == "nvidia"
    assert agent.last_decision_meta["upstream_source"] == "gemini_http_fallback"


def test_gemini_text_message_falls_back_to_nvidia(monkeypatch) -> None:
    agent = VisionAgent(
        "fake-api-key",
        "gemini-3.1-pro-preview",
        provider="gemini",
        nvidia_api_key="nvidia-key",
        nvidia_model="qwen/qwen3.5-397b-a17b",
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
    )

    class FakeNvidiaResponse:
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Can you do $650? Thanks"
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=60):
        if "generativelanguage.googleapis.com" in request.full_url:
            raise urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                hdrs=None,
                fp=io.BytesIO(b'{"error":{"code":429,"message":"quota"}}'),
            )
        assert "integrate.api.nvidia.com" in request.full_url
        return FakeNvidiaResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert agent._gemini_text_message("draft one short reply") == "Can you do $650? Thanks"


def test_lmstudio_decision_retries_after_http_400_with_text_response_format(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings", "Network & internet"],
        clickable_text=["Network & internet"],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"
    state.screenshot_path.write_bytes(b"fake-image")

    calls: list[dict[str, object]] = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "```json\n"
                                + json.dumps(
                                    {
                                        "screen_classification": "settings_home",
                                        "goal_progress": "navigating",
                                        "next_action": "wait",
                                        "target_box": None,
                                        "confidence": 0.76,
                                        "reason": "Wait for the settings surface to finish rendering.",
                                        "risk_level": "low",
                                    }
                                )
                                + "\n```"
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=60):
        payload = json.loads(request.data.decode("utf-8"))
        calls.append(payload)
        if len(calls) == 1:
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=io.BytesIO(b'{"error":"bad response_format"}'),
            )
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    decision = agent._lmstudio_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert len(calls) == 2
    assert calls[0]["stream"] is True
    assert calls[0]["response_format"]["type"] == "text"
    assert isinstance(calls[0]["messages"][0]["content"], list)
    assert calls[1]["stream"] is True
    assert calls[1]["response_format"]["type"] == "text"
    assert isinstance(calls[1]["messages"][0]["content"], str)
    assert decision.next_action == "wait"


def test_lmstudio_non_json_fallback_records_raw_detail(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings"],
        clickable_text=[],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "I think you should tap the network option next."
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    decision = agent._lmstudio_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action == "tap" or decision.next_action == "stop" or decision.next_action == "wait"
    assert agent.last_decision_meta["source"] == "lmstudio_non_json_fallback"
    assert "tap the network option" in str(agent.last_decision_meta.get("detail", ""))


def test_lmstudio_reasoning_only_fallback_records_reasoning_detail(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".tabbar.TabBarActivity",
        visible_text=["Facebook", "Marketplace", "PlayStation 5", "Sony a6700 Mirrorless Camera Body"],
        clickable_text=["Marketplace", "PlayStation 5", "Sony a6700 Mirrorless Camera Body"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.08, "width": 0.16, "height": 0.05},
            }
        ],
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": (
                                    "The app is already on Marketplace. A promising next step would be to open "
                                    "the Sony a6700 listing and inspect the detail page."
                                ),
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    decision = agent._lmstudio_decision(
        goal="inspect valuable marketplace listings read-only",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action in {"tap", "wait", "stop"}
    assert agent.last_decision_meta["source"] == "lmstudio_reasoning_only_fallback"
    assert "Sony a6700" in str(agent.last_decision_meta.get("detail", ""))


def test_lmstudio_timeout_can_be_overridden_by_env(monkeypatch) -> None:
    monkeypatch.setenv("LMSTUDIO_TIMEOUT_SECONDS", "180")

    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )

    assert agent.lmstudio_timeout_seconds == 180.0


def test_gemini_timeout_can_be_overridden_by_env(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "120")

    agent = VisionAgent(
        "test-key",
        "gemini-3.1-pro-preview",
        provider="gemini",
    )

    assert agent.gemini_timeout_seconds == 120.0


def test_lmstudio_streaming_sse_response_is_parsed(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent(
        None,
        "qwen3.5-35b-a3b-uncensored-hauhaucs-aggressive",
        provider="lmstudio",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["settings"])
    state = make_amazon_state(
        visible_text=["Settings", "Network & internet"],
        clickable_text=["Network & internet"],
        components=[],
    )
    state.package_name = "com.android.settings"
    state.activity_name = ".Settings"

    stream_text = "\n".join(
        [
            'data: {"choices":[{"delta":{"reasoning_content":"Thinking about the Settings screen. "}}]}',
            'data: {"choices":[{"delta":{"content":"{\\"screen_classification\\":\\"settings_home\\",\\"goal_progress\\":\\"navigating\\","}}]}',
            'data: {"choices":[{"delta":{"content":"\\"next_action\\":\\"wait\\",\\"target_box\\":null,\\"confidence\\":0.74,\\"reason\\":\\"Wait for the settings surface to settle.\\",\\"risk_level\\":\\"low\\"}"}}]}',
            "data: [DONE]",
        ]
    )

    class FakeResponse:
        headers = {"Content-Type": "text/event-stream"}

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return stream_text.encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: FakeResponse())

    decision = agent._lmstudio_decision(
        goal="open network settings",
        state=state,
        skill=bundle,
        system_instruction="",
        action_history=[],
        available_tools=[],
        yolo_mode=False,
    )

    assert decision.next_action == "wait"
    assert "settings surface" in decision.reason.casefold()
    assert agent.last_decision_meta["source"] == "lmstudio_model"




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


def test_facebook_stale_listing_detail_resets_to_start_marketplace_from_beginning(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=["Back", "Apple Mac Mini M4 16GB 256GB", "$620", "Message seller", "Send offer"],
        clickable_text=["Back", "Message seller", "Send offer"],
        components=[],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_marketplace_feed_opens_listing(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Location: Bothell, WA",
            "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
            "Marketplace",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
                "enabled": True,
                "resource_id": "mp_top_picks_clickable_item",
                "target_box": {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Surface Laptop" in (decision.target_label or "")


def test_facebook_marketplace_feed_prefers_high_value_listing_over_cheap_accessory(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "$5 · Pixel 9 Pro XL phone case",
            "$1,450 · Powerful Gaming PC — Intel Core Ultra 7 + RTX 5060 Ti — Like New",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "$5 · Pixel 9 Pro XL phone case",
            "$1,450 · Powerful Gaming PC — Intel Core Ultra 7 + RTX 5060 Ti — Like New",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "$5 · Pixel 9 Pro XL phone case",
                "enabled": True,
                "target_box": {"x": 0.0, "y": 0.48, "width": 0.49, "height": 0.25},
            },
            {
                "component_type": "touch_target",
                "label": "$1,450 · Powerful Gaming PC — Intel Core Ultra 7 + RTX 5060 Ti — Like New",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.48, "width": 0.49, "height": 0.25},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Gaming PC" in (decision.target_label or "")


def test_facebook_marketplace_feed_prefers_higher_price_among_similar_monitors(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "Just listed, $120 · Samsung c32hg70 32” monitor",
            "Just listed, $500 · Samsung M8 Smart Monitor",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "Just listed, $120 · Samsung c32hg70 32” monitor",
            "Just listed, $500 · Samsung M8 Smart Monitor",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Just listed, $120 · Samsung c32hg70 32” monitor",
                "enabled": True,
                "resource_id": "mp_top_picks_clickable_item",
                "target_box": {"x": 0.0, "y": 0.23, "width": 0.49, "height": 0.26},
            },
            {
                "component_type": "touch_target",
                "label": "Just listed, $500 · Samsung M8 Smart Monitor",
                "enabled": True,
                "resource_id": "mp_top_picks_clickable_item",
                "target_box": {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Samsung M8 Smart Monitor" in (decision.target_label or "")


def test_facebook_value_scan_goal_does_not_bypass_gemini_on_marketplace_feed(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent("fake-api-key", "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Marketplace",
            "For you",
            "Local",
            "Just listed, $500 · Samsung M8 Smart Monitor",
        ],
        clickable_text=[
            "For you",
            "Local",
            "Just listed, $500 · Samsung M8 Smart Monitor",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Just listed, $500 · Samsung M8 Smart Monitor",
                "enabled": True,
                "target_box": {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26},
            }
        ],
    )

    called = {"gemini": False}

    def fake_gemini_decision(**kwargs):
        called["gemini"] = True
        return agent._coerce_decision(
            {
                "screen_classification": "facebook_marketplace_feed",
                "goal_progress": "opening_listing",
                "next_action": "tap",
                "target_box": None,
                "confidence": 0.95,
                "reason": "Use the Gemini model decision on a value scan goal.",
                "risk_level": "low",
                "target_label": "Just listed, $500 · Samsung M8 Smart Monitor",
            },
            state=kwargs["state"],
            skill=kwargs["skill"],
        )

    monkeypatch.setattr(agent, "_gemini_decision", fake_gemini_decision)

    decision = agent.decide(
        goal="Open Facebook Marketplace and inspect valuable resellable listings read-only, checking images and descriptions.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert called["gemini"] is True
    assert decision.next_action == "tap"
    assert decision.target_box is not None
    assert "Samsung M8" in (decision.target_label or "")


def test_facebook_marketplace_feed_avoids_bulky_tv_when_portable_electronic_exists(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "$65 · Samsung 8 series 55 4K Smart LED TV",
            "$375 · Google Pixel 9 Pro XL fully unlocked",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "$65 · Samsung 8 series 55 4K Smart LED TV",
            "$375 · Google Pixel 9 Pro XL fully unlocked",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "$65 · Samsung 8 series 55 4K Smart LED TV",
                "enabled": True,
                "target_box": {"x": 0.0, "y": 0.48, "width": 0.49, "height": 0.25},
            },
            {
                "component_type": "touch_target",
                "label": "$375 · Google Pixel 9 Pro XL fully unlocked",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.48, "width": 0.49, "height": 0.25},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Pixel 9 Pro XL" in (decision.target_label or "")


def test_facebook_marketplace_feed_avoids_low_margin_budget_gaming_pc(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "$160 · Budget Gaming PC – GTX 770 – 16GB DDR3 – Great for Fortnite & Roblox",
            "$700 · Acer Nitro 5 RTX 4060 16GB RAM",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "$160 · Budget Gaming PC – GTX 770 – 16GB DDR3 – Great for Fortnite & Roblox",
            "$700 · Acer Nitro 5 RTX 4060 16GB RAM",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "$160 · Budget Gaming PC – GTX 770 – 16GB DDR3 – Great for Fortnite & Roblox",
                "enabled": True,
                "target_box": {"x": 0.0, "y": 0.48, "width": 0.49, "height": 0.25},
            },
            {
                "component_type": "touch_target",
                "label": "$700 · Acer Nitro 5 RTX 4060 16GB RAM",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.48, "width": 0.49, "height": 0.25},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "Acer Nitro 5" in (decision.target_label or "")


def test_facebook_clean_start_reset_bypasses_gemini(tmp_path: Path, monkeypatch) -> None:
    agent = VisionAgent("fake-api-key", "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "Product Image,1 of 4",
            "Macbook Air M3",
            "$600",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=[
            "Close",
            "Navigate to Search",
            "Hi, is this available?",
            "Send",
        ],
        components=[],
    )

    called = {"gemini": False}

    def fake_gemini_decision(**kwargs):
        called["gemini"] = True
        raise AssertionError("Gemini should not be called for a clean-start reset.")

    monkeypatch.setattr(agent, "_gemini_decision", fake_gemini_decision)

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and message a promising seller with the right opener.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert called["gemini"] is False
    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_weird_visible_state_resets_when_goal_requests_clean_start(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "Subscribe to Email Alerts",
            "From groups",
        ],
        clickable_text=[
            "Close",
            "Navigate to Search",
            "Subscribe to Email Alerts",
        ],
        components=[],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"
    assert decision.tool_arguments["package_name"] == "com.facebook.katana"


def test_facebook_stale_message_thread_resets_for_marketplace_seller_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name="com.facebook.messaging.msys.thread.fragment.MsysThreadViewActivity",
        visible_text=[
            "Back",
            "Marketplace listing",
            "Additional attachment options",
            "Type a message…",
            "Send",
        ],
        clickable_text=["Back", "Marketplace listing", "Send"],
        components=[],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, inspect valuable resellable listings, and when a promising item is found message the seller.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_listing_message_goal_with_clean_start_resets_stale_listing_detail(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 4",
            "Macbook Air M3",
            "$600",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 4",
            "Hi, is this available?",
            "Send",
        ],
        components=[],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and message a promising seller with the right opener.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_marketplace_feed_swipes_after_returning_from_listing(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Location: Bothell, WA",
            "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
            "Marketplace",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Just listed, $325 · Microsoft Surface Laptop 5 16GB 512GB SSD Fantastic Condition.",
                "enabled": True,
                "resource_id": "mp_top_picks_clickable_item",
                "target_box": {"x": 0.0, "y": 0.49, "width": 0.49, "height": 0.26},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect listings read-only.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap"}, {"action": "back"}],
    )

    assert decision.next_action == "swipe"
    assert decision.target_box is not None
    assert decision.target_box.to_dict() == {"x": 0.08, "y": 0.28, "width": 0.84, "height": 0.34}


def test_facebook_listing_detail_expands_description_before_backing_out(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "Product Image,1 of 3",
            "MacBook Pro M2 Max 14",
            "$4000",
            "Description",
            "Amazing condition ... See more",
            "Message seller",
        ],
        clickable_text=["Close", "Navigate to Search", "Amazing condition ... See more", "Message seller"],
        components=[
            {
                "component_type": "button",
                "label": "Amazing condition\nSlightly used\nComes with the original box ... See more",
                "enabled": True,
                "target_box": {"x": 0.03, "y": 0.89, "width": 0.94, "height": 0.07},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap", "target_label": "$4000 · MacBook Pro M2 Max 14"}],
    )

    assert decision.next_action == "tap"
    assert "see more" in (decision.target_label or "").casefold()


def test_facebook_buy_now_listing_detail_expands_description_before_backing_out(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 6",
            "Apple MacBook Air Space Gray",
            "$450",
            "Ships for $11.74 + taxes",
            "Buy now",
            "Payments are processed securely",
        ],
        clickable_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 6",
            "Buy now",
            "Sleek Apple MacBook Air. Space Gray color. Laptop is in really great shape. I’m only selling because I was gifted a newer version. It has a | See more",
        ],
        components=[
            {
                "component_type": "button",
                "label": "Sleek Apple MacBook Air. Space Gray color. Laptop is in really great shape. I’m only selling because I was gifted a newer version. It has a | See more",
                "enabled": True,
                "target_box": {"x": 0.03, "y": 0.9, "width": 0.94, "height": 0.07},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace from a clean main view and inspect valuable resellable listings read-only.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap", "target_label": "$450 · Apple MacBook Air Space Gray"}],
    )

    assert decision.next_action == "tap"
    assert "see more" in (decision.target_label or "").casefold()


def test_facebook_listing_detail_swipes_once_to_reveal_seller_details(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 6",
            "Apple MacBook Air Space Gray",
            "$450",
            "Ships for $11.74 + taxes",
            "Buy now",
            "Payments are processed securely",
            "Description",
        ],
        clickable_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Buy now",
            "See less",
        ],
        components=[],
    )

    decision = agent.decide(
        goal="Inspect the current Facebook Marketplace listing read-only: inspect the product image, expand the description when available, read seller-visible details, then stop.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap", "target_label": "See more"}],
    )

    assert decision.next_action == "swipe"
    assert decision.target_box is not None
    assert decision.target_box.to_dict() == {"x": 0.08, "y": 0.62, "width": 0.84, "height": 0.22}


def test_model_swipe_decision_hydrates_default_facebook_swipe_region(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=["Marketplace", "For you", "Local", "$450 · Apple MacBook Air Space Gray"],
        clickable_text=["For you", "Local", "$450 · Apple MacBook Air Space Gray"],
        components=[],
    )

    decision = agent._coerce_decision(
        {
            "screen_classification": "facebook_marketplace_feed",
            "goal_progress": "advancing_feed",
            "next_action": "swipe",
            "target_box": None,
            "confidence": 1.0,
            "reason": "Scroll slightly to inspect more listings.",
            "risk_level": "low",
        },
        state=state,
        skill=bundle,
    )

    assert decision.next_action == "swipe"
    assert decision.target_box is not None
    assert decision.target_box.to_dict() == {"x": 0.08, "y": 0.28, "width": 0.84, "height": 0.34}


def test_facebook_home_feed_opens_messaging_for_inbox_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=["What's on your mind?", "Menu", "Search", "Messaging"],
        clickable_text=["Menu", "Search", "Messaging"],
        components=[
            {
                "component_type": "button",
                "label": "Messaging",
                "enabled": True,
                "target_box": {"x": 0.8777777777777778, "y": 0.03333333333333333, "width": 0.11203703703703703, "height": 0.050416666666666665},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages and read the inbox.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Messaging"


def test_facebook_home_feed_prefers_marketplace_for_seller_message_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=["What's on your mind?", "Menu", "Search", "Messaging", "Marketplace, tab 4 of 6"],
        clickable_text=["Menu", "Search", "Messaging", "Marketplace, tab 4 of 6"],
        components=[
            {
                "component_type": "button",
                "label": "Messaging",
                "enabled": True,
                "target_box": {"x": 0.8777777777777778, "y": 0.03333333333333333, "width": 0.11203703703703703, "height": 0.050416666666666665},
            },
            {
                "component_type": "button",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.08375, "width": 0.16666666666666666, "height": 0.055},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, pick a listing, and send 'Hi, is this still available?' to the seller.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Marketplace, tab 4 of 6"


def test_facebook_home_feed_prefers_marketplace_for_value_scan_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=["What's on your mind?", "Menu", "Search", "Messaging", "Marketplace, tab 4 of 6"],
        clickable_text=["Menu", "Search", "Messaging", "Marketplace, tab 4 of 6"],
        components=[
            {
                "component_type": "button",
                "label": "Messaging",
                "enabled": True,
                "target_box": {"x": 0.8777777777777778, "y": 0.03333333333333333, "width": 0.11203703703703703, "height": 0.050416666666666665},
            },
            {
                "component_type": "button",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.08375, "width": 0.16666666666666666, "height": 0.055},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace and keep scanning valuable local resale listings.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Marketplace, tab 4 of 6"


def test_facebook_listing_detail_opens_message_seller_for_send_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=["Back", "Apple Mac Mini M4 16GB 256GB", "$620", "Message seller", "Send offer"],
        clickable_text=["Back", "Message seller", "Send offer"],
        components=[
            {
                "component_type": "button",
                "label": "Message seller",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.84, "width": 0.36, "height": 0.06},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, pick a listing, and send 'Hi, is this still available?' to the seller.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Message seller"


def test_facebook_message_composer_types_requested_reply(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=["Message seller", "Hello, is this still available?", "Send"],
        clickable_text=["Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.10462962962962963, "y": 0.6754166666666667, "width": 0.6166666666666667, "height": 0.03666666666666667},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.7712962962962963, "y": 0.6754166666666667, "width": 0.15555555555555556, "height": 0.03666666666666667},
            },
        ],
    )

    decision = agent.decide(
        goal="Reply to the Marketplace seller with 'Yes, it is still available.'",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Yes, it is still available."


def test_facebook_message_inbox_opens_backup_thread(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            }
        ],
        "contacted_items": [],
    }
    state = make_facebook_state(
        activity_name=".messaging.InboxActivity",
        visible_text=["Messages", "Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        clickable_text=["Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.24, "width": 0.84, "height": 0.08},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"


def test_facebook_message_inbox_resets_for_clean_marketplace_scan_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".messaging.InboxActivity",
        visible_text=["Messages", "Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        clickable_text=["Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.24, "width": 0.84, "height": 0.08},
            }
        ],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and keep scanning valuable local resale listings.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_message_inbox_backs_out_after_reset_for_marketplace_scan_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".messaging.InboxActivity",
        visible_text=["Messages", "Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        clickable_text=["Search Messenger", "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        components=[
            {
                "component_type": "touch_target",
                "label": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.24, "width": 0.84, "height": 0.08},
            }
        ],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and keep scanning valuable local resale listings.",
        state=state,
        skill=bundle,
        action_history=[{"action": "reset_app", "tool_name": "reset_app"}],
    )

    assert decision.next_action == "back"
    assert decision.goal_progress == "recovering_to_marketplace"


def test_facebook_marketplace_inbox_opens_backup_thread(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            }
        ],
        "contacted_items": [],
        "workflow": {
            "mode": "reply",
            "mode_reason": "actionable_seller_replies",
            "reply_queue": [
                {
                    "thread_key": "joshua-canon-rf-35mm-f-1-8-macro-is-stm-lens",
                    "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                }
            ],
            "active_thread_key": "joshua-canon-rf-35mm-f-1-8-macro-is-stm-lens",
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_marketplace_inbox_state()

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"


def test_facebook_marketplace_inbox_resets_for_clean_value_scan_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_marketplace_inbox_state()

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and inspect valuable local resale listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "reset_app"


def test_facebook_marketplace_inbox_backs_out_after_reset_for_value_scan_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_marketplace_inbox_state()

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, and inspect valuable local resale listings.",
        state=state,
        skill=bundle,
        action_history=[{"action": "reset_app", "tool_name": "reset_app"}],
        yolo_mode=True,
    )

    assert decision.next_action == "back"
    assert decision.goal_progress == "recovering_to_marketplace"


def test_facebook_home_feed_checks_messages_after_recent_send(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [{"thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"}],
        "contacted_items": [{"item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens"}],
        "workflow": {
            "mode": "reply",
            "mode_reason": "actionable_seller_replies",
            "reply_queue": [{"thread_key": "joshua-canon", "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"}],
            "active_thread_key": "joshua-canon",
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_state(
        activity_name=".kana.feed.impl.FeedFragmentActivity",
        visible_text=["Search Facebook", "Marketplace, tab 4 of 6", "Menu, tab 6 of 6"],
        clickable_text=["Marketplace, tab 4 of 6", "Messaging", "Menu, tab 6 of 6"],
        components=[
            {
                "component_type": "button",
                "label": "Messaging",
                "enabled": True,
                "target_box": {"x": 0.93, "y": 0.08, "width": 0.05, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.64, "y": 0.08, "width": 0.1, "height": 0.05},
            },
        ],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, inspect valuable local resale listings, and send buyer messages using the Facebook skill rules.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap", "target_label": "Send", "screen_classification": "facebook_message_composer"}],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Messaging"
    assert decision.goal_progress == "checking_replies"


def test_facebook_hunt_mode_finishes_listing_before_switching_to_reply(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_key": "joshua-canon",
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
                "needs_reply": True,
            }
        ],
        "contacted_items": [],
        "workflow": {
            "mode": "hunt",
            "mode_reason": "finishing_listing_step",
            "reply_queue": [{"thread_key": "joshua-canon", "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"}],
            "active_thread_key": None,
            "active_listing_key": "lenovo-p16v-gen-1",
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Marketplace",
            "$790",
            "Lenovo P16v gen 1",
            "Description",
            "See details",
            "Message seller",
        ],
        clickable_text=["See details", "Message seller"],
        components=[
            {
                "component_type": "button",
                "label": "See details",
                "enabled": True,
                "target_box": {"x": 0.42, "y": 0.61, "width": 0.2, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Marketplace, inspect valuable local resale listings, and send buyer messages using the Facebook skill rules.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "See details"


def test_facebook_reply_mode_returns_to_hunt_when_queue_is_empty(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [],
        "contacted_items": [],
        "workflow": {
            "mode": "reply",
            "mode_reason": "draining_reply_queue",
            "reply_queue": [],
            "active_thread_key": None,
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_marketplace_inbox_state()

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and continue hunting when replies are done.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "back"
    assert decision.goal_progress == "returning_to_hunt"


def test_facebook_marketplace_feed_opens_account_for_reply_check_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "Tap to view your Marketplace account",
            "What do you want to buy?",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "Tap to view your Marketplace account",
            "What do you want to buy?",
        ],
        components=[
            {
                "component_type": "button",
                "label": "Tap to view your Marketplace account",
                "enabled": True,
                "target_box": {"x": 0.77, "y": 0.08, "width": 0.11, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Tap to view your Marketplace account"
    assert decision.goal_progress == "opening_marketplace_account"


def test_facebook_reply_goal_overrides_hunt_workflow_on_marketplace_feed(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [],
        "contacted_items": [],
        "workflow": {
            "mode": "hunt",
            "mode_reason": "queue_empty",
            "reply_queue": [],
            "active_thread_key": None,
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Sell",
            "For you",
            "Local",
            "Marketplace",
            "Tap to view your Marketplace account",
            "What do you want to buy?",
        ],
        clickable_text=[
            "Sell",
            "For you",
            "Local",
            "Tap to view your Marketplace account",
            "What do you want to buy?",
        ],
        components=[
            {
                "component_type": "button",
                "label": "Tap to view your Marketplace account",
                "enabled": True,
                "target_box": {"x": 0.77, "y": 0.08, "width": 0.11, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Check Facebook Marketplace seller replies, send follow-up replies, and then continue hunting for listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Tap to view your Marketplace account"
    assert decision.goal_progress == "opening_marketplace_account"


def test_facebook_marketplace_account_opens_messages_for_reply_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [],
        "contacted_items": [],
        "workflow": {
            "mode": "hunt",
            "mode_reason": "queue_empty",
            "reply_queue": [],
            "active_thread_key": None,
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Owen Uj",
            "View Marketplace profile",
            "10+ saved items",
            "1 message",
            "Recently viewed",
            "Marketplace access",
        ],
        clickable_text=[
            "View Marketplace profile",
            "10+ saved items",
            "1 message",
            "Recently viewed",
            "Marketplace access",
            "Back",
        ],
        components=[
            {
                "component_type": "button",
                "label": "1 message, ,",
                "enabled": True,
                "target_box": {"x": 0.51, "y": 0.16, "width": 0.46, "height": 0.08},
            }
        ],
    )

    decision = agent.decide(
        goal="Check Facebook Marketplace seller replies, send follow-up replies, and then continue hunting for listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.goal_progress == "opening_messages"
    assert decision.target_label == "1 message, ,"


def test_facebook_thread_surface_is_not_misclassified_as_generic_inbox(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_key": "jesse-prebuilt-gaming-pc-5060ti",
                "thread_title": "Jesse · Prebuilt Gaming pc 5060ti",
                "seller_name": "Jesse",
                "item_title": "Prebuilt Gaming pc 5060ti",
                "last_inbound_message": "Jesse sold Prebuilt Gaming pc 5060ti.",
                "last_outbound_message": "Hey, is this still available?",
                "needs_reply": True,
            }
        ],
        "contacted_items": [],
        "workflow": {
            "mode": "reply",
            "mode_reason": "actionable_seller_replies",
            "reply_queue": [{"thread_key": "jesse-prebuilt-gaming-pc-5060ti", "thread_title": "Jesse · Prebuilt Gaming pc 5060ti"}],
            "active_thread_key": "jesse-prebuilt-gaming-pc-5060ti",
            "active_listing_key": None,
            "last_mode_switch_at": None,
            "last_reply_check_at": None,
            "handled_thread_keys": [],
        },
    }
    state = make_facebook_state(
        activity_name="com.facebook.messaging.msys.thread.fragment.MsysThreadViewActivity",
        visible_text=[
            "Back",
            "Jesse · Prebuilt Gaming pc 5060ti",
            "Marketplace listing",
            "Chat profile",
            "Type a message",
            "Send",
        ],
        clickable_text=[
            "Back",
            "Jesse · Prebuilt Gaming pc 5060ti",
            "Marketplace listing",
            "Chat profile",
            "Type a message",
            "Send",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Type a message",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.95, "width": 0.7, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.92, "y": 0.95, "width": 0.08, "height": 0.05},
            },
            {
                "component_type": "touch_target",
                "label": "Back | Jesse · Prebuilt Gaming pc 5060ti | Marketplace listing | Chat profile",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.05, "width": 1.0, "height": 0.08},
            },
        ],
    )

    decision = agent.decide(
        goal="Check Facebook Marketplace seller replies, send follow-up replies using the Facebook skill rules if any actionable seller messages are present, and then continue the Marketplace hunt for more listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.screen_classification == "facebook_message_thread"
    assert decision.next_action in {"tool", "type"}
    if decision.next_action == "tool":
        assert decision.tool_name == "run_fast_function"
        assert decision.tool_arguments["function_name"] == "send_thread_reply"


def test_facebook_home_feed_prefers_marketplace_tab_over_feed_post(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Go to profile",
            "What's on your mind?",
            "Stories",
            "Good morning. Should I continue using business cards?",
            "Marketplace, tab 4 of 6",
        ],
        clickable_text=[
            "Good morning. Should I continue using business cards?",
            "Messaging",
            "Marketplace, tab 4 of 6",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Good morning. Should I continue using business cards?",
                "enabled": True,
                "target_box": {"x": 0.1, "y": 0.45, "width": 0.8, "height": 0.12},
            },
            {
                "component_type": "touch_target",
                "label": "Marketplace, tab 4 of 6",
                "enabled": True,
                "target_box": {"x": 0.5, "y": 0.03, "width": 0.16, "height": 0.05},
            },
        ],
    )

    decision = agent.decide(
        goal="Resume the Facebook Marketplace hunting workflow and continue scanning listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Marketplace, tab 4 of 6"


def test_facebook_marketplace_account_opens_messages_row_for_reply_check_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Owen Uj",
            "View Marketplace profile",
            "10+ saved items",
            "2 messages",
            "10+ reviews to write",
        ],
        clickable_text=[
            "Owen Uj, View Marketplace profile",
            "10+ saved items, ,",
            "2 messages, ,",
            "10+ reviews to write, ,",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "2 messages, ,",
                "enabled": True,
                "target_box": {"x": 0.1, "y": 0.33, "width": 0.8, "height": 0.06},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "2 messages, ,"
    assert decision.goal_progress == "opening_messages"


def test_facebook_marketplace_inbox_detects_newer_inbox_wording() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    state = make_facebook_state(
        activity_name="com.facebook.messaginginblue.inbox.activities.InboxActivity",
        visible_text=[
            "Back",
            "Marketplace inbox",
            "Restore chat history.",
            "DebySue · 2023 MacBook pro, Unread, DebySue: Yes",
        ],
        clickable_text=["Back", "DebySue · 2023 MacBook pro, Unread, DebySue: Yes"],
        components=[],
    )

    assert agent._facebook_marketplace_inbox_visible(state) is True


def test_facebook_thread_settings_recovers_with_back(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name="com.facebook.messaginginblue.threadsettings.surface.activity.MiBThreadSettingsSurfaceActivity",
        visible_text=[
            "Back",
            "Edit",
            "Joshua · PC",
            "Mute notifications",
            "Messenger",
            "Chat info",
            "Search in conversation",
            "Read receipts",
            "Leave chat",
        ],
        clickable_text=[
            "Back",
            "Edit",
            "Mute notifications",
            "Messenger",
            "Search in conversation",
            "Read receipts",
            "Leave chat",
        ],
        components=[],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, inspect valuable local resale listings, send short human buyer messages using the Facebook skill rules when profitable, and periodically check Marketplace replies from sellers before messaging more new listings.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "back"
    assert decision.goal_progress == "recovering_to_thread"


def test_facebook_marketplace_inbox_falls_back_to_visible_thread_not_help(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            }
        ],
        "contacted_items": [],
    }
    state = make_facebook_marketplace_inbox_without_backup_match_state()

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "Ariel · iphone 15 pro"


def test_facebook_marketplace_inbox_prefers_unread_visible_reply_over_stale_backup(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · PC",
                "item_title": "PC",
                "seller_name": "Joshua",
                "last_inbound_message": "No",
            }
        ],
        "contacted_items": [],
    }
    state = make_facebook_state(
        activity_name="com.facebook.messaginginblue.inbox.activities.InboxActivity",
        visible_text=[
            "Back",
            "Marketplace inbox",
            "Shoumik · [Full PC] 32GB DDR5 RAM / Ryzen 5 7600 / RX 6700 XT /, Unread, Shoumik: Yes, are you interested?",
            "Joshua · PC, Read, You: Hi, is this available?",
        ],
        clickable_text=[
            "Back",
            "Shoumik · [Full PC] 32GB DDR5 RAM / Ryzen 5 7600 / RX 6700 XT /, Unread, Shoumik: Yes, are you interested?",
            "Joshua · PC, Read, You: Hi, is this available?",
        ],
        components=[
            {
                "component_type": "touch_target",
                "label": "Shoumik · [Full PC] 32GB DDR5 RAM / Ryzen 5 7600 / RX 6700 XT /, Unread, Shoumik: Yes, are you interested?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.25, "width": 0.84, "height": 0.09},
            },
            {
                "component_type": "touch_target",
                "label": "Joshua · PC, Read, You: Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.37, "width": 0.84, "height": 0.09},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label.startswith("Shoumik · [Full PC]")


def test_facebook_marketplace_help_recovers_with_back_for_message_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Get help on Marketplace",
            "Learn how to block someone on Marketplace",
            "See our Marketplace safety tips",
            "Learn how to mark an item as sold",
        ],
        clickable_text=[
            "Learn how to block someone on Marketplace",
            "See our Marketplace safety tips",
            "Learn how to mark an item as sold",
            "See more",
        ],
        components=[],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies, and read the latest thread.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "back"


def test_facebook_default_thread_reply_prefers_delivery_to_bothell() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")

    reply = agent._facebook_default_thread_reply(
        {
            "item_title": "MacBook Air M2 13-inch 16GB 256GB",
            "price": "$700",
            "last_inbound_message": "Yes, still available",
            "last_outbound_message": "Hey, is your MacBook Air still available?",
        }
    )

    assert reply == "Can you do $425? Thanks"


def test_facebook_clean_message_normalizes_weird_caps() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")

    cleaned = agent._facebook_clean_message("COULD YOU LET ME KNOW THE rAm and ssd ON THIS macbook air m1?")

    assert cleaned == "Could you let me know the RAM and SSD on this MacBook Air M1?"


def test_facebook_default_thread_reply_asks_for_address_on_pickup_only() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")

    reply = agent._facebook_default_thread_reply(
        {
            "item_title": "Nintendo Switch OLED",
            "last_inbound_message": "Yes, but it's pickup only",
        }
    )

    assert reply == "Hey, what’s the pickup address or nearest cross streets?"


def test_facebook_default_thread_reply_moves_to_bothell_after_counter() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")

    reply = agent._facebook_default_thread_reply(
        {
            "item_title": "ASUS TUF Gaming PC",
            "price": "$410",
            "last_inbound_message": "$390",
            "last_outbound_message": "Can you do $350? Thanks",
        }
    )

    assert reply == "Can we meet in Bothell?"


def test_facebook_default_thread_reply_asks_location_when_seller_cannot_meet() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")

    reply = agent._facebook_default_thread_reply(
        {
            "item_title": "ASUS TUF Gaming PC",
            "last_inbound_message": "I don’t have a car atm",
            "last_outbound_message": "Can we meet in Bothell?",
        }
    )

    assert reply == "Where are you located?"


def test_facebook_message_thread_stop_mentions_latest_known_reply(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            }
        ],
        "contacted_items": [],
    }
    state = make_facebook_state(
        activity_name=".messaging.ThreadActivity",
        visible_text=[
            "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
            "Marketplace listing",
            "Type a message",
            "Send",
        ],
        clickable_text=["Type a message", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Type a message",
                "enabled": True,
                "target_box": {"x": 0.1, "y": 0.9, "width": 0.6, "height": 0.05},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.75, "y": 0.9, "width": 0.15, "height": 0.05},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages and check for new replies.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "stop"
    assert "Latest known seller reply" in decision.reason
    assert "West Seattle" in decision.reason


def test_facebook_read_only_message_goal_does_not_draft_reply(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    bundle.backup_data["facebook_marketplace"] = {
        "threads": [
            {
                "thread_title": "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
                "item_title": "Canon RF 35mm f/1.8 Macro IS STM Lens",
                "seller_name": "Joshua",
                "last_inbound_message": "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            }
        ],
        "contacted_items": [],
    }
    state = make_facebook_state(
        activity_name="com.facebook.messaging.msys.thread.fragment.MsysThreadViewActivity",
        visible_text=[
            "Back",
            "Marketplace listing",
            "Additional attachment options",
            "Type a message…",
            "Send",
        ],
        clickable_text=[
            "Back | Marketplace listing | Additional attachment options | Type a message…",
            "Send",
        ],
        components=[
            {
                "component_type": "text_input",
                "label": "Type a message…",
                "enabled": True,
                "target_box": {"x": 0.35, "y": 0.93, "width": 0.5, "height": 0.04},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.83, "y": 0.93, "width": 0.1, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages, check for new seller replies using the saved backup, open the most relevant Marketplace thread, read the latest seller response, and stop without sending anything.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "stop"
    assert "Latest known seller reply" in decision.reason


def test_facebook_message_composer_replaces_default_with_custom_listing_message(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Canon RF 35mm f/1.8 Macro IS STM Lens",
            "$325",
            "Product Image, 1 of 5",
            "Message seller",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "resource_id": "marketplace_pdp_message_cta_input",
                "target_box": {"x": 0.09, "y": 0.72, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.715, "width": 0.15, "height": 0.036},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, find a good resale listing, and send the seller a message asking if it is available.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, is your Canon RF 35mm f/1.8 still available?"


def test_facebook_message_composer_uses_profit_target_offer_for_overpriced_macbook(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Back",
            "MacBook Air M2 13-inch 16GB 256GB",
            "$700",
            "Product Image, 1 of 5",
            "Hello, is this still available?",
            "Send",
        ],
        clickable_text=["Back", "Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, if it's in good shape, would you take $425 for your MacBook Air M2? Thanks"


def test_facebook_message_composer_uses_more_aggressive_offer_for_overpriced_macbook_air_m1(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Back",
            "MacBook Air M1 8GB 256GB",
            "$375",
            "Product Image, 1 of 5",
            "Hello, is this still available?",
            "Send",
        ],
        clickable_text=["Back", "Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, if it's in good shape, would you take $230 for your MacBook Air M1? Thanks"


def test_facebook_message_composer_distinguishes_macbook_air_m2_base_model_from_16gb_model(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Back",
            "MacBook Air M2 13-inch 8GB 256GB",
            "$550",
            "Product Image, 1 of 5",
            "Hello, is this still available?",
            "Send",
        ],
        clickable_text=["Back", "Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, if it's in good shape, would you take $325 for your MacBook Air M2? Thanks"


def test_facebook_message_composer_falls_back_to_availability_when_ask_is_already_profitable(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Back",
            "MacBook Air M2 13-inch 16GB 256GB",
            "$425",
            "Product Image, 1 of 5",
            "Hello, is this still available?",
            "Send",
        ],
        clickable_text=["Back", "Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, is your MacBook Air M2 still available?"


def test_facebook_message_composer_asks_for_missing_specs_and_condition_when_text_is_incomplete(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Back",
            "MacBook Air",
            "$700",
            "Hello, is this still available?",
            "Send",
        ],
        clickable_text=["Back", "Hello, is this still available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, can you share the specs and current condition for your MacBook Air?"
    assert decision.target_box is not None


def test_facebook_listing_message_goal_expands_details_before_drafting_reply(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Desktop Components - all great quality!",
            "$123",
            "Hello, is this still available?",
            "Message sent to seller",
            "See Conversation",
            "Description",
        ],
        clickable_text=["See details", "More Options", "See Conversation"],
        components=[
            {
                "component_type": "button",
                "label": "See details",
                "enabled": True,
                "target_box": {"x": 0.05, "y": 0.12, "width": 0.4, "height": 0.06},
            },
            {
                "component_type": "text_input",
                "label": "Hello, is this still available?",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.75, "width": 0.64, "height": 0.03},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.78, "y": 0.62, "width": 0.15, "height": 0.04},
            },
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
    )

    assert decision.next_action == "tap"
    assert "see details" in (decision.target_label or "").casefold()


def test_facebook_listing_after_send_opens_see_conversation_to_capture_thread(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Nintendo Switch OLED in White",
            "$200",
            "Message sent to seller",
            "See conversation",
            "Description",
        ],
        clickable_text=["See conversation"],
        components=[
            {
                "component_type": "button",
                "label": "See conversation",
                "enabled": True,
                "target_box": {"x": 0.08, "y": 0.32, "width": 0.45, "height": 0.05},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace, inspect valuable local resale listings, send short human buyer messages using the Facebook skill rules when profitable, periodically check Marketplace replies from sellers, and continue hunting.",
        state=state,
        skill=bundle,
        action_history=[{"action": "tap", "target_label": "Send", "screen_classification": "facebook_message_composer"}],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "See conversation"


def test_facebook_message_composer_uses_custom_message_for_send_buyer_messages_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Navigate to Search",
            "More actions",
            "Product Image,1 of 2",
            "2023 MacBook pro",
            "$1,200",
            "Hi, is this available?",
            "Send",
            "Description",
            "Mac book pro",
            "16\" screen",
            "M2",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.09166666666666666, "y": 0.76375, "width": 0.6407407407407407, "height": 0.022916666666666665},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.7833333333333333, "y": 0.7566666666666667, "width": 0.15555555555555556, "height": 0.03666666666666667},
            },
        ],
    )

    decision = agent.decide(
        goal="Reset Facebook to a clean main view, open Marketplace, inspect valuable local resale listings, prefer iPhones, MacBooks, Macs, cameras, monitors, gaming PCs, GPUs, and premium furniture, read details, and keep scanning. If Marketplace messaging is available again, send buyer messages using the Facebook skill rules; otherwise continue read-only scanning until blocked.",
        state=state,
        skill=bundle,
        action_history=[{"action": "reset_app", "tool_name": "reset_app"}],
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, can you share the full specs for your MacBook Pro?"


def test_facebook_read_only_scanning_phrase_does_not_disable_custom_message_flow(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    goal = (
        "Reset Facebook to a clean main view, open Marketplace, inspect valuable local resale listings, "
        "and if Marketplace messaging is available again, send buyer messages using the Facebook skill rules; "
        "otherwise continue read-only scanning until blocked."
    )

    assert agent._facebook_goal_requests_read_only_message_check(goal) is False
    assert agent._facebook_goal_targets_listing_message(goal) is True


def test_facebook_postprocess_rewrites_send_to_custom_message_for_listing_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 3",
            "[Full PC] 32GB DDR5 RAM / Ryzen 5 7600 / RX 6700 XT /",
            "$1,100",
            "Hi, is this available?",
            "Send",
            "Description",
            "32GB DDR5 RAM @ 6000mhz",
            "AMD Ryzen 5 7600",
            "XFX RX 6700 XT 12GB",
            "Available for PICK-UP ONLY. Located in north Ballard.",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.09166666666666666, "y": 0.79125, "width": 0.6407407407407407, "height": 0.022916666666666665},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.7833333333333333, "y": 0.7841666666666667, "width": 0.15555555555555556, "height": 0.03666666666666667},
            },
        ],
    )
    original = VisionDecision(
        screen_classification="Marketplace Listing Detail",
        goal_progress="sending",
        next_action="tap",
        target_box=BoundingBox(x=0.7833333333333333, y=0.7841666666666667, width=0.15555555555555556, height=0.03666666666666667),
        confidence=1.0,
        reason="The goal explicitly requests sending buyer messages if available. The 'Send' button is visible.",
        risk_level="low",
        target_label="Send",
    )
    goal = "Reset Facebook to a clean main view, open Marketplace, inspect valuable local resale listings, prefer iPhones, MacBooks, Macs, cameras, monitors, gaming PCs, GPUs, and premium furniture, read details, and keep scanning. If Marketplace messaging is available again, send buyer messages using the Facebook skill rules; otherwise continue read-only scanning until blocked."

    decision = agent._apply_post_decision_overrides(
        goal=goal,
        state=state,
        skill=bundle,
        action_history=[{"action": "reset_app", "tool_name": "reset_app"}],
        decision=original,
    )

    assert decision.next_action == "type"
    assert decision.input_text == "Hey, is your gaming PC still available?"


def test_facebook_postprocess_expands_listing_details_before_rewriting_send(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 6",
            'Dell UltraSharp 27" Monitor + Razer RGB Gaming Keyboard',
            "$200",
            "Message seller",
            "Description",
            "Selling a Dell UltraSharp 27 Monitor and Razer RGB gaming keyboard in excellent, like-new",
            "condition. Both were barely used for about a",
            "See more",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=["Hi, is this available?", "Send", "See more"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.09166666666666666, "y": 0.80875, "width": 0.6407407407407407, "height": 0.022916666666666665},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.7833333333333333, "y": 0.8016666666666666, "width": 0.15555555555555556, "height": 0.03666666666666667},
            },
            {
                "component_type": "button",
                "label": "See more",
                "enabled": True,
                "target_box": {"x": 0.7888888888888889, "y": 0.9754166666666667, "width": 0.18055555555555555, "height": 0.014583333333333334},
            },
        ],
    )
    original = VisionDecision(
        screen_classification="Marketplace Listing Detail",
        goal_progress="sending",
        next_action="tap",
        target_box=BoundingBox(x=0.7833333333333333, y=0.8016666666666666, width=0.15555555555555556, height=0.03666666666666667),
        confidence=1.0,
        reason="The goal explicitly requests sending buyer messages if available. The 'Send' button is visible.",
        risk_level="low",
        target_label="Send",
    )

    decision = agent._apply_post_decision_overrides(
        goal="Open Facebook Marketplace, look for profitable resale deals, and message seller on promising items.",
        state=state,
        skill=bundle,
        action_history=[],
        decision=original,
    )

    assert decision.next_action == "tap"
    assert "see more" in (decision.target_label or "").casefold()


def test_facebook_postprocess_rewrites_default_type_message_for_listing_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    manager.save_fast_function(
        "facebook",
        "send_initial_message",
        {
            "name": "send_initial_message",
            "description": "",
            "args": [{"name": "message", "required": True}],
            "steps": [{"action": "type", "input_text": "{{message}}"}, {"action": "tap", "target_label": "Send"}],
            "preconditions": [{"predicate": "facebook_listing_detail_visible"}],
            "postconditions": [{"predicate": "facebook_listing_message_sent"}],
            "fallback_policy": "fallback_to_slow_path",
        },
    )
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 3",
            "M4 MacBook Air",
            "$999",
            "Hi, is this available?",
            "Send",
            "Description",
            "Bought not too long ago, works perfectly fine.",
            "Includes original charger.",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.091, "y": 0.79, "width": 0.64, "height": 0.023},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.783, "y": 0.784, "width": 0.155, "height": 0.036},
            },
        ],
    )
    original = VisionDecision(
        screen_classification="facebook_message_composer",
        goal_progress="drafting_reply",
        next_action="type",
        target_box=BoundingBox(x=0.091, y=0.79, width=0.64, height=0.023),
        confidence=0.91,
        reason="The message input field is focused with the default text selected.",
        risk_level="low",
        input_text="Hi, is this available?",
        submit_after_input=False,
        target_label="Hi, is this available?",
    )

    decision = agent._apply_post_decision_overrides(
        goal="Resume the Facebook Marketplace hunting workflow. Inspect valuable local resale listings, send short human buyer messages using the Facebook skill rules when profitable, and continue hunting.",
        state=state,
        skill=bundle,
        action_history=[],
        decision=original,
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "run_fast_function"
    assert decision.tool_arguments["function_name"] == "send_initial_message"
    assert decision.tool_arguments["arguments"]["message"] == "Hey, can you share the full specs for your MacBook Air?"


def test_facebook_postprocess_rewrites_fast_function_pickup_message_for_listing_goal(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 1",
            'Macbook Air 13" M2',
            "$550",
            "Message seller",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.091, "y": 0.626, "width": 0.64, "height": 0.022},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.783, "y": 0.619, "width": 0.155, "height": 0.029},
            },
        ],
    )
    original = VisionDecision.tool(
        tool_name="run_fast_function",
        tool_arguments={
            "app_name": "facebook",
            "function_name": "send_initial_message",
            "arguments": {"message": "Hi, I can pick this up today. Is this still available?"},
        },
        screen_classification="marketplace_listing_message_input",
        goal_progress="sending_reply",
        confidence=0.95,
        reason="Use the fast function to replace the default Marketplace message and send it with verification.",
        target_label="send_initial_message",
    )

    decision = agent._apply_post_decision_overrides(
        goal="Resume the Facebook Marketplace hunting workflow. Inspect valuable local resale listings, send short human buyer messages using the Facebook skill rules when profitable, and continue hunting.",
        state=state,
        skill=bundle,
        action_history=[],
        decision=original,
    )

    assert decision.next_action == "tool"
    assert decision.tool_name == "run_fast_function"
    assert decision.tool_arguments["function_name"] == "send_initial_message"
    assert decision.tool_arguments["arguments"]["message"] == "Hey, can you share the full specs for your MacBook Air?"


def test_facebook_postprocess_rewrites_mixed_offer_and_specs_message(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 1",
            "Macbook Air 13\" M2",
            "$550",
            "Message seller",
            "Hi, is this available?",
            "Send",
        ],
        clickable_text=["Hi, is this available?", "Send"],
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "target_box": {"x": 0.091, "y": 0.626, "width": 0.64, "height": 0.022},
            },
            {
                "component_type": "button",
                "label": "Send",
                "enabled": True,
                "target_box": {"x": 0.783, "y": 0.619, "width": 0.155, "height": 0.029},
            },
        ],
    )
    original = VisionDecision.tool(
        tool_name="run_fast_function",
        tool_arguments={
            "app_name": "facebook",
            "function_name": "send_initial_message",
            "arguments": {"message": "Would you take $325, and what are the specs and condition?"},
        },
        screen_classification="marketplace_listing_message_input",
        goal_progress="sending_reply",
        confidence=0.95,
        reason="Use the fast function to replace the default Marketplace message and send it with verification.",
        target_label="send_initial_message",
    )

    decision = agent._apply_post_decision_overrides(
        goal="Resume the Facebook Marketplace hunting workflow. Inspect valuable local resale listings, send short human buyer messages using the Facebook skill rules when profitable, and continue hunting.",
        state=state,
        skill=bundle,
        action_history=[],
        decision=original,
    )

    assert decision.next_action == "tool"
    assert decision.tool_arguments["arguments"]["message"] == "Hey, can you share the full specs for your MacBook Air?"


def test_facebook_default_marketplace_message_prefers_direct_offer_with_thanks_when_specs_known() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 3",
            "MacBook Air M2 8GB 256GB",
            "$550",
            "excellent condition",
            "Send offer",
        ],
        clickable_text=["Send offer"],
        components=[],
    )

    message = agent._facebook_default_marketplace_message(
        state,
        goal="Inspect valuable local resale listings and send short human buyer messages when profitable.",
    )

    assert message == "Hey, if it's in good shape, would you take $325 for your MacBook Air M2? Thanks"


def test_facebook_message_candidate_rejection_event_is_recorded() -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    state = make_facebook_state(
        activity_name=".activity.react.ImmersiveReactActivity",
        visible_text=[
            "Close",
            "Product Image,1 of 3",
            "PS5 & Two Controllers",
            "$300",
            "Message seller",
        ],
        clickable_text=["Message seller"],
        components=[],
    )

    message = agent._facebook_finalize_marketplace_message(
        "Hi, I can pick this up today. Is it still available?",
        state=state,
        goal="Inspect valuable local resale listings and send short human buyer messages when profitable.",
        mode="initial",
    )
    events = agent.consume_events()

    assert message == "Hey, can you share the full specs for your PS5 & Two Controllers?"
    assert any(
        event["type"] == "message_candidate_rejected"
        and event["attempted_outbound_text"] == "Hi, I can pick this up today. Is it still available?"
        and event["rejection_reason"] == "premature_logistics"
        for event in events
    )


def test_facebook_message_recovery_prompt_auto_continues_in_yolo_mode(tmp_path: Path) -> None:
    agent = VisionAgent(None, "gemini-3.1-pro-preview")
    bundle = SkillManager(tmp_path).load_skill(APP_REGISTRY["facebook"])
    state = make_facebook_state(
        activity_name=".LoginActivity",
        visible_text=[
            "Are you sure?",
            "Some of your end-to-end encrypted messages may be missing.",
            "CANCEL",
            "YES",
        ],
        clickable_text=["CANCEL", "YES"],
        components=[
            {
                "component_type": "button",
                "label": "YES",
                "enabled": True,
                "target_box": {"x": 0.7759259259259259, "y": 0.5470833333333334, "width": 0.12685185185185185, "height": 0.055},
            }
        ],
    )

    decision = agent.decide(
        goal="Open Facebook Marketplace messages and read the inbox.",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.target_label == "YES"


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


def test_gmail_notification_permission_auto_allows_in_yolo_mode(tmp_path: Path) -> None:
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
        visible_text=["Allow Gmail to send notifications?", "Allow", "Don't allow"],
        clickable_text=["Allow", "Don't allow"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "button",
                "label": "Allow",
                "enabled": True,
                "search_related": False,
                "target_box": {"x": 0.12, "y": 0.48, "width": 0.75, "height": 0.06},
            }
        ],
    )

    decision = agent.decide(
        goal="open Gmail and look through emails",
        state=state,
        skill=bundle,
        action_history=[],
        yolo_mode=True,
    )

    assert decision.next_action == "tap"
    assert decision.requires_user_approval is False
    assert decision.target_label == "Allow"


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
