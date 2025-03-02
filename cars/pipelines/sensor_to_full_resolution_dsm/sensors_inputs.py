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
CARS containing inputs checking for sensor input data
Used for full_res and low_res pipelines
"""

import logging
import os
from typing import List, Tuple

import fiona
import rasterio as rio
from json_checker import Checker, Or

# CARS imports
from cars.conf import mask_classes
from cars.core import inputs
from cars.core.utils import make_relative_path_absolute
from cars.pipelines.sensor_to_full_resolution_dsm import (
    sensor_full_res_dsm_constants as sens_cst,
)

CARS_GEOID_PATH = "geoid/egm96.grd"  # Path in cars package (pkg)


def sensors_check_inputs(conf, config_json_dir=None):  # noqa: C901
    """
    Check the inputs given

    :param conf: configuration of inputs
    :type conf: dict
    :param config_json_dir: path to dir containing json
    :type config_json_dir: str
    """

    overloaded_conf = conf.copy()

    # Overload some optional parameters
    overloaded_conf[sens_cst.EPSG] = conf.get(sens_cst.EPSG, None)
    overloaded_conf[sens_cst.INITIAL_ELEVATION] = conf.get(
        sens_cst.INITIAL_ELEVATION, None
    )
    overloaded_conf[sens_cst.DEFAULT_ALT] = conf.get(sens_cst.DEFAULT_ALT, 0)
    overloaded_conf[sens_cst.ROI] = conf.get(sens_cst.ROI, None)
    overloaded_conf[sens_cst.CHECK_INPUTS] = conf.get(
        sens_cst.CHECK_INPUTS, False
    )

    if "geoid" not in overloaded_conf:
        # use cars geoid
        logging.info("CARS will use its own internal file as geoid reference")
        # Get root package directory
        package_path = os.path.dirname(__file__)
        geoid_path = os.path.join(
            package_path, "..", "..", "conf", CARS_GEOID_PATH
        )
        overloaded_conf[sens_cst.GEOID] = geoid_path
    else:
        overloaded_conf[sens_cst.GEOID] = conf.get(sens_cst.GEOID, None)

    # Validate inputs
    inputs_schema = {
        sens_cst.SENSORS: dict,
        sens_cst.PAIRING: [[str]],
        sens_cst.EPSG: Or(int, None),  # move to rasterization
        sens_cst.INITIAL_ELEVATION: Or(str, None),
        sens_cst.DEFAULT_ALT: int,
        sens_cst.ROI: Or(str, list, tuple, None),
        sens_cst.CHECK_INPUTS: bool,
        sens_cst.GEOID: Or(None, str),
    }

    checker_inputs = Checker(inputs_schema)
    checker_inputs.validate(overloaded_conf)

    # Validate each sensor image
    sensor_schema = {
        sens_cst.INPUT_IMG: str,
        sens_cst.INPUT_COLOR: str,
        sens_cst.INPUT_NODATA: int,
        sens_cst.INPUT_GEO_MODEL: str,
        sens_cst.INPUT_MODEL_FILTER: Or([str], None),
        sens_cst.INPUT_MSK: Or(str, None),
        sens_cst.INPUT_MSK_CLASSES: dict,
    }
    checker_sensor = Checker(sensor_schema)

    mask_classes_schema = {
        sens_cst.IGNORED_BY_DENSE_MATCHING: Or([int], None),
        sens_cst.SET_TO_REF_ALT: Or([int], None),
        sens_cst.IGNORED_BY_SPARSE_MATCHING: Or([int], None),
    }
    checker_mask_classes = Checker(mask_classes_schema)

    for sensor_image_key in conf[sens_cst.SENSORS]:
        # Overload optional parameters
        color = conf[sens_cst.SENSORS][sensor_image_key].get(
            "color",
            conf[sens_cst.SENSORS][sensor_image_key][sens_cst.INPUT_IMG],
        )
        overloaded_conf[sens_cst.SENSORS][sensor_image_key][
            sens_cst.INPUT_COLOR
        ] = color

        geomodel_filters = conf[sens_cst.SENSORS][sensor_image_key].get(
            sens_cst.INPUT_MODEL_FILTER, None
        )
        overloaded_conf[sens_cst.SENSORS][sensor_image_key][
            sens_cst.INPUT_MODEL_FILTER
        ] = geomodel_filters

        no_data = conf[sens_cst.SENSORS][sensor_image_key].get(
            sens_cst.INPUT_NODATA, -9999
        )
        overloaded_conf[sens_cst.SENSORS][sensor_image_key][
            sens_cst.INPUT_NODATA
        ] = no_data

        mask = conf[sens_cst.SENSORS][sensor_image_key].get(
            sens_cst.INPUT_MSK, None
        )
        overloaded_conf[sens_cst.SENSORS][sensor_image_key][
            sens_cst.INPUT_MSK
        ] = mask

        if (
            sens_cst.INPUT_MSK_CLASSES
            in conf[sens_cst.SENSORS][sensor_image_key]
        ):
            filled_with_none = True
            for _, value in conf[sens_cst.SENSORS][sensor_image_key][
                sens_cst.INPUT_MSK_CLASSES
            ].items():
                if value is not None:
                    filled_with_none = False
                    break

            if not filled_with_none and mask is None:
                logging.error("Mask classes were given with no mask associated")
                raise Exception(
                    "Mask classes were given with no mask associated"
                )

        mask_classes_dict = conf[sens_cst.SENSORS][sensor_image_key].get(
            "mask_classes", {}
        )
        updated_mask_classes = mask_classes_dict.copy()
        updated_mask_classes[
            sens_cst.IGNORED_BY_DENSE_MATCHING
        ] = mask_classes_dict.get(sens_cst.IGNORED_BY_DENSE_MATCHING, None)
        updated_mask_classes[sens_cst.SET_TO_REF_ALT] = mask_classes_dict.get(
            sens_cst.SET_TO_REF_ALT, None
        )
        updated_mask_classes[
            sens_cst.IGNORED_BY_SPARSE_MATCHING
        ] = mask_classes_dict.get(sens_cst.IGNORED_BY_SPARSE_MATCHING, None)
        # Check if protected keys are used
        mask_classes.check_mask_classes(updated_mask_classes)
        overloaded_conf[sens_cst.SENSORS][sensor_image_key][
            sens_cst.INPUT_MSK_CLASSES
        ] = updated_mask_classes

        # Validate
        checker_sensor.validate(
            overloaded_conf[sens_cst.SENSORS][sensor_image_key]
        )
        checker_mask_classes.validate(
            overloaded_conf[sens_cst.SENSORS][sensor_image_key][
                sens_cst.INPUT_MSK_CLASSES
            ]
        )

    # Validate pairs
    for (key1, key2) in overloaded_conf[sens_cst.PAIRING]:
        if key1 not in overloaded_conf[sens_cst.SENSORS]:
            logging.error("{} not in sensors images".format(key1))
            raise Exception("{} not in sensors images".format(key1))
        if key2 not in overloaded_conf["sensors"]:
            logging.error("{} not in sensors images".format(key2))
            raise Exception("{} not in sensors images".format(key2))

    # Modify to absolute path
    if config_json_dir is not None:
        for sensor_image_key in overloaded_conf[sens_cst.SENSORS]:
            sensor_image = overloaded_conf[sens_cst.SENSORS][sensor_image_key]
            for tag in [
                sens_cst.INPUT_IMG,
                sens_cst.INPUT_MSK,
                sens_cst.INPUT_GEO_MODEL,
                sens_cst.INPUT_COLOR,
            ]:
                if sensor_image[tag] is not None:
                    sensor_image[tag] = make_relative_path_absolute(
                        sensor_image[tag], config_json_dir
                    )

        for tag in [sens_cst.INITIAL_ELEVATION, sens_cst.ROI, sens_cst.GEOID]:
            if overloaded_conf[tag] is not None:
                if isinstance(overloaded_conf[tag], str):
                    overloaded_conf[tag] = make_relative_path_absolute(
                        overloaded_conf[tag], config_json_dir
                    )

    else:
        logging.debug(
            "path of config file was not given,"
            "relative path are not transformed to absolute paths"
        )

    # Transform ROI if needed
    # ROI can be list of 4 floats + epsg code, or file
    #

    if isinstance(overloaded_conf[sens_cst.ROI], str):
        # Parse file and transform to roi box

        overloaded_conf[sens_cst.ROI] = parse_roi_file(
            overloaded_conf[sens_cst.ROI]
        )

    # Check roi
    check_roi(overloaded_conf[sens_cst.ROI])

    # Check inputs data
    if overloaded_conf[sens_cst.CHECK_INPUTS]:
        for sensor_image_key in overloaded_conf[sens_cst.SENSORS]:
            sensor_image = overloaded_conf[sens_cst.SENSORS][sensor_image_key]
            check_input_data(
                sensor_image[sens_cst.INPUT_IMG],
                sensor_image[sens_cst.INPUT_MSK],
                sensor_image[sens_cst.INPUT_COLOR],
            )
    else:

        logging.info(
            "The inputs consistency will not be checked. "
            "To enable the inputs checking, add check_inputs: True "
            "to your input configuration"
        )

    # Check srtm dir
    check_srtm(overloaded_conf[sens_cst.INITIAL_ELEVATION])

    return overloaded_conf


def check_roi(roi):
    """
    Check roi given

    :param roi: roi : [bbox], epsg
    :type roi: tuple(list, str)
    """

    if roi is not None:
        roi_bbox, roi_epsg = roi

        # TODO check roi, and if epsg is valid
        if len(roi_bbox) != 4:
            raise Exception("Roid bounding box doesn't have the right format")
        if roi_epsg is not None:
            try:
                _ = fiona.crs.from_epsg(4326)
            except AttributeError as error:
                logging.error("ROI EPSG code {} not readable".format(error))


def check_srtm(srtm_dir):
    """
    Check srtm data

    :param srtm_dir: directory of srtm
    :type srtm_dir: str

    """

    if srtm_dir is not None:
        if os.path.isdir(srtm_dir):
            srtm_tiles = os.listdir(srtm_dir)
            if len(srtm_tiles) == 0:
                logging.warning(
                    "SRTM directory is empty, "
                    "the default altitude will be used as reference altitude."
                )
            else:
                logging.info(
                    "Indicated SRTM tiles valid regions "
                    "will be used as reference altitudes "
                    "(the default altitude is used "
                    "for undefined regions of the SRTM)"
                )
        else:
            # TODO add check for single file
            pass
    else:
        logging.info("The default altitude will be used as reference altitude.")


def parse_roi_file(arg_roi_file: str) -> Tuple[List[float], int]:
    """
    Parse ROI file argument and generate bounding box


    :param arg_roi_file : ROI file argument
    :return: ROI Bounding box + EPSG code : xmin, ymin, xmax, ymax, epsg_code
    :rtype: Tuple with array of 4 floats and int
    """

    # Declare output
    roi = None

    _, extension = os.path.splitext(arg_roi_file)

    # test file existence
    if not os.path.exists(arg_roi_file):
        logging.error("File {} does not exist".format(arg_roi_file))
    else:
        # if it is a vector file
        if extension in [".gpkg", ".shp", ".kml"]:
            roi_poly, roi_epsg = inputs.read_vector(arg_roi_file)
            roi = (roi_poly.bounds, roi_epsg)

        # if not, it is an image
        elif inputs.rasterio_can_open(arg_roi_file):
            data = rio.open(arg_roi_file)
            xmin = min(data.bounds.left, data.bounds.right)
            ymin = min(data.bounds.bottom, data.bounds.top)
            xmax = max(data.bounds.left, data.bounds.right)
            ymax = max(data.bounds.bottom, data.bounds.top)

            try:
                roi_epsg = data.crs.to_epsg()
                roi = ([xmin, ymin, xmax, ymax], roi_epsg)
            except AttributeError as error:
                logging.error("ROI EPSG code {} not readable".format(error))
                raise Exception(
                    "ROI EPSG code {} not readable".format(error)
                ) from error

        else:
            logging.error(
                "ROI file {} has an unsupported format".format(arg_roi_file)
            )
            raise Exception(
                "ROI file {} has an unsupported format".format(arg_roi_file)
            )

    return roi


def check_input_data(image, mask, color):
    """
    Check image, mask and color given

    Images must have same size

    :param image: image path
    :type image: str
    :param mask: mask path
    :type mask: str
    :param color: color path
    :type color: str
    """

    if inputs.rasterio_get_nb_bands(image) != 1:
        raise Exception("{} is not mono-band images".format(image))

    if mask is not None:
        if inputs.rasterio_get_size(image) != inputs.rasterio_get_size(mask):
            raise Exception(
                "The image {} and the mask {} "
                "do not have the same size".format(image, mask)
            )

    with rio.open(image) as img_reader:
        trans = img_reader.transform
        if trans.e < 0:
            logging.warning(
                "{} seems to have an incoherent pixel size. "
                "Input images has to be in sensor geometry.".format(image)
            )

    with rio.open(color) as img_reader:
        trans = img_reader.transform
        if trans.e < 0:
            logging.warning(
                "{} seems to have an incoherent pixel size. "
                "Input images has to be in sensor geometry.".format(image)
            )


def generate_inputs(conf):
    """
    Generate sensors inputs form inputs conf :

    a list of (sensor_left, sensor_right)

    :param conf: input conf
    :type conf: dict

    :return: list of sensors pairs
    :rtype: list(tuple(dict, dict))

    """

    # Get needed pairs
    pairs = conf[sens_cst.PAIRING]

    # Generate list of pairs
    list_sensor_pairs = []
    for (key1, key2) in pairs:
        merged_key = key1 + "_" + key2
        sensor1 = conf[sens_cst.SENSORS][key1]
        sensor2 = conf[sens_cst.SENSORS][key2]
        list_sensor_pairs.append((merged_key, sensor1, sensor2))

    return list_sensor_pairs
