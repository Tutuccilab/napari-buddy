"""
napari widget to create and save a buddy pipeline config (.json).

The saved file is buddy's config layout (buddy >= 0.6: one block per pipeline step, see buddy/config.py and
config_files/config_example.json):

    {
      "inputdir":  "...",
      "outputdir": "...",
      "if_already_processed": "ask",       # re-running a step: "ask" | "skip" | "overwrite"
      "channels": {                        # step 1
          "ASH1CLB2": {"filter": "CY5",  "mrna": "ASH1CLB2", "colormap": "red",  "threshold": 50},
          "DAPI":     {"filter": "DAPI", "mrna": "DAPI",     "colormap": "blue"}
      },
      "spots": {                           # step 3; decomposition (Big-FISH alpha, beta, gamma) is the same for every channel
          "scale": [200, 65, 65], "spot_radius": [800, 120, 120], "sigma": [0.75, 2.3, 2.3], "patch_size": [200, 200],
          "decomposition": {"alpha": 0.5, "beta": 2, "gamma": 1}
      },
      "segmentation": {                    # step 2: Omnipose (the Omnipose tab) + the clean-up (General tab)
          "organism": "S.cerevisiae", "cell_model": "cyto2_omni", "nucleus_model": "nuclei", "tile": false,
          "min_size": 10, "nuclei_min_size": 10,
          "use_preset": true,              # true: the organism's Omnipose settings, cells / nuclei only show them
          "cells": {"diameter": 50, "mask_threshold": -3, "flow_threshold": 1},
          "nuclei": {"diameter": 0, "mask_threshold": 0, "flow_threshold": 0},
          "min_cell_area": 20, "expand_px": 0, "remove_edge_cells": true
      },
      "hardware": {"use_gpu": true, "gpu_spot_detection": true},
      "bud_classification": {"enabled": true, "model": "DIC_DAPI_only", "ash_channel": "ASH1CLB2",
                             "overwrite_manual_corrections": false}
    }

``build_config`` / ``save_config`` are plain functions so a config can also be
created from a script or notebook without opening napari.
"""
import json
from pathlib import Path

from magicgui.widgets import (
    CheckBox,
    ComboBox,
    Container,
    FileEdit,
    FloatSpinBox,
    Label,
    LineEdit,
    PushButton,
    SpinBox,
)

ORGANISMS = ["S.cerevisiae", "E.coli"]
BUD_MODELS = ["DIC_DAPI_only", "with_ASH1CLB2"]
IF_PROCESSED = ["ask", "skip", "overwrite"]
COLORMAPS = ["gray", "red", "green", "blue", "magenta", "cyan", "yellow", "gold", "lime", "orange"]
# the Omnipose presets of buddy (buddy/config.py), shown as the starting values of the Omnipose tab
try:
    from buddy.config import (
        OMNIPOSE_NUCLEUS_PRESET,
        OMNIPOSE_PRESETS,
        SEGMENTATION_DEFAULTS,
    )
except ImportError:                                 # buddy < 0.5.0: no "segmentation" block
    OMNIPOSE_PRESETS, OMNIPOSE_NUCLEUS_PRESET, SEGMENTATION_DEFAULTS = None, None, None


# ----------------------------------------------------------------------
# pure helpers (usable without napari)
# ----------------------------------------------------------------------
def _number(v):
    """A spin box value as int when it is a whole number (so the file says 2, not 2.0)."""
    v = float(v)
    return int(v) if v.is_integer() else v


def _parse_numbers(text, cast=float):
    """'200, 65,65' -> [200.0, 65.0, 65.0]; empty entries are dropped."""
    return [cast(x) for x in str(text).replace(" ", "").split(",") if x != ""]


