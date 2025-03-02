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
Preprocessing module:
contains functions used for triangulation
"""

# Standard imports
import logging
from typing import Dict

# Third party imports
import numpy as np
import xarray as xr

from cars.conf import input_parameters
from cars.core import constants as cst
from cars.core import former_confs_utils

# CARS imports
from cars.core.geometry import AbstractGeometry


def triangulate(
    loader_to_use,
    configuration,
    disp_ref: xr.Dataset,
    disp_sec: xr.Dataset = None,
    im_ref_msk_ds: xr.Dataset = None,
    im_sec_msk_ds: xr.Dataset = None,
    snap_to_img1: bool = False,
) -> Dict[str, xr.Dataset]:
    """
    This function will perform triangulation from a disparity map

    :param loader_to_use: geometry loader to use
    :type loader_to_use: str
    :param configuration: StereoConfiguration
    :type configuration: StereoConfiguration
    :param disp_ref: left to right disparity map dataset
    :param disp_sec: if available, the right to left disparity map dataset
    :param im_ref_msk_ds: reference image dataset (image and
                          mask (if indicated by the user) in epipolar geometry)
    :param im_sec_msk_ds: secondary image dataset (image and
                          mask (if indicated by the user) in epipolar geometry)
    :param snap_to_img1: If True, Lines of Sight of img2 are moved so as to
                         cross those of img1
    :param snap_to_img1: bool
    :returns: point_cloud as a dictionary of dataset containing:

        - Array with shape (roi_size_x,roi_size_y,3), with last dimension \
          corresponding to longitude, latitude and elevation
        - Array with shape (roi_size_x,roi_size_y) with output mask
        - Array for color (optional): only if color1 is not None

    The dictionary keys are :

        - 'ref' to retrieve the dataset built from the left to \
           right disparity map
        - 'sec' to retrieve the dataset built from the right to \
           left disparity map (if provided in input)
    """

    # Retrieve information from configuration
    input_configuration = configuration[input_parameters.INPUT_SECTION_TAG]

    # Retrieve grids

    (
        grid1,
        grid2,
        uncorrected_grid_2,
    ) = former_confs_utils.get_grid_from_cars_post_prepare_configurations(
        configuration
    )

    if snap_to_img1:
        grid2 = uncorrected_grid_2
        if grid2 is None:
            logging.error(
                "Uncorrected grid was not given in order to snap it to img1"
            )

    point_clouds = {}
    point_clouds[cst.STEREO_REF] = compute_points_cloud(
        loader_to_use,
        disp_ref,
        input_configuration,
        grid1,
        grid2,
        roi_key=cst.ROI,
        dataset_msk=im_ref_msk_ds,
    )

    if disp_sec is not None:
        # reverse geometric models input_parameters.PRODUCT1_KEY and
        # input_parameters.PRODUCT2_KEY to use the secondary disparity map
        reversed_input_configuration = {}
        for key, value in input_configuration.items():
            if input_parameters.PRODUCT1_KEY in key:
                reversed_input_configuration[
                    key.replace(
                        input_parameters.PRODUCT1_KEY,
                        input_parameters.PRODUCT2_KEY,
                    )
                ] = value
            elif input_parameters.PRODUCT2_KEY in key:
                reversed_input_configuration[
                    key.replace(
                        input_parameters.PRODUCT2_KEY,
                        input_parameters.PRODUCT1_KEY,
                    )
                ] = value
            else:
                reversed_input_configuration[key] = value

        point_clouds[cst.STEREO_SEC] = compute_points_cloud(
            loader_to_use,
            disp_sec,
            reversed_input_configuration,
            grid2,
            grid1,
            roi_key=cst.ROI_WITH_MARGINS,
            dataset_msk=im_sec_msk_ds,
        )

    return point_clouds


def triangulate_matches(
    loader_to_use, configuration, matches, snap_to_img1=False
):
    """
    This function will perform triangulation from sift matches

    :param loader_to_use: geometry loader to use
    :type loader_to_use: str
    :param configuration: StereoConfiguration
    :type configuration: StereoConfiguration
    :param matches: numpy.array of matches of shape (nb_matches, 4)
    :type data: numpy.ndarray
    :param snap_to_img1: If this is True, Lines of Sight of img2 are moved so
                         as to cross those of img1
    :param snap_to_img1: bool
    :returns: point_cloud as a dataset containing:

        - Array with shape (nb_matches,1,3), with last dimension \
        corresponding to longitude, latitude and elevation
        - Array with shape (nb_matches,1) with output mask

    :rtype: xarray.Dataset
    """

    # Retrieve information from configuration
    input_configuration = configuration[input_parameters.INPUT_SECTION_TAG]

    # Retrieve grids
    (
        grid1,
        grid2,
        uncorrected_grid_2,
    ) = former_confs_utils.get_grid_from_cars_post_prepare_configurations(
        configuration
    )
    if snap_to_img1:
        grid2 = uncorrected_grid_2

    geometry_loader = (
        AbstractGeometry(  # pylint: disable=abstract-class-instantiated
            loader_to_use
        )
    )
    llh = geometry_loader.triangulate(
        input_configuration,
        cst.MATCHES_MODE,
        matches,
        grid1,
        grid2,
    )

    row = np.array(range(llh.shape[0]))
    col = np.array([0])

    msk = np.full(llh.shape[0:2], 255, dtype=np.uint8)

    point_cloud = xr.Dataset(
        {
            cst.X: ([cst.ROW, cst.COL], llh[:, :, 0]),
            cst.Y: ([cst.ROW, cst.COL], llh[:, :, 1]),
            cst.Z: ([cst.ROW, cst.COL], llh[:, :, 2]),
            cst.POINTS_CLOUD_CORR_MSK: ([cst.ROW, cst.COL], msk),
        },
        coords={cst.ROW: row, cst.COL: col},
    )
    point_cloud.attrs[cst.EPSG] = int(4326)

    return point_cloud


def compute_points_cloud(
    loader_to_use: str,
    data: xr.Dataset,
    cars_conf,
    grid1: str,
    grid2: str,
    roi_key: str,
    dataset_msk: xr.Dataset = None,
) -> xr.Dataset:
    # TODO detail a bit more what this method do
    """
    Compute points cloud

    :param loader_to_use: geometru loader to use
    :type loader_to_use: str:param loader_to_use: geometru loader to use
    :param data: The reference to disparity map dataset
    :param cars_conf: cars input configuration dictionary
    :param grid1: path to the reference image grid file
    :param grid2: path to the secondary image grid file
    :param roi_key: roi of the disparity map key
          ('roi' if cropped while calling create_disp_dataset,
          otherwise 'roi_with_margins')
    :param dataset_msk: dataset with mask information to use
    :return: the points cloud dataset
    """
    geometry_loader = (
        AbstractGeometry(  # pylint: disable=abstract-class-instantiated
            loader_to_use
        )
    )

    llh = geometry_loader.triangulate(
        cars_conf,
        cst.DISP_MODE,
        data,
        grid1,
        grid2,
        roi_key,
    )

    row = np.array(range(data.attrs[roi_key][1], data.attrs[roi_key][3]))
    col = np.array(range(data.attrs[roi_key][0], data.attrs[roi_key][2]))

    values = {
        cst.X: ([cst.ROW, cst.COL], llh[:, :, 0]),  # longitudes
        cst.Y: ([cst.ROW, cst.COL], llh[:, :, 1]),  # latitudes
        cst.Z: ([cst.ROW, cst.COL], llh[:, :, 2]),
        cst.POINTS_CLOUD_CORR_MSK: (
            [cst.ROW, cst.COL],
            data[cst.DISP_MSK].values,
        ),
    }

    if dataset_msk is not None:
        ds_values_list = [key for key, _ in dataset_msk.items()]

        if cst.EPI_MSK in ds_values_list:
            if roi_key == cst.ROI_WITH_MARGINS:
                ref_roi = [
                    0,
                    0,
                    int(dataset_msk.dims[cst.COL]),
                    int(dataset_msk.dims[cst.ROW]),
                ]
            else:
                ref_roi = [
                    int(-dataset_msk.attrs[cst.EPI_MARGINS][0]),
                    int(-dataset_msk.attrs[cst.EPI_MARGINS][1]),
                    int(
                        dataset_msk.dims[cst.COL]
                        - dataset_msk.attrs[cst.EPI_MARGINS][2]
                    ),
                    int(
                        dataset_msk.dims[cst.ROW]
                        - dataset_msk.attrs[cst.EPI_MARGINS][3]
                    ),
                ]
            im_msk = dataset_msk[cst.EPI_MSK].values[
                ref_roi[1] : ref_roi[3], ref_roi[0] : ref_roi[2]
            ]
            values[cst.POINTS_CLOUD_MSK] = ([cst.ROW, cst.COL], im_msk)
        else:
            worker_logger = logging.getLogger("distributed.worker")
            worker_logger.warning("No mask is present in the image dataset")

    point_cloud = xr.Dataset(values, coords={cst.ROW: row, cst.COL: col})

    # add color
    nb_bands = 1
    if cst.EPI_COLOR in data:
        color = data[cst.EPI_COLOR].values
        if len(color.shape) > 2:
            nb_bands = color.shape[0]
            if nb_bands == 1:
                color = color[0, :, :]

        if nb_bands > 1:
            if cst.BAND not in point_cloud.dims:
                point_cloud.assign_coords({cst.BAND: np.arange(nb_bands)})

            point_cloud[cst.EPI_COLOR] = xr.DataArray(
                color,
                dims=[cst.BAND, cst.ROW, cst.COL],
            )
        else:
            point_cloud[cst.EPI_COLOR] = xr.DataArray(
                color,
                dims=[cst.ROW, cst.COL],
            )

    point_cloud.attrs[cst.ROI] = data.attrs[cst.ROI]
    if roi_key == cst.ROI_WITH_MARGINS:
        point_cloud.attrs[cst.ROI_WITH_MARGINS] = data.attrs[
            cst.ROI_WITH_MARGINS
        ]
    point_cloud.attrs[cst.EPI_FULL_SIZE] = data.attrs[cst.EPI_FULL_SIZE]
    point_cloud.attrs[cst.EPSG] = int(4326)

    return point_cloud


def geoid_offset(points, geoid):
    """
    Compute the point cloud height offset from geoid.

    :param points: point cloud data in lat/lon/alt WGS84 (EPSG 4326)
        coordinates.
    :type points: xarray.Dataset
    :param geoid: geoid elevation data.
    :type geoid: xarray.Dataset
    :return: the same point cloud but using geoid as altimetric reference.
    :rtype: xarray.Dataset
    """

    # deep copy the given point cloud that will be used as output
    out_pc = points.copy(deep=True)

    # currently assumes that the OTB EGM96 geoid will be used with longitude
    # ranging from 0 to 360, so we must unwrap longitudes to this range.
    longitudes = np.copy(out_pc[cst.X].values)
    longitudes[longitudes < 0] += 360

    # perform interpolation using point cloud coordinates.
    if (
        not geoid.lat_min
        <= out_pc[cst.Y].min()
        <= out_pc[cst.Y].max()
        <= geoid.lat_max
        and geoid.lon_min
        <= np.min(longitudes)
        <= np.max(longitudes)
        <= geoid.lat_max
    ):
        raise RuntimeError(
            "Geoid does not fully cover the area spanned by the point cloud."
        )

    # interpolate data
    ref_interp = geoid.interp(
        {
            "lat": out_pc[cst.Y],
            "lon": xr.DataArray(longitudes, dims=(cst.ROW, cst.COL)),
        }
    )
    # offset using geoid height
    out_pc[cst.Z] = points[cst.Z] - ref_interp.hgt

    # remove coordinates lat & lon added by the interpolation
    out_pc = out_pc.reset_coords(["lat", "lon"], drop=True)

    return out_pc
