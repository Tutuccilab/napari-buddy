import json

from napari_buddy._pipeline_widget import Estimate, format_seconds, prior_seconds


def test_estimate_starts_from_prior_then_follows_measurements():
    e = Estimate({"a": (10, 10.0)})
    assert e.seconds_left() == 100
    e.restart_clock(now=0)
    for i in range(1, 9):                      # this run is 2x slower than the prior
        e.image_done("a", now=20 * i)
    assert e.seconds_per_image("a") == (2 * 10 + 8 * 20) / 10
    assert e.text().startswith("8/10")


def test_estimate_without_prior_waits_for_first_image():
    e = Estimate({"a": (3, None)})
    assert e.seconds_left() is None and "estimating" in e.text()
    e.restart_clock(now=0)
    e.image_done("a", now=5)
    assert e.seconds_left() == 10


def test_prior_seconds(tmp_path):
    for i, t in enumerate([10, 20, 30]):
        (tmp_path / f"{i}.json").write_text(json.dumps({"time": {"x": t, "y": 1, "mode": "serial"}}))
    assert prior_seconds(sorted(tmp_path.glob("*.json")), ["x", "y"]) == 21
    assert prior_seconds([], ["x"]) is None
    assert format_seconds(30) == "30 s" and format_seconds(600) == "10 min"
