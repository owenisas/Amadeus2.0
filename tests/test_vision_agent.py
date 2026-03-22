import json
import io
from pathlib import Path
import urllib.error

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
    assert calls[0]["response_format"]["type"] == "text"
    assert isinstance(calls[0]["messages"][0]["content"], list)
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


def test_facebook_stale_listing_detail_backs_out(tmp_path: Path) -> None:
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

    assert decision.next_action == "back"


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
