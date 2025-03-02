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
this module contains the dense_matching application class.
"""


import collections

# Standard imports
import logging
import os

# Third party imports
import numpy as np
from affine import Affine
from json_checker import Checker, Or

# CARS imports
import cars.applications.rasterization.rasterization_tools as rasterization_step
import cars.orchestrator.orchestrator as ocht
from cars.applications import application_constants
from cars.applications.rasterization import rasterization_constants
from cars.applications.rasterization.point_cloud_rasterization import (
    PointCloudRasterization,
)
from cars.core import constants as cst
from cars.core import projection
from cars.data_structures import cars_dataset

# R0903  temporary disabled for error "Too few public methods"
# œgoing to be corrected by adding new methods as check_conf


class SimpleGaussian(
    PointCloudRasterization, short_name="simple_gaussian"
):  # pylint: disable=R0903
    """
    PointsCloudRasterisation
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, conf=None):
        """
        Init function of PointsCloudRasterisation

        :param conf: configuration for rasterization
        :return: a application_to_use object
        """

        # Check conf
        checked_conf = self.check_conf(conf)
        # used_config used for printing config
        self.used_config = checked_conf

        # check conf

        # get rasterization parameter
        self.used_method = checked_conf["method"]
        self.dsm_radius = checked_conf["dsm_radius"]
        self.sigma = checked_conf["sigma"]
        self.grid_points_division_factor = checked_conf[
            "grid_points_division_factor"
        ]
        self.resolution = checked_conf["resolution"]
        # get nodata values
        self.dsm_no_data = checked_conf["dsm_no_data"]
        self.color_no_data = checked_conf["color_no_data"]
        self.color_dtype = checked_conf["color_dtype"]
        self.msk_no_data = checked_conf["msk_no_data"]
        # Get if color, mask and stats are saved
        self.write_color = checked_conf["write_color"]
        self.write_stats = checked_conf["write_stats"]
        self.write_mask = checked_conf["write_msk"]
        self.write_dsm = checked_conf["write_dsm"]

        # Init orchestrator
        self.orchestrator = None

    def check_conf(self, conf):
        """
        Check configuration

        :param conf: configuration to check
        :type conf: dict

        :return: overloaded configuration
        :rtype: dict

        """

        # init conf
        if conf is not None:
            overloaded_conf = conf.copy()
        else:
            conf = {}
            overloaded_conf = {}

        # Overload conf

        # get rasterization parameter
        overloaded_conf["method"] = conf.get("method", "simple_gaussian")
        overloaded_conf["dsm_radius"] = conf.get("dsm_radius", 1.0)
        overloaded_conf["sigma"] = conf.get("sigma", None)
        overloaded_conf["grid_points_division_factor"] = conf.get(
            "grid_points_division_factor", None
        )
        overloaded_conf["resolution"] = conf.get("resolution", 0.5)

        # get nodata values
        overloaded_conf["dsm_no_data"] = conf.get("dsm_no_data", -32768)
        overloaded_conf["color_no_data"] = conf.get("color_no_data", 0)
        overloaded_conf["color_dtype"] = conf.get("color_dtype", "uint16")
        overloaded_conf["msk_no_data"] = conf.get("msk_no_data", 65535)

        # Get if color, mask and stats are saved
        overloaded_conf["write_color"] = conf.get("write_color", True)
        overloaded_conf["write_stats"] = conf.get("write_stats", False)
        overloaded_conf["write_msk"] = conf.get("write_msk", False)
        overloaded_conf["write_dsm"] = conf.get("write_dsm", True)

        rasterization_schema = {
            "method": str,
            "resolution": float,
            "dsm_radius": Or(float, int),
            "sigma": Or(float, None),
            "grid_points_division_factor": Or(None, int),
            "dsm_no_data": int,
            "msk_no_data": int,
            "color_no_data": int,
            "color_dtype": str,
            "write_color": bool,
            "write_msk": bool,
            "write_stats": bool,
            "write_dsm": bool,
        }

        # Check conf
        checker = Checker(rasterization_schema)
        checker.validate(overloaded_conf)

        return overloaded_conf

    def get_resolution(self):

        return self.resolution

    def get_margins(self):

        margins = {"radius": self.dsm_radius, "resolution": self.resolution}
        return margins

    def run(
        self,
        merged_points_cloud,
        epsg,
        orchestrator=None,
        dsm_file_name=None,
        color_file_name=None,
    ):
        """
        Run PointsCloudRasterisation application.

        Creates a CarsDataset filled with dsm tiles.

        :param merged_points_cloud: merged point cloud. CarsDataset contains:

            - Z x W Delayed tiles. \
                Each tile will be a future pandas DataFrame containing:

                - data with keys  "x", "y", "z", "corr_msk" \
                    optional: "clr", "msk", "data_valid", "coord_epi_geom_i",\
                     "coord_epi_geom_j","idx_im_epi"
                - attrs with keys "epsg", "ysize", "xsize", "xstart", "ystart"

             - attributes containing "bounds", "ysize", "xsize", "epsg"

        :type merged_points_cloud: CarsDataset filled with pandas.DataFrame
        :param epsg: epsg of raster data
        :type epsg: str
        :param orchestrator: orchestrator used
        :param dsm_file_name: path of dsm
        :type dsm_file_name: str
        :param color_file_name: path of color
        :type color_file_name: str

        :return: raster DSM. CarsDataset contains:

            - Z x W Delayed tiles. \
                Each tile will be a future xarray Dataset containing:

                - data : with keys : "hgt", "img", "raster_msk",optional : \
                  "n_pts", "pts_in_cell", "hgt_mean", "hgt_stdev"
                - attrs with keys: "epsg"
            - attributes containing: None

        :rtype : CarsDataset filled with xr.Dataset
        """

        # Default orchestrator
        if orchestrator is None:
            # Create default sequential orchestrator for current application
            # be awere, no out_json will be shared between orchestrators
            # No files saved
            self.orchestrator = ocht.Orchestrator(
                orchestrator_conf={"mode": "sequential"}
            )
        else:
            self.orchestrator = orchestrator

        if merged_points_cloud.dataset_type == "points":

            # Create CarsDataset
            terrain_raster = cars_dataset.CarsDataset("arrays")

            # Get tiling grid
            terrain_raster.tiling_grid = merged_points_cloud.tiling_grid
            terrain_raster.generate_none_tiles()

            bounds = merged_points_cloud.attributes["bounds"]
            ysize = merged_points_cloud.attributes["ysize"]
            xsize = merged_points_cloud.attributes["xsize"]

            # Save objects
            # Initialize files names
            # TODO get from config ?
            out_dsm_file_name = None
            out_clr_file_name = None
            out_msk_file_name = None
            out_dsm_mean_file_name = None
            out_dsm_std_file_name = None
            out_dsm_n_pts_file_name = None
            out_dsm_points_in_cell_file_name = None

            if self.write_dsm:
                if dsm_file_name is not None:
                    out_dsm_file_name = dsm_file_name
                else:
                    out_dsm_file_name = os.path.join(
                        self.orchestrator.out_dir, "dsm.tif"
                    )
                self.orchestrator.add_to_save_lists(
                    out_dsm_file_name,
                    cst.RASTER_HGT,
                    terrain_raster,
                    dtype=np.float32,
                    nodata=self.dsm_no_data,
                    cars_ds_name="dsm",
                )
            if self.write_color:
                if color_file_name is not None:
                    out_clr_file_name = color_file_name
                else:
                    out_clr_file_name = os.path.join(
                        self.orchestrator.out_dir, "clr.tif"
                    )
                self.orchestrator.add_to_save_lists(
                    out_clr_file_name,
                    cst.RASTER_COLOR_IMG,
                    terrain_raster,
                    dtype=self.color_dtype,
                    nodata=self.color_no_data,
                    cars_ds_name="color",
                )
            if self.write_stats:
                out_dsm_mean_file_name = os.path.join(
                    self.orchestrator.out_dir, "dsm_mean.tif"
                )
                out_dsm_std_file_name = os.path.join(
                    self.orchestrator.out_dir, "dsm_std.tif"
                )
                out_dsm_n_pts_file_name = os.path.join(
                    self.orchestrator.out_dir, "dsm_n_pts.tif"
                )
                out_dsm_points_in_cell_file_name = os.path.join(
                    self.orchestrator.out_dir, "dsm_pts_in_cell.tif"
                )
                self.orchestrator.add_to_save_lists(
                    out_dsm_mean_file_name,
                    cst.RASTER_HGT_MEAN,
                    terrain_raster,
                    dtype=np.float32,
                    nodata=self.dsm_no_data,
                    cars_ds_name="dsm_mean",
                )
                self.orchestrator.add_to_save_lists(
                    out_dsm_std_file_name,
                    cst.RASTER_HGT_STD_DEV,
                    terrain_raster,
                    dtype=np.float32,
                    nodata=self.dsm_no_data,
                    cars_ds_name="dsm_std",
                )
                self.orchestrator.add_to_save_lists(
                    out_dsm_n_pts_file_name,
                    cst.RASTER_NB_PTS,
                    terrain_raster,
                    dtype=np.uint16,
                    nodata=0,
                    cars_ds_name="dsm_n_pts",
                )
                self.orchestrator.add_to_save_lists(
                    out_dsm_points_in_cell_file_name,
                    cst.RASTER_NB_PTS_IN_CELL,
                    terrain_raster,
                    dtype=np.uint16,
                    nodata=0,
                    cars_ds_name="dsm_pts_in_cells",
                )
            if self.write_mask:
                out_msk_file_name = os.path.join(
                    self.orchestrator.out_dir, "msk.tif"
                )
                self.orchestrator.add_to_save_lists(
                    out_msk_file_name,
                    cst.RASTER_MSK,
                    terrain_raster,
                    dtype=np.uint16,
                    nodata=self.msk_no_data,
                    cars_ds_name="dsm_mask",
                )

            # Get saving infos in order to save tiles when they are computed
            [saving_info] = self.orchestrator.get_saving_infos([terrain_raster])

            # Generate profile
            geotransform = (
                bounds[0],
                self.resolution,
                0.0,
                bounds[3],
                0.0,
                -self.resolution,
            )
            transform = Affine.from_gdal(*geotransform)
            raster_profile = collections.OrderedDict(
                {
                    "height": ysize,
                    "width": xsize,
                    "driver": "GTiff",
                    "dtype": "float32",
                    "transform": transform,
                    "crs": "EPSG:{}".format(epsg),
                    "tiled": True,
                }
            )

            # Get number of tiles
            logging.info(
                "Number of tiles in cloud rasterization :"
                "row : {} "
                "col : {}".format(
                    terrain_raster.tiling_grid.shape[0],
                    terrain_raster.tiling_grid.shape[1],
                )
            )

            # Add infos to orchestrator.out_json
            updating_dict = {
                application_constants.APPLICATION_TAG: {
                    rasterization_constants.RASTERIZATION_PARAMS_TAG: {
                        rasterization_constants.METHOD: self.used_method,
                        rasterization_constants.DSM_RADIUS: self.dsm_radius,
                        rasterization_constants.SIGMA: self.sigma,
                        rasterization_constants.GRID_POINTS_DIVISION_FACTOR: (
                            self.grid_points_division_factor
                        ),
                        rasterization_constants.RESOLUTION: self.resolution,
                    },
                    rasterization_constants.RASTERIZATION_RUN_TAG: {
                        rasterization_constants.EPSG_TAG: epsg,
                        rasterization_constants.DSM_TAG: out_dsm_file_name,
                        rasterization_constants.DSM_NO_DATA_TAG: float(
                            self.dsm_no_data
                        ),
                        rasterization_constants.COLOR_NO_DATA_TAG: float(
                            self.color_no_data
                        ),
                        rasterization_constants.COLOR_TAG: out_clr_file_name,
                        rasterization_constants.MSK_TAG: out_msk_file_name,
                        rasterization_constants.DSM_MEAN_TAG: (
                            out_dsm_mean_file_name
                        ),
                        rasterization_constants.DSM_STD_TAG: (
                            out_dsm_std_file_name
                        ),
                        rasterization_constants.DSM_N_PTS_TAG: (
                            out_dsm_n_pts_file_name
                        ),
                        rasterization_constants.DSM_POINTS_IN_CELL_TAG: (
                            out_dsm_points_in_cell_file_name
                        ),
                    },
                }
            }
            self.orchestrator.update_out_info(updating_dict)

            # Generate rasters
            for col in range(terrain_raster.shape[1]):
                for row in range(terrain_raster.shape[0]):

                    if merged_points_cloud.tiles[row][col] is not None:
                        # Get window
                        window = cars_dataset.window_array_to_dict(
                            terrain_raster.tiling_grid[row, col]
                        )

                        # Delayed call to rasterization operations using all
                        #  required point clouds
                        terrain_raster[
                            row, col
                        ] = self.orchestrator.cluster.create_task(
                            rasterization_wrapper
                        )(
                            merged_points_cloud[row, col],
                            self.resolution,
                            epsg,
                            window,
                            raster_profile,
                            saving_info=saving_info,
                            radius=self.dsm_radius,
                            sigma=self.sigma,
                            dsm_no_data=self.dsm_no_data,
                            color_no_data=self.color_no_data,
                            msk_no_data=self.msk_no_data,
                            grid_points_division_factor=(
                                self.grid_points_division_factor
                            ),
                        )

            # Sort tiles according to rank TODO remove or implement it ?

        else:
            logging.error(
                "PointsCloudRasterisation application doesn't support"
                "this input data "
                "format"
            )

        return terrain_raster