def build_config(inputdir, outputdir, organism, patch_size, sigma, scale,
                 spot_radius, channels, min_cell_area=20, expand_px=0, remove_edge_cells=False,
                 use_gpu=True, gpu_spot_detection=True, bud_classification=None,
                 if_already_processed="ask", segmentation=None, decomposition=None):
    """
    Assemble the config dict (buddy's file layout: one block per step).

    channels : iterable of (mrna, filter, colormap, threshold)
        Rows with an empty mrna are skipped. A blank/None threshold is omitted
        (Experiment then treats it as None).
    bud_classification : dict ("enabled", "model", "ash_channel", ...) or None (block left out)
    segmentation : the Omnipose part of the "segmentation" block ("cell_model", "nucleus_model", "tile", "min_size",
        "nuclei_min_size", "use_preset", "cells", "nuclei"; the Omnipose tab) or None (buddy's defaults, see buddy/config.py)
    decomposition : {"alpha", "beta", "gamma"} of Big-FISH's decompose_dense, the same for every channel, or None (left out)
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
        "channels": ch_dict,
        "segmentation": {
            "organism": organism,
            **(segmentation or {}),
            "min_cell_area": int(min_cell_area),
            "expand_px": int(expand_px),
            "remove_edge_cells": bool(remove_edge_cells),
        },
        "spots": {
            "scale": _parse_numbers(scale, float),
            "spot_radius": _parse_numbers(spot_radius, float),
            "sigma": _parse_numbers(sigma, float),
            "patch_size": [int(v) for v in _parse_numbers(patch_size, float)],
            **({"decomposition": dict(decomposition)} if decomposition else {}),
        },
        "hardware": {"use_gpu": bool(use_gpu), "gpu_spot_detection": bool(gpu_spot_detection)},
    }
    if bud_classification is not None:
        cfg["bud_classification"] = {"overwrite_manual_corrections": False, **bud_classification}
    return cfg


def save_config(path, cfg):
    """
    Write cfg to path as JSON, forcing a .json suffix. Returns the Path.
    The file looks like buddy's config_example.json: every block written out (the ones the panel has no fields
    for - cell_cycle, tiff_input, experiments - with their defaults), in the same order, with the example's
    "_about" comment lines, so a config made here is self-explanatory when opened later.
    """
    out = Path(str(path))
    if out.suffix.lower() != ".json":
        out = out.with_suffix(".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        from buddy.config import to_json
        text = to_json(full_layout(cfg))
    except ImportError:                                 # buddy < 0.6
        text = json.dumps(cfg, indent=2, ensure_ascii=False)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return out


def full_layout(cfg):
    """cfg (the blocks of build_config) completed with buddy's defaults and the comments of config_example.json."""
    from buddy.config import example_config, file_layout, validate
    example = example_config()
    full = file_layout(validate(json.loads(json.dumps(cfg))))      # validate works on a copy: cfg stays as built
    out = {k: v for k, v in example.items() if k.startswith("_")}  # the top-level comments first
    out["_about"] = ("buddy config made with napari-buddy's Create config file: one block per step, every setting "
                     "written out (explained in TUTORIAL.md, section 5)")
    for key, value in full.items():
        if isinstance(value, dict) and isinstance(example.get(key), dict):
            comments = {k: v for k, v in example[key].items() if k.startswith("_")}
            value = {**comments, **value}
        out[key] = value
    out["experiments"] = cfg.get("experiments", [])                # the example's strains are not this experiment's
    return out


