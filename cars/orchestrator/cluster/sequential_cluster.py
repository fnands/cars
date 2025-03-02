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
Contains functions for sequential cluster
"""

# Standard imports

# Third party imports
from json_checker import Checker

# CARS imports
from cars.orchestrator.cluster import abstract_cluster


@abstract_cluster.AbstractCluster.register_subclass("sequential")
class SequentialCluster(abstract_cluster.AbstractCluster):
    """
    SequentialCluster
    """

    def __init__(  # pylint: disable=W0613
        self, conf_cluster, out_dir, launch_worker=True
    ):
        """
        Init function of SequentialCluster

        :param conf_cluster: configuration for cluster

        """

        self.check_conf(conf_cluster)

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
        overloaded_conf["mode"] = conf.get("mode", "sequential")

        cluster_schema = {"mode": str}

        # Check conf
        checker = Checker(cluster_schema)
        checker.validate(overloaded_conf)

        return overloaded_conf

    def cleanup(self):
        """
        Cleanup cluster

        """

    def create_task(self, func, nout=1):
        """
        Create task

        :param func: function
        :param nout: number of outputs
        """
        return func

    def start_tasks(self, task_list):
        """
        Start all tasks

        :param task_list: task list
        """
        return task_list

    def scatter(self, data, broadcast=True):  # pylint: disable=W0613
        """
        Distribute data through workers

        :param data: task data
        """
        return data

    def future_iterator(self, future_list):
        """
        Start all tasks

        :param future_list: future_list list
        """

        for future in future_list:
            yield future
