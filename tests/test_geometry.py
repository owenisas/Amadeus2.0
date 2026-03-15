from agent_runner.models import BoundingBox
from agent_runner.utils import denormalize_box, normalize_box


def test_normalize_and_denormalize_box_round_trip() -> None:
    pixel_box = BoundingBox(x=108, y=480, width=216, height=240)
    normalized = normalize_box(pixel_box, width=1080, height=2400)

    assert normalized.to_dict() == {
        "x": 0.1,
        "y": 0.2,
        "width": 0.2,
        "height": 0.1,
    }

    round_trip = denormalize_box(normalized, width=1080, height=2400)
    assert round_trip.to_dict() == pixel_box.to_dict()
