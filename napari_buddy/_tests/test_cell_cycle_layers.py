"""The cell-cycle layer: buddy's cell_cycle.csv (buddy >= 0.3.0) shown as the phase written on each cell."""
import numpy as np
import pandas as pd

from napari_buddy._reader import cell_cycle_layer_data


def _field(tmp_path, phases):
    mask = np.zeros((60, 60), np.int32)
    for i, _ in enumerate(phases, start=1):
        mask[5:15, 10 * i - 8:10 * i - 1] = i
    pd.DataFrame({"image_cell_id": range(1, len(phases) + 1), "cell_cycle_phase": phases,
                  "why": [f"reason {p}" for p in phases]}).to_csv(tmp_path / "cell_cycle.csv", index=False)
    return mask


def test_only_budded_phases_are_written(tmp_path):
    mask = _field(tmp_path, ["G1", "S", "G2", "M", "NA"])
    [(centres, kwargs, kind)] = cell_cycle_layer_data(tmp_path, mask)
    assert kind == "points" and kwargs["name"] == "cell cycle" and kwargs["metadata"]["group"] == "cellcycle"
    assert kwargs["features"]["cell_cycle_phase"].tolist() == ["S", "G2", "M"]
    for (y, x), label in zip(centres, [2, 3, 4]):                          # each text sits on its own cell
        assert mask[int(round(y)), int(round(x))] == label


def test_nothing_without_the_file_or_budded_cells(tmp_path):
    mask = np.ones((10, 10), np.int32)
    assert cell_cycle_layer_data(tmp_path, mask) == []                     # no cell_cycle.csv (older buddy)
    mask = _field(tmp_path, ["G1", "unbudded"])
    assert cell_cycle_layer_data(tmp_path, mask) == []
