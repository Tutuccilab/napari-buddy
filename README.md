# napari-buddy

The napari GUI companion to [buddy](https://github.com/Tutuccilab/buddy). It
provides napari widgets to drive the buddy smFISH pipeline interactively: build
a pipeline config file, read in raw VSI images, tune spot detection (background
filtering → detection → thresholding → decomposition) with live sliders, load
buddy results (`img.json`) as layers, and correct mother/bud assignments by
hand.

# Donwload code and example data
Go to https://doi.org/10.5281/zenodo.22900927 to dowload napari, napari-buddy and some test data. 
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

## Usage

Launch napari with the plugin installed:

    python -m napari

The plugin's widgets appear under **Plugins → Napari Buddy**:

- **Create config file** — build and save a buddy pipeline config (`.json`).
- **Read in VSI file** — load a raw VSI image (DIC + channels) into napari.
- **Filter / Detect / Threshold / Decompose spots** — tune spot-detection
  parameters interactively before running batch detection in buddy.
- **Open data** — load a buddy result (`img.json`) as layers (DIC,
  cell/nucleus masks, fluorescence channels, detected/decomposed spots).
- **Reassign buds to mothers** — draw lines to link buds to their mother cells.

## Contributing

Contributions are welcome. Run the tests with [pytest]; please keep coverage at
least the same before submitting a pull request.

## Citation

If you use napari-buddy in your research, please cite it via the archived
release — see `CITATION.cff` or the Zenodo DOI (add the DOI badge here once
minted).

## License

Distributed under the terms of the [BSD-3] license. napari-buddy is free and
open source software.

## Issues

If you encounter a problem, please [file an issue] with a detailed description.

[napari]: https://github.com/napari/napari
[pytest]: https://docs.pytest.org/
[BSD-3]: http://opensource.org/licenses/BSD-3-Clause
[file an issue]: https://github.com/USERNAME/napari-buddy/issues
