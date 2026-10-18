"""
Test data for napari-buddy: the same small field as buddy's own tests (field_A, a 512 x 512 px crop of a yeast
image with three smFISH channels, DAPI, DIC and Omnipose masks).

Where it comes from, in this order:
  1. the buddy repo next to this one (../buddy/tests/data/field_A), when you have both repos side by side;
  2. napari_buddy/_tests/data/field_A (downloaded here before);
  3. the GitHub release test-data-v2 of buddy (downloaded once into napari_buddy/_tests/data/).
Without it the tests that need it are skipped - or fail, when NAPARI_BUDDY_REQUIRE_TEST_DATA is set (GitHub workflow).
"""
import io
import json
import os
import shutil
import urllib.request
import zipfile
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
DATA_DIR = TESTS_DIR / "data"
SIBLING_FIELD = TESTS_DIR.parents[2] / "buddy" / "tests" / "data" / "field_A"
TEST_DATA_URL = "https://github.com/Tutuccilab/buddy/releases/download/test-data-v2/field_A.zip"
CHANNELS = ("ASH1CLB2", "SRL1", "SUN4")


def _find_field():
    for field in (SIBLING_FIELD, DATA_DIR / "field_A"):
        if (field / "img.json").is_file() and (field / "reference").is_dir():
            return field, None
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(TEST_DATA_URL, timeout=120) as r:
            zipfile.ZipFile(io.BytesIO(r.read())).extractall(DATA_DIR)
    except Exception as e:                                # no network, a private repository, ...
        return None, f"{type(e).__name__}: {e}"
    field = DATA_DIR / "field_A"
    return (field, None) if (field / "img.json").is_file() else (None, "the zip has no field_A/img.json")


@pytest.fixture(scope="session")
def field_a():
    """The test field (read-only: tests that run buddy work on a copy, see processed_field)."""
    field, error = _find_field()
    if field is None:
        message = f"test data (field_A) not available ({error}): put buddy next to napari-buddy, or allow the download"
        if os.environ.get("NAPARI_BUDDY_REQUIRE_TEST_DATA"):
            pytest.fail(message)
        pytest.skip(message)
    return field


@pytest.fixture(scope="session")
def processed_field(field_a, tmp_path_factory):
    """
    A copy of the test field after buddy's step 3 (spots, alignment, counting; on the CPU, bud model off),
    so that the reader has everything to show. Returns the image folder (with img.json).
    """
    from buddy import pipeline
    from buddy.experiment import Experiment
    root = tmp_path_factory.mktemp("buddy_run")
    folder = root / "output" / field_a.name
    shutil.copytree(field_a, folder, ignore=shutil.ignore_patterns("reference", "corrected", "manual"))
    cfg = json.loads((field_a / "config.json").read_text())
    cfg["inputdir"], cfg["outputdir"] = str(root / "input"), str(root / "output")
    cfg_file = root / "config.json"
    cfg_file.write_text(json.dumps(cfg, indent=1))
    meta = json.loads((folder / "img.json").read_text())
    meta["savepath"] = str(folder)
    (folder / "img.json").write_text(json.dumps(meta, indent=1))

    exp = Experiment.from_cfg_file(str(cfg_file))
    exp.use_gpu = False
    exp.parameters["use_gpu"] = False
    exp.parameters["gpu_spot_detection"] = False
    exp.bud_classification["enabled"] = False
    pipeline.spots_image(folder / "img.json", exp)
    pipeline.buds_and_counts(folder / "img.json", exp)
    return folder
