"""The reader: opening an image folder processed by buddy gives the layers napari-buddy shows."""
import numpy as np

from napari_buddy import napari_get_reader

CHANNELS = ("ASH1CLB2", "SRL1", "SUN4")   # the smFISH channels of the test field


def test_get_reader_pass():
    """files that are not buddy's img.json are left to other readers"""
    assert napari_get_reader("fake.file") is None


def test_reader_opens_a_processed_image(processed_field):
    """img.json after step 3: images, masks and, per channel, the stack, the filtered stack and the spots"""
    path = str(processed_field / "img.json")
    reader = napari_get_reader(path)
    assert callable(reader)
    layers = reader(path)
    assert isinstance(layers, list) and layers
    assert all(isinstance(t, tuple) and len(t) == 3 for t in layers)
    names = {kwargs["name"]: (data, kind) for data, kwargs, kind in layers}

    for name in ("DIC", "DAPI", "DIC masks", "DAPI masks"):
        assert name in names, f"layer {name!r} missing; got {sorted(names)}"
    assert names["DIC masks"][1] == "labels"
    for ch in CHANNELS:
        assert ch in names and f"{ch} background filtered" in names, f"{ch}: stack layers missing"
        spot_layers = [n for n in names if n.startswith(f"{ch} spots detected")]
        assert spot_layers, f"{ch}: no spot layer"
        spots, kind = names[spot_layers[0]]
        assert kind == "points"
        saved = np.load(processed_field / f"{ch}_spots.npy")
        assert len(spots) == len(saved), f"{ch}: {len(spots)} spots shown, {len(saved)} detected by buddy"


def test_reader_spots_match_the_reference(processed_field, field_a):
    """the spots napari shows are the ones buddy 0.1.0 found on this field (the regression reference)"""
    for ch in CHANNELS:
        got = np.load(processed_field / f"{ch}_spots.npy")
        want = np.load(field_a / "reference" / "step3" / f"{ch}_spots.npy")
        assert got.shape == want.shape, f"{ch}: {len(got)} spots, reference {len(want)}"


def test_fluorescence_channels_open_with_tight_contrast(processed_field):
    """raw and filtered channels: limits well inside the data range, which stays the slider range"""
    path = str(processed_field / "img.json")
    layers = {kw["name"]: (data, kw) for data, kw, kind in napari_get_reader(path)(path) if kind == "image"}
    for ch in CHANNELS:
        for name in (ch, f"{ch} background filtered"):
            data, kw = layers[name]
            low, high = kw["metadata"]["display_limits"]
            assert kw["contrast_limits"] == [float(data.min()), float(data.max())]
            assert data.min() <= low < high < data.max()
    assert "display_limits" not in layers["DIC"][1]["metadata"]          # DIC and DAPI keep napari's default
