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
Contains functions for wrapper disk
"""

# Standard imports
import logging
import os
import shutil
from abc import ABCMeta, abstractmethod

import pandas

# Third party imports
import xarray as xr

# CARS imports
from cars.data_structures import cars_dataset

# Third party imports


DENSE_NAME = "DenseDO"
SPARSE_NAME = "SparseDO"


class AbstractWrapper(metaclass=ABCMeta):
    """
    AbstractWrapper
    """

    @abstractmethod
    def get_obj(self, obj):
        """
        Get Object

        :param obj: object to transform

        :return: object
        """

    @abstractmethod
    def get_function_and_kwargs(self, func, kwargs, nout=1):
        """
        Get function to apply and overloaded key arguments

        :param func: function to run
        :param kwargs: key arguments of func
        :param nout: number of outputs

        :return: function to apply, overloaded key arguments
        """

    @abstractmethod
    def cleanup(self):
        """
        Cleanup tmp_dir
        """


class WrapperNone(AbstractWrapper):
    """
    AbstractWrapper
    """

    def __init__(self, tmp_dir):
        """
        Init function of WrapperDisk

        :param tmp_dir: temporary directory
        """

    def get_obj(self, obj):
        """
        Get Object

        :param obj: object to transform

        :return: object
        """
        return obj

    def get_function_and_kwargs(self, func, kwargs, nout=1):
        """
        Get function to apply and overloaded key arguments

        :param func: function to run
        :param kwargs: key arguments of func
        :param nout: number of outputs

        :return: function to apply, overloaded key arguments
        """

        # apply disk wrapper
        new_func = none_wrapper_fun

        # Get overloaded key arguments

        new_kwargs = kwargs
        new_kwargs["fun"] = func

        return new_func, kwargs

    def cleanup(self):
        """
        Cleanup tmp_dir
        """


class WrapperDisk(AbstractWrapper):

    """
    WrapperDisk
    """

    def __init__(self, tmp_dir):
        """
        Init function of WrapperDisk

        :param tmp_dir: temporary directory
        """

        self.tmp_dir = os.path.join(tmp_dir, "tmp")
        if not os.path.exists(self.tmp_dir):
            os.makedirs(self.tmp_dir)

        self.current_object_id = 0

    def cleanup(self):
        """
        Cleanup tmp_dir
        """

        logging.info("Clean tmp directory ...")
        shutil.rmtree(self.tmp_dir)

    def get_function_and_kwargs(self, func, kwargs, nout=1):
        """
        Get function to apply and overloaded key arguments

        :param func: function to run
        :param kwargs: key arguments of func
        :param nout: number of outputs

        :return: function to apply, overloaded key arguments
        """

        # apply disk wrapper
        new_func = disk_wrapper_fun

        # Get overloaded key arguments
        # Create ids
        id_list = []
        for _ in range(nout):
            id_list.append(self.current_object_id)
            self.current_object_id += 1

        new_kwargs = kwargs
        new_kwargs["id_list"] = id_list
        new_kwargs["fun"] = func
        new_kwargs["tmp_dir"] = self.tmp_dir

        return new_func, new_kwargs

    def get_obj(self, obj):
        """
        Get Object

        :param obj: object to transform

        :return: object
        """
        res = load(obj)
        return res


def none_wrapper_fun(*argv, **kwargs):
    """
    Create a wrapper for functionn running it

    :param argv: args of func
    :param kwargs: kwargs of func

    :return: path to results
    """

    func = kwargs["fun"]
    kwargs.pop("fun")

    return func(*argv, **kwargs)


def disk_wrapper_fun(*argv, **kwargs):
    """
    Create a wrapper for function

    :param argv: args of func
    :param kwargs: kwargs of func

    :return: path to results
    """

    # Get function to wrap and id_list
    id_list = kwargs["id_list"]
    func = kwargs["fun"]
    tmp_dir = kwargs["tmp_dir"]
    kwargs.pop("id_list")
    kwargs.pop("fun")
    kwargs.pop("tmp_dir")

    # load args
    loaded_argv = load_args(argv)
    loaded_kwargs = load_kwargs(kwargs)

    # call function
    res = func(*loaded_argv, **loaded_kwargs)

    if res is not None:
        to_disk_res = dump(res, tmp_dir, id_list)
    else:
        to_disk_res = res

    return to_disk_res


def load_args(args):
    """
    Load args from disk to memory

    :param argv: args of func

    :return: new args
    """

    new_args = []
    for arg in args:
        if isinstance(arg, list):
            list_arg = load_args(arg)
            new_args.append(list_arg)

        else:
            if is_dumped_object(arg):
                new_args.append(load(arg))
            else:
                new_args.append(arg)

    return new_args


def load_kwargs(kwargs):
    """
    Load key args from disk to memory

    :param kwargs: keyargs of func

    :return: new kwargs
    """

    new_kwargs = {}
    for key in kwargs:
        if is_dumped_object(kwargs[key]):
            new_kwargs[key] = load(kwargs[key])
        else:
            new_kwargs[key] = kwargs[key]

    return new_kwargs


def is_dumped_object(obj):
    """
    Check if a given object is dumped

    :param obj: object

    :return: is dumped
    :rtype: bool
    """

    is_dumped = False
    if isinstance(obj, str):
        if DENSE_NAME in obj or SPARSE_NAME in obj:
            is_dumped = True

    return is_dumped


def load(path):
    """
    Load object from disk

    :param path: path
    :type path: str

    :return: object
    """

    if path is not None:
        obj = path
        if DENSE_NAME in path:
            obj = cars_dataset.CarsDataset("arrays").load_single_tile(path)

        elif SPARSE_NAME in path:
            obj = cars_dataset.CarsDataset("points").load_single_tile(path)

        else:
            logging.warning("Not a dumped arrays or points")
    else:
        obj = None
    return obj


def dump_single_object(obj, path):
    """
    Dump object to disk

    :param path: path
    :type path: str
    """

    if isinstance(obj, xr.Dataset):
        # is from array
        cars_dataset.CarsDataset("arrays").save_single_tile(obj, path)
    elif isinstance(obj, pandas.DataFrame):
        # is from points
        cars_dataset.CarsDataset("points").save_single_tile(obj, path)
    else:
        raise Exception("Not an arrays or points")


def create_path(obj, tmp_dir, id_num):
    """
    Create path where to dump object

    :param tmp_dir: tmp_dir
    :param id_num: id of object

    :return: path
    """

    path = None

    if isinstance(obj, xr.Dataset):
        # is from array
        path = DENSE_NAME
    elif isinstance(obj, pandas.DataFrame):
        # is from points
        path = SPARSE_NAME
    else:
        logging.warning("Not an arrays or points")
        path = obj

    path = os.path.join(tmp_dir, path + "_" + repr(id_num))

    return path


def dump(res, tmp_dir, id_list):
    """
    Dump results to tmp_dir, according to ids

    :param res: objects to dump
    :param tmp_dir: tmp_dir
    :param id_list: list of ids of objects

    :return: path
    """

    paths = None

    if len(id_list) > 1:
        paths = []
        for i, single_id in enumerate(id_list):
            if res[i] is not None:
                path = create_path(res[i], tmp_dir, single_id)
                dump_single_object(res[i], path)
                paths.append(path)
            else:
                paths.append(None)

        paths = (*paths,)

    else:
        paths = create_path(res, tmp_dir, id_list[0])
        dump_single_object(res, paths)

    return paths
