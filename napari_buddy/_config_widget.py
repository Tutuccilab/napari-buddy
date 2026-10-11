"""
napari widget to create and save a buddy pipeline config (.json).

The saved file matches what ``buddy.experiment.Experiment.from_cfg_file``
expects:

    {
      "inputdir":  "...",
      "outputdir": "...",
      "if_already_processed": "ask",       # re-running a step: "ask" | "skip" | "overwrite"
      "parameters": {
          "organism":    "S.cerevisiae",     # or "E.coli"
          "patch_size":  [200, 200],         # focus patch (y, x)
          "sigma":       [0.75, 2.3, 2.3],   # background gaussian (z, yx, yx)
          "scale":       [200, 65, 65],      # voxel size nm (z, yx, yx)
          "spot_radius": [800, 120, 120],    # object radius nm (z, yx, yx)
          "min_cell_area": 20,               # step 2: remove cells smaller than this (px)
          "expand_px": 0,                    # step 2: grow cells by this many px
          "remove_edge_cells": true,         # step 2: remove cells touching the image edge
          "use_gpu": true,                   # Omnipose + bud model on the GPU (if available)
          "gpu_spot_detection": true         # background filter, spot detection, decomposition on the GPU
      },
      "bud_classification": {"enabled": true, "model": "DIC_DAPI_only", "ash_channel": "ASH1CLB2",
                             "overwrite_manual_corrections": false},
      "channels": {
          "ASH1CLB2": {"filter": "CY5",  "mrna": "ASH1CLB2", "colormap": "red",  "threshold": 50},
          "DAPI":     {"filter": "DAPI", "mrna": "DAPI",     "colormap": "blue"}
      }
    }

``build_config`` / ``save_config`` are plain functions so a config can also be
created from a script or notebook without opening napari.
"""
import json
from pathlib import Path

from magicgui.widgets import (
    Container, PushButton, Label, LineEdit, FileEdit, ComboBox, CheckBox, SpinBox,
)

ORGANISMS = ["S.cerevisiae", "E.coli"]
BUD_MODELS = ["DIC_DAPI_only", "with_ASH1CLB2"]
IF_PROCESSED = ["ask", "skip", "overwrite"]
COLORMAPS = ["gray", "red", "green", "blue", "magenta", "cyan", "yellow", "gold", "lime", "orange"]


# ----------------------------------------------------------------------
# pure helpers (usable without napari)
# ----------------------------------------------------------------------
def _parse_numbers(text, cast=float):
    """'200, 65,65' -> [200.0, 65.0, 65.0]; empty entries are dropped."""
    return [cast(x) for x in str(text).replace(" ", "").split(",") if x != ""]


def build_config(inputdir, outputdir, organism, patch_size, sigma, scale,
                 spot_radius, channels, min_cell_area=20, expand_px=0, remove_edge_cells=False,
                 use_gpu=True, gpu_spot_detection=True, bud_classification=None,
                 if_already_processed="ask"):
    """
    Assemble the config dict.

    channels : iterable of (mrna, filter, colormap, threshold)
        Rows with an empty mrna are skipped. A blank/None threshold is omitted
        (Experiment then treats it as None).
    bud_classification : dict ("enabled", "model", "ash_channel", ...) or None (block left out)
    """
    ch_dict = {}
    for mrna, filt, colormap, threshold in channels:
        mrna = str(mrna).strip()
        if not mrna:
            continue
        entry = {"filter": str(filt).strip(), "mrna": mrna, "colormap": colormap}
        if threshold not in (None, "", "None"):
            entry["threshold"] = int(float(threshold))
        ch_dict[mrna] = entry

    cfg = {
        "inputdir": str(inputdir),
        "outputdir": str(outputdir),
        "if_already_processed": if_already_processed,
        "parameters": {
            "organism": organism,
            "patch_size": [int(v) for v in _parse_numbers(patch_size, float)],
            "sigma": _parse_numbers(sigma, float),
            "scale": _parse_numbers(scale, float),
            "spot_radius": _parse_numbers(spot_radius, float),
            "min_cell_area": int(min_cell_area),
            "expand_px": int(expand_px),
            "remove_edge_cells": bool(remove_edge_cells),
            "use_gpu": bool(use_gpu),
            "gpu_spot_detection": bool(gpu_spot_detection),
        },
        "channels": ch_dict,
    }
    if bud_classification is not None:
        cfg["bud_classification"] = {"overwrite_manual_corrections": False, **bud_classification}
    return cfg


def save_config(path, cfg):
    """Write cfg to path as JSON, forcing a .json suffix. Returns the Path."""
    out = Path(str(path))
    if out.suffix.lower() != ".json":
        out = out.with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(cfg, f, indent=2)
    return out


