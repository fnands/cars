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
CARS sensor_to_full_resolution_dsm pipeline class file
"""

# Standard imports
from __future__ import print_function

import json
import logging
import os

# CARS imports
from cars import __version__
from cars.applications.application import Application
from cars.applications.grid_generation import grid_correction
from cars.applications.sparse_matching import sparse_matching_tools
from cars.conf import log_conf
from cars.core import preprocessing
from cars.core.utils import safe_makedirs
from cars.orchestrator import orchestrator
from cars.pipelines.pipeline import Pipeline
from cars.pipelines.pipeline_template import PipelineTemplate
from cars.pipelines.sensor_to_full_resolution_dsm import dsm_output
from cars.pipelines.sensor_to_full_resolution_dsm import (
    sensor_full_res_dsm_constants as sens_cst,
)
from cars.pipelines.sensor_to_full_resolution_dsm import sensors_inputs

# Path in cars package (pkg)
CARS_GEOID_PATH = "geoid/egm96.grd"


@Pipeline.register("sensor_to_low_resolution_dsm")
class SensorToLowResolutionDsmPipeline(PipelineTemplate):
    """
    SensorToLowResolutionDsmPipeline
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, conf, config_json_dir=None):
        """
        Creates pipeline

        :param pipeline_name: name of the pipeline.
        :type pipeline_name: str
        :param cfg: configuration {'matching_cost_method': value}
        :type cfg: dictionary
        :param config_json_dir: path to dir containing json
        :type config_json_dir: str
        """

        # Merge parameters from associated json
        # priority : cars_pipeline.json << user_inputs.json
        # Get root package directory
        package_path = os.path.dirname(__file__)
        json_file = os.path.join(
            package_path,
            "..",
            "conf_pipeline",
            "sensor_to_low_resolution_dsm.json",
        )
        with open(json_file, "r", encoding="utf8") as fstream:
            pipeline_config = json.load(fstream)

        self.conf = pipeline_config.copy()
        self.conf.update(conf)

        # Check conf orchestrator
        self.orchestrator_conf = self.conf.get(sens_cst.ORCHESTRATOR, None)
        self.check_orchestrator(self.orchestrator_conf)

        # Check conf inputs
        self.inputs = self.check_inputs(
            self.conf[sens_cst.INPUTS], config_json_dir=config_json_dir
        )

        # Check conf output
        self.output = self.check_output(self.conf[sens_cst.OUTPUT])

        # Check conf application
        self.check_applications(self.conf.get(sens_cst.APPLICATIONS, {}))

    def check_inputs(self, conf, config_json_dir=None):
        """
        Check the inputs given

        :param conf: configuration of inputs
        :type conf: dict
        :param config_json_dir: directory of used json, if
               user filled paths with relative paths
        :type config_json_dir: str

        :return: overloader inputs
        :rtype: dict
        """
        return sensors_inputs.sensors_check_inputs(
            conf, config_json_dir=config_json_dir
        )

    def check_output(self, conf):
        """
        Check the output given

        :param conf: configuration of output
        :type conf: dict

        :return: overloader output
        :rtype: dict
        """
        return dsm_output.full_res_dsm_check_output(conf)

    def check_applications(self, conf):
        """
        Check the given configuration for applications

        :param conf: configuration of applications
        :type conf: dict
        """

        # Check if all specified applications are used
        needed_applications = [
            "grid_generation",
            "sparse_matching",
            "resampling",
            "dense_matching",
            "triangulation",
            "point_cloud_fusion",
            "point_cloud_rasterization",
        ]

        for app_key in conf.keys():
            if app_key not in needed_applications:
                logging.error(
                    "No {} application used in pipeline".format(app_key)
                )
                raise Exception(
                    "No {} application used in pipeline".format(app_key)
                )

        # Epipolar grid generation
        self.epipolar_grid_generation_application = Application(
            "grid_generation", cfg=conf.get("grid_generation", {})
        )

        # Sparse Matching
        self.sparse_matching_app = Application(
            "sparse_matching", cfg=conf.get("sparse_matching", {})
        )

        # image resampling
        self.resampling_application = Application(
            "resampling", cfg=conf.get("resampling", {})
        )

        # Matching
        self.dense_matching_application = Application(
            "dense_matching", cfg=conf.get("dense_matching", {})
        )

        # Triangulation
        self.triangulation_application = Application(
            "triangulation", cfg=conf.get("triangulation", {})
        )

        # Points cloud fusion
        self.pc_fusion_application = Application(
            "point_cloud_fusion", cfg=conf.get("point_cloud_fusion", {})
        )

        # Rasterization
        self.rasterization_application = Application(
            "point_cloud_rasterization",
            cfg=conf.get("point_cloud_rasterization", {}),
        )

    def run(self):
        """
        Run pipeline

        """
        out_dir = self.output["out_dir"]

        log_conf.add_log_file(out_dir, "sensor_to_low_res_dsm")

        # start cars orchestrator
        with orchestrator.Orchestrator(
            orchestrator_conf=self.orchestrator_conf,
            out_dir=out_dir,
            out_json_path=os.path.join(
                out_dir, self.output[sens_cst.INFO_BASENAME]
            ),
        ) as cars_orchestrator:

            # initialize out_json
            cars_orchestrator.update_out_info(
                {
                    "version": __version__,
                    "pipeline": "sensor_to_low_resolution_dsm_pipeline",
                    "inputs": self.inputs,
                }
            )

            # Run applications

            # Initialize epsg for terrain tiles
            epsg = self.inputs[sens_cst.EPSG]
            if epsg is not None:
                # Compute roi polygon, in input EPSG
                roi_poly = preprocessing.compute_roi_poly(
                    self.inputs[sens_cst.ROI], epsg
                )

            list_terrain_roi = []

            # initialise lists of points
            list_epipolar_points_cloud_left = []
            list_epipolar_points_cloud_right = []

            list_sensor_pairs = sensors_inputs.generate_inputs(self.inputs)
            logging.info(
                "Received {} stereo pairs configurations".format(
                    len(list_sensor_pairs)
                )
            )

            for (
                pair_key,
                sensor_image_left,
                sensor_image_right,
            ) in list_sensor_pairs:

                # Create Pair folder
                pair_folder = os.path.join(out_dir, pair_key)
                safe_makedirs(pair_folder)
                safe_makedirs(os.path.join(pair_folder, "tmp"))

                # Run applications

                # Run grid generation
                (
                    grid_left,
                    grid_right,
                ) = self.epipolar_grid_generation_application.run(
                    sensor_image_left,
                    sensor_image_right,
                    orchestrator=cars_orchestrator,
                    pair_folder=pair_folder,
                    pair_key=pair_key,
                    srtm_dir=self.inputs[sens_cst.INITIAL_ELEVATION],
                    default_alt=self.inputs[sens_cst.DEFAULT_ALT],
                    geoid_path=self.inputs[sens_cst.GEOID],
                )

                # Run epipolar resampling
                (
                    epipolar_image_left,
                    epipolar_image_right,
                ) = self.resampling_application.run(
                    sensor_image_left,
                    sensor_image_right,
                    grid_left,
                    grid_right,
                    orchestrator=cars_orchestrator,
                    pair_folder=pair_folder,
                    pair_key=pair_key,
                    margins=self.sparse_matching_app.get_margins(),
                    add_color=False,
                )

                # Run epipolar sparse_matching application
                (epipolar_matches_left, _,) = self.sparse_matching_app.run(
                    epipolar_image_left,
                    epipolar_image_right,
                    grid_left.attributes["disp_to_alt_ratio"],
                    orchestrator=cars_orchestrator,
                    pair_folder=pair_folder,
                    pair_key=pair_key,
                    mask1_ignored_by_sift=sensor_image_left[
                        sens_cst.INPUT_MSK_CLASSES
                    ][sens_cst.IGNORED_BY_SPARSE_MATCHING],
                    mask2_ignored_by_sift=sensor_image_right[
                        sens_cst.INPUT_MSK_CLASSES
                    ][sens_cst.IGNORED_BY_SPARSE_MATCHING],
                )

                # Run grid correction application

                # Filter matches
                matches_array = self.sparse_matching_app.filter_matches(
                    epipolar_matches_left,
                    orchestrator=cars_orchestrator,
                    pair_key=pair_key,
                    pair_folder=pair_folder,
                    save_matches=self.sparse_matching_app.get_save_matches(),
                )
                # Estimate grid correction
                (
                    grid_correction_coef,
                    corrected_matches_array,
                    corrected_matches_cars_ds_left,
                    corrected_matches_cars_ds_right,
                    _,
                    _,
                ) = grid_correction.estimate_right_grid_correction(
                    matches_array,
                    grid_right,
                    initial_cars_ds=epipolar_matches_left,
                )

                # Correct grid right
                corrected_grid_right = grid_correction.correct_grid(
                    grid_right, grid_correction_coef
                )

                # Compute disp_min and disp_max
                (
                    dmin,
                    dmax,
                ) = sparse_matching_tools.derive_disparity_range_from_matches(
                    corrected_matches_array,
                    orchestrator=cars_orchestrator,
                    disparity_margin=(
                        self.sparse_matching_app.get_disparity_margin()
                    ),
                    pair_key=pair_key,
                    pair_folder=pair_folder,
                    disp_to_alt_ratio=(
                        grid_left.attributes["disp_to_alt_ratio"]
                    ),
                    disparity_outliers_rejection_percent=(
                        self.sparse_matching_app.get_disp_out_reject_percent()
                    ),
                    save_matches=self.sparse_matching_app.get_save_matches(),
                )

                if epsg is None:
                    # compute epsg
                    epsg = preprocessing.compute_epsg(
                        sensor_image_left,
                        sensor_image_right,
                        grid_left,
                        grid_right,
                        self.triangulation_application.get_geometry_loader(),
                        orchestrator=cars_orchestrator,
                        pair_folder=pair_folder,
                        srtm_dir=self.inputs[sens_cst.INITIAL_ELEVATION],
                        default_alt=self.inputs[sens_cst.DEFAULT_ALT],
                        disp_min=dmin,
                        disp_max=dmax,
                    )
                    # Compute roi polygon, in input EPSG
                    roi_poly = preprocessing.compute_roi_poly(
                        self.inputs[sens_cst.ROI], epsg
                    )

                # Run epipolar triangulation application
                (
                    epipolar_points_cloud_left,
                    epipolar_points_cloud_right,
                ) = self.triangulation_application.run(
                    sensor_image_left,
                    sensor_image_right,
                    epipolar_image_left,
                    epipolar_image_right,
                    grid_left,
                    grid_right,
                    corrected_matches_cars_ds_left,
                    corrected_matches_cars_ds_right,
                    epsg,
                    orchestrator=cars_orchestrator,
                    pair_folder=pair_folder,
                    pair_key=pair_key,
                    uncorrected_grid_right=grid_right,
                    geoid_path=self.inputs[sens_cst.GEOID],
                    disp_min=dmin,
                    disp_max=dmax,
                )

                # Compute terrain bounding box /roi related to current images
                current_terrain_roi_bbox = preprocessing.compute_terrain_bbox(
                    self.inputs[sens_cst.INITIAL_ELEVATION],
                    self.inputs[sens_cst.DEFAULT_ALT],
                    self.inputs[sens_cst.GEOID],
                    sensor_image_left,
                    sensor_image_right,
                    epipolar_image_left,
                    grid_left,
                    corrected_grid_right,
                    epsg,
                    self.triangulation_application.get_geometry_loader(),
                    resolution=self.rasterization_application.get_resolution(),
                    disp_min=dmin,
                    disp_max=dmax,
                    roi_poly=roi_poly,
                    orchestrator=cars_orchestrator,
                    pair_key=pair_key,
                    pair_folder=pair_folder,
                    check_inputs=self.inputs[sens_cst.CHECK_INPUTS],
                )
                list_terrain_roi.append(current_terrain_roi_bbox)

                # add points cloud to list
                list_epipolar_points_cloud_left.append(
                    epipolar_points_cloud_left
                )
                list_epipolar_points_cloud_right.append(
                    epipolar_points_cloud_right
                )

            # compute terrain bounds
            (
                terrain_bounds,
                optimal_terrain_tile_width,
            ) = preprocessing.compute_terrain_bounds(
                list_terrain_roi,
                roi_poly=roi_poly,
                resolution=self.rasterization_application.get_resolution(),
            )

            # Merge point clouds
            merged_points_clouds = self.pc_fusion_application.run(
                list_epipolar_points_cloud_left,
                list_epipolar_points_cloud_right,
                terrain_bounds,
                epsg,
                orchestrator=cars_orchestrator,
                margins=self.rasterization_application.get_margins(),
                optimal_terrain_tile_width=optimal_terrain_tile_width,
            )

            # rasterize point cloud
            _ = self.rasterization_application.run(
                merged_points_clouds,
                epsg,
                orchestrator=cars_orchestrator,
                dsm_file_name=os.path.join(
                    out_dir, self.output[sens_cst.DSM_BASENAME]
                ),
            )
