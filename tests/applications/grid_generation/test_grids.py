#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2020 Centre National d'Etudes Spatiales (CNES).
#
# This file is part of CARS
# (see https://github.com/CNES/cars).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
Test module for cars/steps/epi_rectif/test_grids.py
"""

# Standard imports
from __future__ import absolute_import

# Third party imports
import numpy as np
import pytest
import rasterio as rio
import xarray as xr

from cars.applications.grid_generation import grid_correction, grids
from cars.applications.sparse_matching import sparse_matching_tools

# CARS imports
from cars.conf import input_parameters
from cars.data_structures import cars_dataset

# CARS Tests imports
from tests.helpers import absolute_data_path, get_geoid_path


@pytest.mark.unit_tests
def test_correct_right_grid():
    """
    Call right grid correction method and check outputs properties
    """
    matches_file = absolute_data_path(
        "input/preprocessing_input/matches_ventoux.npy"
    )
    grid_file = absolute_data_path(
        "input/preprocessing_input/right_epipolar_grid_uncorrected_ventoux.tif"
    )
    origin = [0, 0]
    spacing = [30, 30]

    matches = np.load(matches_file)
    matches = np.array(matches)

    matches_filtered = sparse_matching_tools.remove_epipolar_outliers(matches)

    with rio.open(grid_file) as rio_grid:
        grid = rio_grid.read()
        grid = np.transpose(grid, (1, 2, 0))

        # Estimate grid correction
        # Create fake cars dataset with grid
        grid_right = cars_dataset.CarsDataset("arrays")
        grid_right.tiling_grid = np.array(
            [[[0, grid.shape[0], 0, grid.shape[1]]]]
        )
        grid_right[0, 0] = grid
        grid_right.attributes["grid_origin"] = origin
        grid_right.attributes["grid_spacing"] = spacing

        (
            grid_correction_coef,
            corrected_matches,
            _,
            _,
            in_stats,
            out_stats,
        ) = grid_correction.estimate_right_grid_correction(
            matches_filtered, grid_right
        )

        # Correct grid right
        corrected_grid_cars_ds = grid_correction.correct_grid(
            grid_right, grid_correction_coef
        )
        corrected_grid = corrected_grid_cars_ds[0, 0]

        # Uncomment to update ref
        # np.save(absolute_data_path("ref_output/corrected_right_grid.npy"),
        # corrected_grid)
        corrected_grid_ref = np.load(
            absolute_data_path("ref_output/corrected_right_grid.npy")
        )
        np.testing.assert_allclose(
            corrected_grid, corrected_grid_ref, atol=0.05, rtol=1.0e-6
        )

        assert corrected_grid.shape == grid.shape

        # Assert that we improved all stats
        assert abs(out_stats["mean_epipolar_error"][0]) < abs(
            in_stats["mean_epipolar_error"][0]
        )
        assert abs(out_stats["mean_epipolar_error"][1]) < abs(
            in_stats["mean_epipolar_error"][1]
        )
        assert abs(out_stats["median_epipolar_error"][0]) < abs(
            in_stats["median_epipolar_error"][0]
        )
        assert abs(out_stats["median_epipolar_error"][1]) < abs(
            in_stats["median_epipolar_error"][1]
        )
        assert (
            out_stats["std_epipolar_error"][0]
            < in_stats["std_epipolar_error"][0]
        )
        assert (
            out_stats["std_epipolar_error"][1]
            < in_stats["std_epipolar_error"][1]
        )
        assert out_stats["rms_epipolar_error"] < in_stats["rms_epipolar_error"]
        assert (
            out_stats["rmsd_epipolar_error"] < in_stats["rmsd_epipolar_error"]
        )

        # Assert absolute performances

        assert abs(out_stats["median_epipolar_error"][0]) < 0.1
        assert abs(out_stats["median_epipolar_error"][1]) < 0.1

        assert abs(out_stats["mean_epipolar_error"][0]) < 0.1
        assert abs(out_stats["mean_epipolar_error"][1]) < 0.1
        assert out_stats["rms_epipolar_error"] < 0.5

        # Assert corrected matches are corrected
        assert (
            np.fabs(np.mean(corrected_matches[:, 1] - corrected_matches[:, 3]))
            < 0.1
        )


@pytest.mark.unit_tests
def test_generate_epipolar_grids_default_alt():
    """
    Test generate_epipolar_grids method with default alt and no dem
    """
    conf = {
        input_parameters.IMG1_TAG: absolute_data_path(
            "input/phr_ventoux/left_image.tif"
        ),
        input_parameters.IMG2_TAG: absolute_data_path(
            "input/phr_ventoux/right_image.tif"
        ),
    }
    dem = None
    default_alt = 500

    (
        left_grid,
        right_grid,
        _,
        _,
        epi_size,
        baseline,
    ) = grids.generate_epipolar_grids(
        conf,
        "OTBGeometry",
        dem,
        default_alt=default_alt,
        epipolar_step=30,
        geoid=get_geoid_path(),
    )

    assert epi_size == [612, 612]
    assert baseline == 1 / 0.7039446234703064

    # Uncomment to update baseline
    # left_grid.to_netcdf(absolute_data_path(
    # "ref_output/left_grid_default_alt.nc"))

    left_grid_ref = xr.open_dataset(
        absolute_data_path("ref_output/left_grid_default_alt.nc")
    )
    assert np.allclose(left_grid_ref["x"].values, left_grid[:, :, 0])
    assert np.allclose(left_grid_ref["y"].values, left_grid[:, :, 1])

    # Uncomment to update baseline
    # right_grid.to_netcdf(absolute_data_path(
    # "ref_output/right_grid_default_alt.nc"))

    right_grid_ref = xr.open_dataset(
        absolute_data_path("ref_output/right_grid_default_alt.nc")
    )
    assert np.allclose(right_grid_ref["x"].values, right_grid[:, :, 0])
    assert np.allclose(right_grid_ref["y"].values, right_grid[:, :, 1])


@pytest.mark.unit_tests
def test_generate_epipolar_grids():
    """
    Test generate_epipolar_grids method
    """
    conf = {
        input_parameters.IMG1_TAG: absolute_data_path(
            "input/phr_ventoux/left_image.tif"
        ),
        input_parameters.IMG2_TAG: absolute_data_path(
            "input/phr_ventoux/right_image.tif"
        ),
    }
    dem = absolute_data_path("input/phr_ventoux/srtm")

    (
        left_grid,
        right_grid,
        _,
        _,
        epi_size,
        baseline,
    ) = grids.generate_epipolar_grids(
        conf,
        "OTBGeometry",
        dem,
        default_alt=None,
        epipolar_step=30,
        geoid=get_geoid_path(),
    )

    assert epi_size == [612, 612]
    assert baseline == 1 / 0.7039416432380676

    # Uncomment to update baseline
    # left_grid.to_netcdf(absolute_data_path("ref_output/left_grid.nc"))

    left_grid_ref = xr.open_dataset(
        absolute_data_path("ref_output/left_grid.nc")
    )
    assert np.allclose(left_grid_ref["x"].values, left_grid[:, :, 0])
    assert np.allclose(left_grid_ref["y"].values, left_grid[:, :, 1])

    # Uncomment to update baseline
    # right_grid.to_netcdf(absolute_data_path("ref_output/right_grid.nc"))

    right_grid_ref = xr.open_dataset(
        absolute_data_path("ref_output/right_grid.nc")
    )
    assert np.allclose(right_grid_ref["x"].values, right_grid[:, :, 0])
    assert np.allclose(right_grid_ref["y"].values, right_grid[:, :, 1])