# ----------------------------------------------------------------------
# napari widget
# ----------------------------------------------------------------------
def config_widget():
    """Fill in the fields and save a buddy config .json."""
    inputdir  = FileEdit(label="input dir",  mode="d")
    outputdir = FileEdit(label="output dir", mode="d")
    organism  = ComboBox(label="organism", choices=ORGANISMS, value=ORGANISMS[0])

    patch_size  = LineEdit(label="patch_size (y,x)",        value="200,200")
    sigma       = LineEdit(label="sigma (z,yx,yx)",         value="0.75,2.3,2.3")
    scale       = LineEdit(label="scale nm (z,yx,yx)",      value="200,65,65")
    spot_radius = LineEdit(label="spot_radius nm (z,yx,yx)", value="800,120,120")

    header = Label(value="Channels (in order of acquisition):  mRNA | filter | colormap | threshold (blank = None)")
    channels_box = Container(layout="vertical", labels=False)
    rows = []  # list of dicts holding each row's widgets

    def _renumber():
        # the row order is the acquisition order that gets written to the config
        for i, e in enumerate(rows, 1):
            e["idx"].value = f"{i}."

    def add_channel(mrna="", filt="", colormap="green", threshold=""):
        w_idx  = Label(value="")
        w_mrna = LineEdit(value=mrna)
        w_filt = LineEdit(value=filt)
        w_cmap = ComboBox(choices=COLORMAPS,
                          value=colormap if colormap in COLORMAPS else "gray")
        w_thr  = LineEdit(value=str(threshold))
        w_del  = PushButton(text="remove")
        row = Container(widgets=[w_idx, w_mrna, w_filt, w_cmap, w_thr, w_del],
                        layout="horizontal", labels=False)
        entry = {"row": row, "idx": w_idx, "mrna": w_mrna, "filter": w_filt,
                 "cmap": w_cmap, "thr": w_thr}

        def _remove(*_):
            if row in list(channels_box):
                channels_box.remove(row)
            if entry in rows:
                rows.remove(entry)
            _renumber()

        w_del.clicked.connect(_remove)
        rows.append(entry)
        channels_box.append(row)
        _renumber()

    add_btn = PushButton(text="+ add channel")
    add_btn.clicked.connect(lambda *_: add_channel())

    # default channels, in order of acquisition
    add_channel("ASH1CLB2", "CY5",       "magenta", "50")
    add_channel("SRL1",     "CY3.5 NAR", "gold",    "50")
    add_channel("SUN4",     "CY3",       "lime",    "50")
    add_channel("DAPI",     "DAPI",      "blue",    "")

    # step 2 (segmentation) post-processing
    min_cell_area = SpinBox(label="min_cell_area (px)", value=20, min=0, max=100000)
    expand_px     = SpinBox(label="expand_px (px)", value=0, min=0, max=50)
    remove_edge   = CheckBox(text="remove cells touching the image edge", value=True)
    # GPU
    use_gpu       = CheckBox(text="use GPU for Omnipose and the bud model", value=True)
    gpu_spots     = CheckBox(text="use GPU for background filter, spot detection, decomposition", value=True)
    # automatic bud classification
    bud_enabled   = CheckBox(text="automatic bud classification", value=True)
    bud_model     = ComboBox(label="bud model", choices=BUD_MODELS, value=BUD_MODELS[0])
    ash_channel   = LineEdit(label="ASH1/CLB2 channel (with_ASH1CLB2 only)", value="ASH1CLB2")
    # re-running steps on images that were processed with other settings
    if_processed  = ComboBox(label="if already processed", choices=IF_PROCESSED, value="ask")

    save_path = FileEdit(label="save as", mode="w", filter="*.json")
    save_btn  = PushButton(text="Save config")
    status    = Label(value="")

    def _on_save(*_):
        try:
            channels = [(e["mrna"].value, e["filter"].value,
                         e["cmap"].value, e["thr"].value) for e in rows]
            bud = ({"enabled": True, "model": bud_model.value, "ash_channel": ash_channel.value}
                   if bud_enabled.value else {"enabled": False})
            cfg = build_config(inputdir.value, outputdir.value, organism.value,
                               patch_size.value, sigma.value, scale.value,
                               spot_radius.value, channels,
                               min_cell_area=min_cell_area.value, expand_px=expand_px.value,
                               remove_edge_cells=remove_edge.value, use_gpu=use_gpu.value,
                               gpu_spot_detection=gpu_spots.value, bud_classification=bud,
                               if_already_processed=if_processed.value)
            if not cfg["channels"]:
                status.value = "add at least one channel with an mRNA name"
                return
            out = save_config(save_path.value, cfg)
            status.value = f"saved: {out}"
        except Exception as e:  # surface the error in the widget instead of crashing
            status.value = f"error: {e}"

    save_btn.clicked.connect(_on_save)

    return Container(
        widgets=[
            inputdir, outputdir, organism,
            patch_size, sigma, scale, spot_radius,
            header, channels_box, add_btn,
            Label(value="Segmentation (step 2)"), min_cell_area, expand_px, remove_edge,
            Label(value="GPU"), use_gpu, gpu_spots,
            Label(value="Bud classification"), bud_enabled, bud_model, ash_channel,
            Label(value="Re-running steps"), if_processed,
            save_path, save_btn, status,
        ],
        layout="vertical",
    )
