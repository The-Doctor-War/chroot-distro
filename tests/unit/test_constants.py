import os
from unittest.mock import patch

from chroot_distro.constants import (
    DEFAULT_LAYER_DOWNLOAD_WORKERS,
    MAX_LAYER_DOWNLOAD_WORKERS,
    layer_download_workers,
)


def test_layer_download_workers_default():
    with patch.dict(os.environ, {}, clear=True):
        assert layer_download_workers() == DEFAULT_LAYER_DOWNLOAD_WORKERS


def test_layer_download_workers_custom():
    with patch.dict(os.environ, {"CD_DOWNLOAD_WORKERS": "6"}):
        assert layer_download_workers() == 6


def test_layer_download_workers_max_clamp():
    with patch.dict(os.environ, {"CD_DOWNLOAD_WORKERS": "12"}):
        assert layer_download_workers() == 10
        assert MAX_LAYER_DOWNLOAD_WORKERS == 10


def test_layer_download_workers_min_clamp():
    with patch.dict(os.environ, {"CD_DOWNLOAD_WORKERS": "0"}):
        assert layer_download_workers() == 1


def test_layer_download_workers_invalid():
    with patch.dict(os.environ, {"CD_DOWNLOAD_WORKERS": "abc"}):
        assert layer_download_workers() == DEFAULT_LAYER_DOWNLOAD_WORKERS
