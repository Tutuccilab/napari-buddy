"""The E. coli example data of the File -> Open Sample menu (downloaded from Zenodo: needs internet, slow)."""
import pytest

from napari_buddy._sample_data import smRNAfish_Ecoli_rpoD_rnlAB_hipBA


@pytest.mark.slow
def test_smRNAfish_Ecoli_rpoD_rnlAB_hipBA():
    layers = smRNAfish_Ecoli_rpoD_rnlAB_hipBA(cleanup=False)
    assert isinstance(layers, list) and layers
