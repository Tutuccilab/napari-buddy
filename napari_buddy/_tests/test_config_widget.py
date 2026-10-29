"""The Create config file panel: build_config writes one block per step; the Omnipose tab writes use_preset and the preset's values."""
import json

import pytest
from magicgui.widgets import ComboBox

from napari_buddy._config_widget import (
    _omnipose_tab,
    build_config,
    config_widget,
    save_config,
)


def test_build_config_writes_one_block_per_step():
    seg = {"cell_model": "cyto2_omni", "nucleus_model": "nuclei", "tile": True, "min_size": 12, "nuclei_min_size": 10,
           "use_preset": False, "cells": {"diameter": 40}, "nuclei": {}}
    cfg = build_config("in", "out", "S.cerevisiae", "200,200", "0.75,2.3,2.3", "200,65,65", "800,120,120",
                       [("DAPI", "DAPI", "blue", "")], segmentation=seg, remove_edge_cells=True, use_gpu=False,
                       decomposition={"alpha": 0.7, "beta": 2, "gamma": 1})
    assert cfg["segmentation"] == {"organism": "S.cerevisiae", **seg, "min_cell_area": 20, "expand_px": 0, "remove_edge_cells": True}
    assert cfg["spots"] == {"scale": [200, 65, 65], "spot_radius": [800, 120, 120], "sigma": [0.75, 2.3, 2.3], "patch_size": [200, 200],
                            "decomposition": {"alpha": 0.7, "beta": 2, "gamma": 1}}
    assert cfg["hardware"] == {"use_gpu": False, "gpu_spot_detection": True}
    assert "parameters" not in cfg
    pytest.importorskip("buddy.config")
    from buddy.config import (
        validate,  # what buddy makes of it: the same flat parameters as before
    )
    checked = validate(json.loads(json.dumps(cfg)))
    assert checked["parameters"]["min_size"] == 12 and checked["parameters"]["use_gpu"] is False
    assert checked["parameters"]["decomposition"] == {"alpha": 0.7, "beta": 2, "gamma": 1}
    assert checked["segmentation"] == {"cell_model": "cyto2_omni", "nucleus_model": "nuclei", "tile": True, "use_preset": False,
                                       "cells": {"diameter": 40}, "nuclei": {}}


def test_save_config_is_readable_and_complete(tmp_path):
    """The saved file has every block of config_example.json, its comments, and the panel's values."""
    cfg = build_config("in", "out", "S.cerevisiae", "200,200", "0.75,2.3,2.3", "200,65,65", "800,120,120",
                       [("DAPI", "DAPI", "blue", "")], segmentation={"tile": True})
    text = save_config(tmp_path / "c", cfg).read_text(encoding="utf-8")
    saved = json.loads(text)
    assert '"scale": [200.0, 65.0, 65.0]' in text and saved["spots"]["scale"] == [200, 65, 65]
    assert saved["segmentation"]["tile"] is True and saved["segmentation"]["use_preset"] is False
    pytest.importorskip("buddy.config")
    from buddy.config import example_config
    example = example_config()
    assert list(saved) == list(example)                                  # same blocks, same order
    assert "Create config file" in saved["_about"] and saved["segmentation"]["_about"] == example["segmentation"]["_about"]
    assert saved["cell_cycle"]["g1_max_ash"] == example["cell_cycle"]["g1_max_ash"]   # a block the panel has no fields for
    assert saved["experiments"] == []                                    # not the example's strains
    assert "cell_flags" not in saved


def test_omnipose_tab_use_preset(qapp):
    yeast = {"diameter": 50, "mask_threshold": -3, "flow_threshold": 1}
    organism = ComboBox(choices=["S.cerevisiae", "E.coli"], value="S.cerevisiae")
    tab = _omnipose_tab(organism)
    # as config_example.json: use_preset true and the preset's values spelled out, the fields locked
    assert tab.block() == {"cell_model": "cyto2_omni", "nucleus_model": "nuclei", "tile": False, "min_size": 10,
                           "nuclei_min_size": 10, "use_preset": True, "cells": yeast,
                           "nuclei": {"diameter": 0, "mask_threshold": 0, "flow_threshold": 0}}
    assert not tab.cells["diameter"].enabled
    organism.value = "E.coli"                      # presets of the other organism: the fields follow
    assert tab.block()["cells"]["diameter"] == 0
    organism.value = "S.cerevisiae"
    tab.use_preset.value = False                   # tuning: fields unlocked, use_preset false in the file
    assert tab.cells["diameter"].enabled
    tab.tile.value = True
    tab.cells["diameter"].value = 40
    assert tab.block()["tile"] is True and tab.block()["use_preset"] is False and tab.block()["cells"] == {**yeast, "diameter": 40}
    tab.use_preset.value = True                    # back to the preset: the values are reset
    assert tab.block()["cells"] == yeast and not tab.cells["diameter"].enabled


def test_config_widget_builds(qapp):
    panel = config_widget()
    assert panel.findChildren(type(panel)) is not None
