"""The cell-cycle layers: buddy's cell_cycle.csv (buddy >= 0.3.0) shown as coloured cells + text."""
import numpy as np
import pandas as pd

from napari_buddy._reader import PHASE_COLOURS, cell_cycle_layer_data


def _field(tmp_path, phases):
    mask = np.zeros((60, 60), np.int32)
    for i, _ in enumerate(phases, start=1):
        mask[5:15, 10 * i - 8:10 * i - 1] = i
    pd.DataFrame({"image_cell_id": range(1, len(phases) + 1), "cell_cycle_phase": phases,
                  "why": [f"reason {p}" for p in phases]}).to_csv(tmp_path / "cell_cycle.csv", index=False)
    return mask


def test_only_budded_phases_are_coloured(tmp_path):
    mask = _field(tmp_path, ["G1", "S", "G2", "M", "NA"])
    (phase_map, kwargs, kind), (centres, text_kwargs, text_kind) = cell_cycle_layer_data(tmp_path, mask)
    assert kind == "labels" and text_kind == "points"
    assert kwargs["metadata"]["group"] == text_kwargs["metadata"]["group"] == "cellcycle"
    codes = {p: i for i, p in enumerate(PHASE_COLOURS, start=1)}
    for label, phase in enumerate(["G1", "S", "G2", "M", "NA"], start=1):
        assert set(np.unique(phase_map[mask == label])) == {codes.get(phase, 0)}, phase
    assert text_kwargs["features"]["cell_cycle_phase"].tolist() == ["S", "G2", "M"]
    assert len(centres) == 3


def test_nothing_without_the_file_or_budded_cells(tmp_path):
    mask = np.ones((10, 10), np.int32)
    assert cell_cycle_layer_data(tmp_path, mask) == []                     # no cell_cycle.csv (older buddy)
    mask = _field(tmp_path, ["G1", "unbudded"])
    assert cell_cycle_layer_data(tmp_path, mask) == []
