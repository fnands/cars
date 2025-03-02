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
this module contains the constants used in sensor_to_full_resolution
 pipeline.
"""

# Sensor input

INPUTS = "inputs"
OUTPUT = "output"
APPLICATIONS = "applications"
ORCHESTRATOR = "orchestrator"

SENSORS = "sensors"
PAIRING = "pairing"

EPSG = "epsg"
INITIAL_ELEVATION = "initial_elevation"

CHECK_INPUTS = "check_inputs"
DEFAULT_ALT = "default_alt"
ROI = "roi"
GEOID = "geoid"

INPUT_IMG = "image"
INPUT_MSK = "mask"
INPUT_MSK_CLASSES = "mask_classes"
INPUT_GEO_MODEL = "geomodel"
INPUT_MODEL_FILTER = "geomodel_filters"
INPUT_NODATA = "no_data"
INPUT_COLOR = "color"

# mask_classes constants
IGNORED_BY_DENSE_MATCHING = "ignored_by_dense_matching"
SET_TO_REF_ALT = "set_to_ref_alt"
IGNORED_BY_SPARSE_MATCHING = "ignored_by_sparse_matching"

# Pipeline output
OUT_DIR = "out_dir"
DSM_BASENAME = "dsm_basename"
CLR_BASENAME = "clr_basename"
INFO_BASENAME = "info_basename"
