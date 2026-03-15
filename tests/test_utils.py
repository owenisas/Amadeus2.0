from pathlib import Path

from agent_runner.models import DeviceInfo, ScreenState
from agent_runner.utils import describe_state_signature, extract_ui_components, extract_visible_text


def test_extract_visible_text_from_uiautomator_xml() -> None:
    xml = """
    <hierarchy>
      <node text="Your Orders" clickable="true" />
      <node text="" content-desc="Track package" clickable="false" />
      <node text="Your Orders" clickable="true" />
      <android.widget.LinearLayout clickable="true">
        <android.widget.TextView text="Network and internet" />
      </android.widget.LinearLayout>
    </hierarchy>
    """
    visible, clickable = extract_visible_text(xml)
    assert visible == ["Your Orders", "Track package", "Network and internet"]
    assert clickable == ["Your Orders", "Network and internet"]


def test_describe_state_signature_has_expected_fields() -> None:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.amazon.mShop.android.shopping",
        activity_name=".OrdersActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/example.png"),
        hierarchy_path=Path("/tmp/example.xml"),
        screenshot_sha256="abc123456789",
        xml_source="<hierarchy />",
        visible_text=["Your Orders", "Arriving tomorrow"],
        clickable_text=["Your Orders"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
    )
    signature = describe_state_signature(state)
    assert signature["package_name"] == device.package_name
    assert signature["activity_name"] == device.activity_name
    assert signature["screenshot_sha256"] == "abc123456789"


def test_extract_ui_components_finds_text_inputs_and_search_actions() -> None:
    xml = """
    <hierarchy>
      <node
        class="android.widget.EditText"
        text=""
        resource-id="com.android.vending:id/search_box"
        content-desc="Search apps &amp; games"
        clickable="true"
        enabled="true"
        focused="true"
        bounds="[10,20][210,120]" />
      <node
        class="android.widget.ImageButton"
        text=""
        resource-id="com.android.vending:id/search_go_btn"
        content-desc="Search"
        clickable="true"
        enabled="true"
        bounds="[220,20][320,120]" />
    </hierarchy>
    """
    components = extract_ui_components(xml, width=400, height=800)

    assert components[0]["component_type"] == "text_input"
    assert components[0]["search_related"] is True
    assert components[0]["target_box"] == {"x": 0.025, "y": 0.025, "width": 0.5, "height": 0.125}
    assert components[1]["component_type"] == "search_action"
