"""
The spot-tuning panels (Filter out background, Detect spot, Threshold spots, Decompose spots) on a channel of the
test field: they must give the same result as buddy's pipeline functions, so that the settings you tune in napari
mean the same in the pipeline. Uses the ASH1CLB2 channel of field_A (41 x 512 x 512).

The panels only read and add layers, so the tests use napari's ViewerModel (the viewer without its window): no
OpenGL needed, which the GitHub Windows runners do not have.
"""
import json

import numpy as np
import pytest
import tifffile
from napari.components import ViewerModel

from napari_buddy._widget import (
    background_filtering_magic_widget,
    spot_decomposition_magic_widget,
    spot_detection_magic_widget,
    spot_thresholding_magic_widget,
)

CHANNEL = "ASH1CLB2"


def _detection():
    try:
        from buddy.spots import detection           # buddy >= 0.2.0
    except ImportError:
        pytest.skip("needs buddy >= 0.2.0 (buddy.spots.detection)")
    return detection


@pytest.fixture
def viewer(qapp):
    """the viewer without a window (qapp: magicgui builds the panels as Qt widgets)"""
    return ViewerModel()


@pytest.fixture(scope="module")
def settings(field_a):
    p = json.loads((field_a / "config.json").read_text())["parameters"]
    return {"sigma": tuple(p["sigma"]), "scale": tuple(p["scale"]), "spot_radius": tuple(p["spot_radius"])}


@pytest.fixture(scope="module")
def stack(field_a):
    return tifffile.imread(field_a / f"{CHANNEL}.tif")


@pytest.fixture(scope="module")
def filtered(stack, settings):
    """buddy's background filter on the whole stack"""
    detection = _detection()
    out, _ = detection.filter_background(stack, settings["sigma"])
    return out


def _detect(viewer, filtered, settings, threshold):
    layer = viewer.add_image(filtered, name=f"{CHANNEL} background filtered", metadata={"channel": CHANNEL})
    scale, radius = settings["scale"], settings["spot_radius"]
    return spot_detection_magic_widget()(viewer=viewer, img_layer=layer, threshold=threshold, scale_z=scale[0],
                                         scale_yx=scale[1], spot_radius_z=radius[0], spot_radius_yx=radius[1])


def _coordinates(spots):
    spots = np.asarray(spots)[:, :3].astype(int)
    return spots[np.lexsort(spots.T[::-1])]


def test_background_filter_panel_equals_pipeline(viewer, stack, filtered, settings):
    layer = viewer.add_image(stack, name=CHANNEL)
    data, kwargs, kind = background_filtering_magic_widget()(img_layer=layer, sigma_z=settings["sigma"][0],
                                                              sigma_yx=settings["sigma"][1])
    assert kind == "image" and kwargs["name"] == f"{CHANNEL} background filtered"
    assert np.abs(data.astype(np.int64) - filtered.astype(np.int64)).max() <= 1      # GPU vs CPU: rounding only


def test_spot_detection_panel_equals_pipeline(viewer, stack, filtered, settings):
    detection = _detection()
    (log, _, _), (mask, _, _), (spots, spot_kwargs, kind) = _detect(viewer, filtered, settings, threshold=50)
    assert kind == "points" and len(spots) > 0
    pipeline_spots, _, _ = detection.detect_spots(stack, filtered, 0, stack.shape[0], 50, settings["scale"],
                                                  settings["spot_radius"])
    assert np.array_equal(_coordinates(spots), _coordinates(pipeline_spots))


def test_thresholding_panel_equals_detecting_at_that_threshold(viewer, filtered, settings):
    """re-thresholding the detected spots at 100 gives the same spots as detecting at 100 directly"""
    (log, _, _), (mask, _, _), (spots50, kwargs50, _) = _detect(viewer, filtered, settings, threshold=50)
    viewer.add_image(log, name=f"{CHANNEL} LoG filtered")
    viewer.add_labels(mask.astype(np.uint8), name=f"{CHANNEL} local maxima")
    points = viewer.add_points(spots50, metadata=dict(kwargs50["metadata"]))
    rethresholded, _, _ = spot_thresholding_magic_widget()(viewer=viewer, img_layer=points, threshold=100)
    _, _, (spots100, _, _) = _detect(ViewerModel(), filtered, settings, threshold=100)
    assert 0 < len(rethresholded) < len(spots50)
    assert np.array_equal(_coordinates(rethresholded), _coordinates(spots100))


def test_decomposition_panel_equals_pipeline(viewer, stack, filtered, settings):
    """same number of decomposed spots and dense regions as buddy (positions inside a region are partly random)"""
    detection = _detection()
    viewer.add_image(stack, name=CHANNEL)
    _, _, (spots, kwargs, _) = _detect(viewer, filtered, settings, threshold=50)
    points = viewer.add_points(spots, metadata=dict(kwargs["metadata"]))
    result = spot_decomposition_magic_widget()(viewer=viewer, point_layer=points)
    dense_regions, decomposed = result[0][0], result[1][0]
    pipeline_decomposed, pipeline_dense, _, _ = detection.decompose_spots(stack, spots, settings["scale"],
                                                                          settings["spot_radius"])
    assert len(decomposed) == len(pipeline_decomposed)
    assert len(dense_regions) == len(pipeline_dense)
    assert len(decomposed) >= len(spots)