# ----------------------------------------------------------------------
# napari widget
# ----------------------------------------------------------------------
def config_widget():
    """Fill in the fields and save a buddy config .json."""
    from ._pipeline_widget import example_paths
    example = example_paths()                          # the example set, when buddy's repo is next to this one
    inputdir  = FileEdit(label="input dir",  mode="d", value=example.get("inputdir", ""))
    outputdir = FileEdit(label="output dir", mode="d", value=example.get("outputdir", ""))
    organism  = ComboBox(label="organism", choices=ORGANISMS, value=ORGANISMS[0])

    patch_size  = LineEdit(label="patch_size (y,x)",        value="200,200")
    sigma       = LineEdit(label="sigma (z,yx,yx)",         value="0.75,2.3,2.3")
    scale       = LineEdit(label="scale nm (z,yx,yx)",      value="200,65,65")
    spot_radius = LineEdit(label="spot_radius nm (z,yx,yx)", value="800,120,120")
    # decomposition of dense regions (Big-FISH decompose_dense), the same for every channel
    decomposition = {"alpha": FloatSpinBox(label="alpha: molecule intensity / reference spot", value=0.5, min=0, max=1, step=0.05),
                     "beta": FloatSpinBox(label="beta: dense region >= beta x reference spot", value=2, min=0, max=100, step=0.5),
                     "gamma": FloatSpinBox(label="gamma: denoising filter width (x spot radius)", value=1, min=0, max=10, step=0.5)}

    header = Label(value="Channels (in order of acquisition):  mRNA | filter | colormap | threshold (blank = automatic)")
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

    # ---- Omnipose tab: the "segmentation" block (buddy >= 0.5.0) ----------------------------------
    omni = _omnipose_tab(organism)

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
                               if_already_processed=if_processed.value, segmentation=omni.block(),
                               decomposition={k: _number(w.value) for k, w in decomposition.items()})
            if not cfg["channels"]:
                status.value = "add at least one channel with an mRNA name"
                return
            out = save_config(save_path.value, cfg)
            status.value = f"saved: {out}"
        except Exception as e:  # noqa: BLE001 - surface the error in the widget instead of crashing
            status.value = f"error: {e}"

    save_path = FileEdit(label="save as", mode="w", filter="*.json")
    save_btn  = PushButton(text="Save config")
    status    = Label(value="")

    save_btn.clicked.connect(_on_save)

    main = Container(
        widgets=[
            inputdir, outputdir, organism,
            header, channels_box, add_btn,
            Label(value="Mask clean-up (step 2)"), min_cell_area, expand_px, remove_edge,
            Label(value="GPU"), use_gpu, gpu_spots,
            Label(value="Bud classification"), bud_enabled, bud_model, ash_channel,
            Label(value="Re-running steps"), if_processed,
        ],
        layout="vertical",
    )
    spots_tab = Container(
        widgets=[Label(value="Spot detection (step 3) - the \"spots\" block of the config file"),
                 patch_size, sigma, scale, spot_radius,
                 Label(value="Decomposition of dense regions (the same for every channel)"), *decomposition.values(),
                 Label(value="Find sigma, scale, spot_radius and the thresholds with Plugins > Napari Buddy > Spot tuning.")],
        layout="vertical")
    bottom = Container(widgets=[save_path, save_btn, status], layout="vertical")

    # three tabs (General; Spots = the "spots" block; Omnipose = the Omnipose part of "segmentation") above one save
    # row; each tab scrolls, so the panel fits on a small screen and with many channel rows
    from qtpy.QtWidgets import QTabWidget, QVBoxLayout, QWidget
    tabs = QTabWidget()
    tabs.addTab(_scrolled(main.native), "General")
    tabs.addTab(_scrolled(spots_tab.native), "Spots")
    tabs.addTab(_scrolled(omni.container.native), "Omnipose")
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(tabs)
    layout.addWidget(bottom.native)
    panel._magicgui = (main, spots_tab, omni.container, bottom)      # keep the magicgui widgets alive
    return panel


def _scrolled(native):
    """A tab page with a vertical scroll bar: the widget at the top, scrolling when taller than the dock."""
    from qtpy.QtCore import Qt
    from qtpy.QtWidgets import QScrollArea

    from ._tabs import _packed
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    area.setWidget(_packed(native))
    return area


