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


def test_skill_manager_bootstraps_and_updates_files(tmp_path: Path) -> None:
    manager = SkillManager(tmp_path)
    bundle = manager.load_skill(APP_REGISTRY["amazon"])

    assert bundle.app_dir.exists()
    assert "Amazon" in bundle.instructions

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
    assert screen_id in bundle.screens["screens"]
    assert bundle.selectors["selectors"][0]["label"] == "Your Orders"
    assert any(
        selector.get("component_type") == "text_input"
        for selector in bundle.selectors["selectors"]
    )

    manager.update_run_state(
        bundle,
        status="completed",
        reason="Done",
        last_screen_id=screen_id,
        action_history=[],
        failure_count=0,
    )
    assert "Status: completed" in (bundle.app_dir / "memory.md").read_text(encoding="utf-8")


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
