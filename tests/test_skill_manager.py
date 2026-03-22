from pathlib import Path

from agent_runner.config import APP_REGISTRY
from agent_runner.models import BoundingBox, DeviceInfo, ScreenState, VisionDecision
from agent_runner.skill_manager import SkillManager


def make_state(app_name: str) -> ScreenState:
    app = APP_REGISTRY[app_name]
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name=app.package_name,
        activity_name=".TestActivity",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="hash123",
        xml_source="""
        <hierarchy>
          <node
            class="android.widget.EditText"
            content-desc="Search orders"
            clickable="true"
            enabled="true"
            bounds="[100,200][600,320]" />
        </hierarchy>
        """,
        visible_text=["Your Orders", "Track package"],
        clickable_text=["Your Orders"],
        package_name=app.package_name,
        activity_name=".TestActivity",
        device=device,
    )


def make_facebook_thread_state() -> ScreenState:
    app = APP_REGISTRY["facebook"]
    device = DeviceInfo(
        serial="10.0.0.206:43337",
        width=1080,
        height=2400,
        density=440,
        orientation="portrait",
        package_name=app.package_name,
        activity_name=".ThreadActivity",
    )
    return ScreenState(
        screenshot_path=Path("/tmp/facebook-thread.png"),
        hierarchy_path=Path("/tmp/facebook-thread.xml"),
        screenshot_sha256="facebookhash",
        xml_source="""
        <hierarchy>
          <node class="android.view.ViewGroup" text="Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens" content-desc="Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens" />
          <node class="android.view.ViewGroup" text="Marketplace listing" content-desc="Marketplace listing" />
          <node class="android.view.ViewGroup" text="5.0 (13 reviews of Joshua)" content-desc="5.0 (13 reviews of Joshua)" />
          <node class="android.view.ViewGroup" text="Owen, Hi, I’m interested in the Canon RF 35mm f/1.8 Macro IS STM Lens. Is it still available?" content-desc="Owen, Hi, I’m interested in the Canon RF 35mm f/1.8 Macro IS STM Lens. Is it still available?" />
          <node class="android.view.ViewGroup" text="Joshua, Yes, available for pickup in West Seattle off 49th Ave SW near Juneau" content-desc="Joshua, Yes, available for pickup in West Seattle off 49th Ave SW near Juneau" />
          <node class="android.widget.ImageView" text="" content-desc="Seen by Joshua Carlin" />
        </hierarchy>
        """,
        visible_text=[
            "Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens",
            "Marketplace listing",
            "5.0 (13 reviews of Joshua)",
            "Owen, Hi, I’m interested in the Canon RF 35mm f/1.8 Macro IS STM Lens. Is it still available?",
            "Joshua, Yes, available for pickup in West Seattle off 49th Ave SW near Juneau",
            "Seen by Joshua Carlin",
        ],
        clickable_text=["Joshua · Canon RF 35mm f/1.8 Macro IS STM Lens"],
        package_name=app.package_name,
        activity_name=".ThreadActivity",
        device=device,
    )


def test_skill_manager_bootstraps_and_updates_files(tmp_path: Path) -> None:
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["amazon"])
    load_events = manager.consume_events()

    assert bundle.app_dir.exists()
    assert "Amazon" in bundle.instructions
    assert load_events[0]["type"] == "skill_loaded"
    assert (bundle.app_dir / "data" / "backup.json").exists()
    assert (bundle.app_dir / "data" / "backup.md").exists()

    state = make_state("amazon")
    decision = VisionDecision(
        screen_classification="orders",
        goal_progress="navigating",
        next_action="tap",
        target_box=BoundingBox(0.2, 0.2, 0.2, 0.1),
        confidence=0.8,
        reason="Open orders.",
        risk_level="low",
        target_label="Your Orders",
    )
    screen_id = manager.update_after_observation(bundle, state, decision)
    observation_events = manager.consume_events()
    assert screen_id in bundle.screens["screens"]
    assert bundle.selectors["selectors"][0]["label"] == "Your Orders"
    assert any(
        selector.get("component_type") == "text_input"
        for selector in bundle.selectors["selectors"]
    )
    assert any(event["type"] == "skill_auto_updated" for event in observation_events)

    manager.update_backup(bundle, state)
    backup_events = manager.consume_events()
    assert any(event["type"] == "backup_updated" for event in backup_events)
    assert bundle.backup_data["recent_screens"]
    assert "Recent screens" in bundle.backup_summary

    manager.update_run_state(
        bundle,
        status="completed",
        reason="Done",
        last_screen_id=screen_id,
        action_history=[],
        failure_count=0,
    )
    run_state_events = manager.consume_events()
    assert "Status: completed" in (bundle.app_dir / "memory.md").read_text(encoding="utf-8")
    assert any(event["type"] == "memory_updated" for event in run_state_events)

    manager.update_run_state(
        bundle,
        status="stalled",
        reason="Still on the same screen.",
        last_screen_id=screen_id,
        action_history=[],
        failure_count=1,
    )
    memory_text = (bundle.app_dir / "memory.md").read_text(encoding="utf-8")
    assert "Status: completed" in memory_text
    assert "Status: stalled" in memory_text


def test_skill_manager_records_search_transition(tmp_path: Path) -> None:
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["playstore"])
    before_state = make_state("playstore")
    after_state = make_state("playstore")
    after_state.visible_text[:] = ["Results for maps", "Google Maps"]
    after_state.clickable_text[:] = ["Google Maps"]
    decision = VisionDecision(
        screen_classification="search_box",
        goal_progress="typing_query",
        next_action="type",
        target_box=BoundingBox(0.1, 0.1, 0.4, 0.1),
        confidence=0.8,
        reason="Enter a Play Store search query.",
        risk_level="low",
        input_text="maps",
        submit_after_input=True,
        target_label="Search apps & games",
    )

    manager.update_after_transition(
        bundle,
        before_state=before_state,
        decision=decision,
        after_state=after_state,
    )

    assert bundle.state["last_search_transition"]["input_text"] == "maps"
    assert bundle.state["last_search_transition"]["submit_after_input"] is True


def test_skill_manager_updates_facebook_backup_from_thread_state(tmp_path: Path) -> None:
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["facebook"])
    manager.consume_events()
    state = make_facebook_thread_state()

    manager.update_backup(bundle, state)

    events = manager.consume_events()
    facebook_backup = bundle.backup_data["facebook_marketplace"]

    assert any(event["type"] == "backup_updated" for event in events)
    assert facebook_backup["threads"][0]["item_title"] == "Canon RF 35mm f/1.8 Macro IS STM Lens"
    assert facebook_backup["threads"][0]["seller_name"] == "Joshua"
    assert (
        facebook_backup["threads"][0]["last_inbound_message"]
        == "Yes, available for pickup in West Seattle off 49th Ave SW near Juneau"
    )
    assert facebook_backup["contacted_items"][0]["message_status"] == "seller_confirmed_available"
    assert "West Seattle" in bundle.backup_summary
    assert "Canon RF 35mm f/1.8 Macro IS STM Lens" in bundle.backup_summary