class _omnipose_tab:
    """
    The Omnipose part of the "segmentation" block: models, tiling, the smallest cell / nucleus and the main Omnipose
    settings of the cells and the nuclei. The fields start at buddy's presets (for the organism chosen on the
    General tab); block() returns the cells / nuclei settings only where they differ from them, so a config made
    here stays small and follows buddy's defaults otherwise.
    """
    CELL_KEYS = ("diameter", "mask_threshold", "flow_threshold")
    NUCLEUS_KEYS = ("diameter", "mask_threshold", "flow_threshold")
    _TUNE = "uncheck to tune the cells / nuclei settings below (saved as use_preset false)"

    def __init__(self, organism_box):
        defaults = SEGMENTATION_DEFAULTS or {"cell_model": "cyto2_omni", "nucleus_model": "nuclei", "tile": False}
        self.organism_box = organism_box
        self.cell_model = LineEdit(label="cell model", value=defaults["cell_model"])
        self.nucleus_model = LineEdit(label="nucleus model", value=defaults["nucleus_model"])
        self.tile = CheckBox(text="tile: run the networks on tiles (less GPU memory; set on 'CUDA out of memory')",
                             value=bool(defaults["tile"]))
        self.min_size = SpinBox(label="min_size: smallest cell (px)", value=10, min=0, max=100000)
        self.nuclei_min_size = SpinBox(label="nuclei_min_size: smallest nucleus (px)", value=10, min=0, max=100000)
        self.use_preset = CheckBox(text="use the organism's preset (General tab) - " + self._TUNE, value=True)
        self.cells = {k: FloatSpinBox(label=f"cells: {k}", min=-10, max=10000, step=0.5) for k in self.CELL_KEYS}
        self.nuclei = {k: FloatSpinBox(label=f"nuclei: {k}", min=-10, max=10000, step=0.5) for k in self.NUCLEUS_KEYS}
        self.reset_btn = PushButton(text="reset to buddy's presets")
        self.reset_btn.clicked.connect(lambda *_: self.reset())
        self.container = Container(
            widgets=[Label(value="Omnipose (step 2) - the \"segmentation\" block of the config file"),
                     self.cell_model, self.nucleus_model, self.tile, self.min_size, self.nuclei_min_size,
                     self.use_preset,
                     Label(value="Cells"), *self.cells.values(),
                     Label(value="Nuclei"), *self.nuclei.values(),
                     self.reset_btn,
                     Label(value="Other Omnipose settings: edit the saved file (buddy/config.py lists them).")],
            layout="vertical")
        self.reset()
        self._lock()
        organism_box.changed.connect(lambda *_: self.reset())
        self.use_preset.changed.connect(lambda *_: self._lock())

    def _lock(self):
        """The cells / nuclei fields follow the preset while use_preset is on (and show its values)."""
        on = bool(self.use_preset.value)
        if on:
            self.reset()
        for w in (*self.cells.values(), *self.nuclei.values(), self.reset_btn):
            w.enabled = not on

    def presets(self):
        organism = self.organism_box.value
        cells = (OMNIPOSE_PRESETS or {}).get(organism) or {"diameter": 50, "mask_threshold": -3, "flow_threshold": 1}
        nuclei = OMNIPOSE_NUCLEUS_PRESET or {"diameter": 0, "mask_threshold": 0, "flow_threshold": 0}
        return cells, nuclei

    def reset(self):
        cells, nuclei = self.presets()
        for k, w in self.cells.items():
            w.value = float(cells[k])
        for k, w in self.nuclei.items():
            w.value = float(nuclei[k])

    def block(self):
        """
        The "segmentation" block as config_example.json has it: models, tile, min sizes, use_preset and the three
        cells / nuclei settings (the preset's values while use_preset is on; buddy ignores them then).
        """
        return {"cell_model": self.cell_model.value.strip(), "nucleus_model": self.nucleus_model.value.strip(),
                "tile": bool(self.tile.value), "min_size": int(self.min_size.value), "nuclei_min_size": int(self.nuclei_min_size.value),
                "use_preset": bool(self.use_preset.value),
                "cells": {k: _number(w.value) for k, w in self.cells.items()},
                "nuclei": {k: _number(w.value) for k, w in self.nuclei.items()}}
