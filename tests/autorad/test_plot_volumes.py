import numpy as np
import pytest
from conftest import prostate_data
import plotly
from autorad.visualization.plot_volumes import BaseVolumes, plot_roi

image_path = prostate_data["img"]
mask_path = prostate_data["seg"]


@pytest.mark.parametrize("constant_bbox", [True, False])
def test_from_nifti(constant_bbox):
    volumes = BaseVolumes.from_nifti(
        image_path, mask_path, resample=True, constant_bbox=constant_bbox
    )
    assert volumes.image.shape == volumes.mask.shape
    assert np.sum(volumes.mask) > 0


def test_crop_and_slice():
    # create a mask with zero-margin of 10 voxels
    mask = np.pad(
        np.ones((10, 10, 10)),
        pad_width=10,
        mode="constant",
    )
    return mask

def test_plot_roi():
    # Test with valid image and mask file path
    fig = plot_roi(image_path, mask_path)
    assert isinstance(fig, plotly.graph_objects.Figure), 'Unexpected output type'

    # Test with invalid image file path
    with pytest.raises(FileNotFoundError) as err:
        plot_roi('invalid_image.nii.gz', mask_path)
