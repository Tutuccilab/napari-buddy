# napari-buddy

[![tests](https://github.com/Tutuccilab/napari-buddy/actions/workflows/tests.yml/badge.svg)](https://github.com/Tutuccilab/napari-buddy/actions/workflows/tests.yml)

The napari GUI companion to [buddy](https://github.com/Tutuccilab/buddy). It
provides napari widgets to drive the buddy smFISH pipeline interactively: build
a pipeline config file, read in raw VSI images, tune spot detection (background
filtering → detection → thresholding → decomposition) with live sliders, load
buddy results (`img.json`) as layers, and correct mother/bud assignments by
hand.

## Installation

napari-buddy is installed together with buddy by buddy's installer (`install.ps1` on Windows, `install.sh` on
macOS / Linux, with this repo next to the buddy repo). How to install, GPU set-up and troubleshooting:
[buddy/INSTALL.md](https://github.com/Tutuccilab/buddy/blob/main/INSTALL.md). To install only the plugin into an
existing buddy environment: `python -m pip install -e .` from this folder.

**Versions:** napari-buddy 0.4.x needs buddy 0.6.x (0.3.x worked with buddy 0.3.0 up to 0.5.x). Both packages warn
when the other one is too old or too new; update both with `git pull` and `python -m pip install -e .` in each repo.

## Usage

Launch napari with the plugin installed:

    python -m napari

The plugin's widgets appear under **Plugins → Napari Buddy**:

- **buddy pipeline** — run the whole buddy pipeline from napari: choose a config file (the field starts at buddy's
  `config_files/config_example.json`, the example set; or **Create config file...**) and the input / output folders, then press the steps in order: 1 Read, 2 Segment, 3 Spots + buds,
  4 Check and correct (opens the Correct images panel), 5 Reassign spots; **Run 1-3** runs the automatic steps one
  after the other. Starting a step closes the layers in napari to free memory. Steps run in the background with a
  progress bar and a time estimate (from earlier runs, then from this run); **Stop after this image** stops a
  step cleanly. Images already processed with the same settings are skipped; for images processed with other
  settings a yes/no question lists what changed. Needs buddy installed in the same environment.
- **Create config file** — build and save a buddy pipeline config (`.json`, one block per step), on three tabs:
  **General** (folders, channels, mask clean-up, GPU use, bud classification, re-run behaviour), **Spots** (`patch_size`,
  `sigma`, `scale`, `spot_radius` and the decomposition settings `alpha`, `beta`, `gamma`) and **Omnipose** (the
  segmentation networks and their settings; *use the organism's preset* on = buddy's preset, off = tune them).
- **Read in VSI file** — load a raw VSI image (DIC + channels) into napari.
- **Filter / Detect / Threshold / Decompose spots** — tune spot-detection parameters interactively before running
  batch detection in buddy (Decompose has `alpha`, `beta`, `gamma`, the config's `spots.decomposition`).
- **Open data** — load a buddy result (`img.json`) as layers, grouped from bottom to top: DIC + DAPI,
  raw channels, filtered channels, spots, masks (cell, nucleus and bud masks, a `bud → mother links`
  layer with a line from each bud to its mother, and the `check these buds` boxes of the bud model) and, with
  buddy 0.3.0, the `cell cycle` layer (the phase S, G2 or M written on each budded cell).
- **Layer groups** — show / hide whole groups of layers (by type, including the cell-cycle phases, or by channel) at once.
- **Correct images** — choose the config file, then go through the images one after the other with
  previous / save / save + next / skip buttons (also from a buddy notebook: `review_images(exp)`).
- **Reassign buds to mothers** — draw lines to link buds to their mother cells; the
  `bud → mother links` layer updates after **Apply links** (saving also applies lines you drew).

## Tests

    python -m pip install -e ".[testing]"
    pytest -m "not slow"

The tests use buddy's test field (from the buddy repo next to this one, or downloaded from buddy's release
`test-data-v1`) and check the reader and that the spot-tuning panels give the same result as buddy's pipeline.
GitHub runs the tests on every push.

## License

Distributed under the terms of the [BSD-3] license. napari-buddy is free and
open source software.

## Issues

If you encounter a problem, please [file an issue] with a detailed description.

[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[file an issue]: https://github.com/Tutuccilab/napari-buddy/issues
