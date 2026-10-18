# napari-buddy

[![tests](https://github.com/Tutuccilab/napari-buddy/actions/workflows/tests.yml/badge.svg)](https://github.com/Tutuccilab/napari-buddy/actions/workflows/tests.yml)

The napari GUI companion to [buddy](https://github.com/Tutuccilab/buddy). It
provides napari widgets to drive the buddy smFISH pipeline interactively: build
a pipeline config file, read in raw VSI images, tune spot detection (background
filtering → detection → thresholding → decomposition) with live sliders, load
buddy results (`img.json`) as layers, and correct mother/bud assignments by
hand.

# Download code and example data
Go to https://doi.org/10.5281/zenodo.22900927 to download napari, napari-buddy and some test data. 
The folder structure of the zipped file should allow you to directly start with the tutorial after installation.
Note: newer versions of the code can be downloaded by cloning this repo.

## Installation

`napari-buddy` depends on **buddy** (not on PyPI), so install buddy **first**,
then this plugin, into the same conda environment:

    # in your activated buddy env, from the buddy repo root:
    python -m pip install -e ".[test,napari,notebooks]"

    # then, from this plugin's repo root:
    python -m pip install -e .

Requires Python 3.9–3.10 (not 3.11+, because buddy's omnipose dependency is
capped there). Use `python -m pip` so the install lands in the active env.
See the [buddy](https://github.com/Tutuccilab/buddy) install guide for the full
environment setup and troubleshooting.

**Versions:** napari-buddy 0.2.0 works with buddy 0.1.0 up to 0.3.x (the cell-cycle layer needs buddy 0.3.0). Both packages warn when the other one is too old
or too new; update both with `git pull` and `python -m pip install -e .` in each repo.

## Usage

Launch napari with the plugin installed:

    python -m napari

The plugin's widgets appear under **Plugins → Napari Buddy**:

- **buddy pipeline** — run the whole buddy pipeline from napari: choose a config file (or **Create config
  file...**) and the input / output folders, then press the steps in order: 1 Read, 2 Segment, 3 Spots + buds,
  4 Check and correct (opens the Correct images panel), 5 Reassign spots; **Run 1-3** runs the automatic steps one
  after the other. Starting a step closes the layers in napari to free memory. Steps run in the background with a
  progress bar and a time estimate (from earlier runs, then from this run); **Stop after this image** stops a
  step cleanly. Images already processed with the same settings are skipped; for images processed with other
  settings a yes/no question lists what changed. Needs buddy installed in the same environment.
- **Create config file** — build and save a buddy pipeline config (`.json`): channels, detection
  parameters, segmentation post-processing, GPU use, bud classification and re-run behaviour.
- **Read in VSI file** — load a raw VSI image (DIC + channels) into napari.
- **Filter / Detect / Threshold / Decompose spots** — tune spot-detection
  parameters interactively before running batch detection in buddy.
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