def rasterization_wrapper(
    cloud,
    resolution,
    epsg,
    window,
    profile,
    saving_info=None,
    sigma: float = None,
    radius: int = 1,
    dsm_no_data: int = np.nan,
    color_no_data: int = np.nan,
    msk_no_data: int = 65535,
    grid_points_division_factor: int = None,
):
    """
    Wrapper for rasterization step :
    - Convert a list of clouds to correct epsg
    - Rasterize it with associated colors

    :param cloud: combined cloud
    :type cloud: pandas.DataFrame
    :param resolution: Produced DSM resolution (meter, degree [EPSG dependent])
    :type resolution: float
    :param  epsg_code: epsg code for the CRS of the output DSM
    :type epsg_code: int
    :param  window: Window considered
    :type window: int
    :param  profile: rasterio profile
    :type profile: dict
    :param saving_info: information about CarsDataset ID.
    :type saving_info: dict
    :param sigma: sigma for gaussian interpolation.
        (If None, set to resolution)
    :param radius: Radius for hole filling.
    :param dsm_no_data: no data value to use in the final raster
    :param color_no_data: no data value to use in the final colored raster
    :param msk_no_data: no data value to use in the final mask image
    :param grid_points_division_factor: number of blocks to use to divide
        the grid points (memory optimization, reduce the highest memory peak).
        If it is not set, the factor is automatically set to construct
        700000 points blocks.

    :return: digital surface model + projected colors
    :rtype: xr.Dataset
    """

    cloud_attributes = cars_dataset.get_attributes_dataframe(cloud)
    cloud_epsg = cloud_attributes["epsg"]

    # convert back to correct epsg
    # If the points cloud is not in the right epsg referential, it is converted
    if epsg != cloud_epsg:
        projection.points_cloud_conversion_dataframe(cloud, cloud_epsg, epsg)

    # Call simple_rasterization
    raster = rasterization_step.simple_rasterization_dataset_wrapper(
        cloud,
        resolution,
        epsg,
        xstart=cloud_attributes["xstart"],
        ystart=cloud_attributes["ystart"],
        xsize=cloud_attributes["xsize"],
        ysize=cloud_attributes["ysize"],
        sigma=sigma,
        radius=radius,
        dsm_no_data=dsm_no_data,
        color_no_data=color_no_data,
        msk_no_data=msk_no_data,
        grid_points_division_factor=grid_points_division_factor,
    )

    # Fill raster
    if raster is not None:
        cars_dataset.fill_dataset(
            raster,
            saving_info=saving_info,
            window=window,
            profile=profile,
            attributes=None,
            overlaps=None,
        )

    return raster
