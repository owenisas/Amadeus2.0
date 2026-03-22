from __future__ import annotations

import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from agent_runner.models import BoundingBox, ScreenState


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp_slug() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
    return digest.hexdigest()


def extract_visible_text(xml_source: str) -> tuple[list[str], list[str]]:
    visible: list[str] = []
    clickable: list[str] = []
    try:
        root = ET.fromstring(xml_source)
    except ET.ParseError:
        return visible, clickable
    for node in root.iter():
        text = _element_text(node)
        if text:
            visible.append(text)
        if node.attrib.get("clickable") == "true":
            clickable_label = text or _descendant_text(node)
            if clickable_label:
                clickable.append(clickable_label)
    return dedupe_keep_order(visible), dedupe_keep_order(clickable)


def extract_ui_components(
    xml_source: str,
    *,
    width: int,
    height: int,
) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_source)
    except ET.ParseError:
        return components
    for node in root.iter():
        component_type = _component_type(node)
        if component_type is None:
            continue
        label = _element_text(node) or _descendant_text(node)
        bounds = _parse_bounds(node.attrib.get("bounds", ""))
        component: dict[str, Any] = {
            "component_type": component_type,
            "class_name": node.attrib.get("class", ""),
            "resource_id": node.attrib.get("resource-id", ""),
            "package_name": node.attrib.get("package", ""),
            "label": label,
            "enabled": node.attrib.get("enabled") == "true",
            "clickable": node.attrib.get("clickable") == "true",
            "focused": node.attrib.get("focused") == "true",
            "search_related": _is_search_related(node, label),
        }
        if bounds is not None:
            component["target_box"] = normalize_box(bounds, width=width, height=height).to_dict()
        components.append(component)
    return _dedupe_components(components)


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def _element_text(node: ET.Element) -> str:
    return (node.attrib.get("text") or node.attrib.get("content-desc") or "").strip()


def _descendant_text(node: ET.Element) -> str:
    texts: list[str] = []
    for child in node.iter():
        text = _element_text(child)
        if text:
            texts.append(text)
    return " | ".join(dedupe_keep_order(texts[:4]))


def _component_type(node: ET.Element) -> str | None:
    class_name = node.attrib.get("class", "")
    if "EditText" in class_name or node.attrib.get("editable") == "true":
        return "text_input"
    if node.attrib.get("clickable") != "true":
        return None
    label = (_element_text(node) or _descendant_text(node)).casefold()
    if _is_search_related(node, label):
        return "search_action"
    if any(token in class_name for token in ["Button", "ImageButton", "CheckBox", "Switch"]):
        return "button"
    if label:
        return "touch_target"
    return None


def _parse_bounds(raw_bounds: str) -> BoundingBox | None:
    match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", raw_bounds.strip())
    if not match:
        return None
    left, top, right, bottom = (int(value) for value in match.groups())
    return BoundingBox(
        x=float(left),
        y=float(top),
        width=float(max(0, right - left)),
        height=float(max(0, bottom - top)),
    )


def _is_search_related(node: ET.Element, label: str) -> bool:
    combined = " ".join(
        filter(
            None,
            [
                label,
                node.attrib.get("resource-id", ""),
                node.attrib.get("content-desc", ""),
                node.attrib.get("hint", ""),
            ],
        )
    ).casefold()
    return any(token in combined for token in ["search", "find", "query", "apps & games", "搜索"])


def _dedupe_components(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for component in components:
        key = (
            component.get("component_type", ""),
            component.get("resource_id", ""),
            component.get("label", "").casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(component)
    return deduped


def normalize_box(box: BoundingBox, width: int, height: int) -> BoundingBox:
    return BoundingBox(
        x=box.x / width,
        y=box.y / height,
        width=box.width / width,
        height=box.height / height,
    ).clamp()


def denormalize_box(box: BoundingBox, width: int, height: int) -> BoundingBox:
    return BoundingBox(
        x=box.x * width,
        y=box.y * height,
        width=box.width * width,
        height=box.height * height,
    )


def describe_state_signature(state: ScreenState) -> dict[str, Any]:
    text_digest = hashlib.sha256(
        "\n".join(sorted([token.casefold() for token in state.visible_text[:30]])).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "package_name": state.package_name,
        "activity_name": state.activity_name,
        "text_digest": text_digest,
        "top_visible_text": state.visible_text[:10],
        "clickable_text": state.clickable_text[:10],
        "screenshot_sha256": state.screenshot_sha256[:16],
    }


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "screen"


def dump_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))
