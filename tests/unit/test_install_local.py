from unittest.mock import MagicMock
import pytest

from chroot_distro.commands import install_local


def test_oci_read_json_rejects_non_regular_file():
    tf = MagicMock()
    member = MagicMock()
    member.isreg.return_value = False
    member_map = {"index.json": member}

    with pytest.raises(RuntimeError, match="not a regular file"):
        install_local._oci_read_json(tf, member_map, "index.json")


def test_oci_cache_layer_rejects_non_regular_file():
    tf = MagicMock()
    member = MagicMock()
    member.isreg.return_value = False
    digest = "sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    blob_path = "blobs/sha256/1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    member_map = {blob_path: member}

    with pytest.raises(RuntimeError, match="not a regular file"):
        install_local._oci_cache_layer(tf, member_map, digest)
