import json
import os
import sys

if sys.version_info >= (3, 14):
    import tarfile

    from compression import zstd
else:
    from backports import zstd
    from backports.zstd import tarfile
from unittest.mock import patch

from chroot_distro.commands.backup import command_backup
from chroot_distro.commands.restore import command_restore
from chroot_distro.parser import build_parser


@patch("chroot_distro.commands.backup.session.get_active_chroot_pids", return_value=[])
@patch("chroot_distro.commands.backup.mount_manager.get_active_mounts", return_value=[])
@patch("chroot_distro.commands.backup.ContainerLock")
@patch("chroot_distro.commands.restore.mount_manager.ensure_no_mounts")
@patch("chroot_distro.commands.restore.ContainerLock")
def test_backup_and_restore_end_to_end(
    mock_restore_lock,
    mock_ensure_no_mounts,
    mock_backup_lock,
    mock_get_active_mounts,
    mock_get_active_chroot_pids,
    tmp_path,
):
    # Setup paths inside tmp_path
    containers_dir = tmp_path / "containers"
    containers_dir.mkdir()

    # Define a container named "testcont"
    container_name = "testcont"
    cont_dir = containers_dir / container_name
    rootfs_dir = cont_dir / "rootfs"
    rootfs_dir.mkdir(parents=True)

    # 1. Create container files
    manifest_data = {"image": "alpine:latest", "architecture": "x86_64"}
    manifest_file = cont_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    # Add files/dirs in rootfs
    usr_bin = rootfs_dir / "usr" / "bin"
    usr_bin.mkdir(parents=True)

    test_file = usr_bin / "hello"
    test_file.write_text("echo hello")
    test_file.chmod(0o755)

    link_file = rootfs_dir / "bin_link"
    link_file.symlink_to("usr/bin/hello")

    # Backup destination
    backup_archive = tmp_path / "testcont_backup.tar.xz"

    # Build backup arguments
    parser = build_parser()
    backup_args = parser.parse_args(["backup", container_name, "--output", str(backup_archive)])

    # Patch paths to point to our temp containers directory
    with (
        patch("chroot_distro.paths.CONTAINERS_DIR", str(containers_dir)),
        patch("chroot_distro.commands.restore.CONTAINERS_DIR", str(containers_dir)),
    ):
        # 2. Run backup
        command_backup(backup_args)

        assert backup_archive.exists()

        # Verify the tar file has valid structure: <container_name>/manifest.json and <container_name>/rootfs/...
        with tarfile.open(backup_archive, "r:xz") as tf:
            names = tf.getnames()
            assert f"{container_name}/manifest.json" in names
            assert f"{container_name}/rootfs/usr/bin/hello" in names
            assert f"{container_name}/rootfs/bin_link" in names

            # Check file ownership in tar is zeroed
            info = tf.getmember(f"{container_name}/rootfs/usr/bin/hello")
            assert info.uid == 0
            assert info.gid == 0
            assert info.uname == ""
            assert info.gname == ""

        # 3. Simulate restoration to a new container named "restoredcont"
        # We can rename the archive file or restore directly.
        # But wait, restore command determines target container name from the top-level folder name inside the archive.
        # So it will restore to "testcont" again.
        # Let's delete "testcont" first.
        import shutil

        shutil.rmtree(cont_dir)
        assert not cont_dir.exists()

        # Build restore arguments
        restore_args = parser.parse_args(["restore", str(backup_archive)])

        # Run restore
        command_restore(restore_args)

        # 4. Verify restoration
        assert cont_dir.exists()
        assert manifest_file.exists()
        assert json.loads(manifest_file.read_text()) == manifest_data

        assert test_file.exists()
        assert test_file.read_text() == "echo hello"

        # Check permissions were restored (mode is preserved, masked by 0o7777)
        assert (test_file.stat().st_mode & 0o777) == 0o755

        # Check symlink was restored
        assert link_file.is_symlink()
        assert os.readlink(link_file) == "usr/bin/hello"


@patch("chroot_distro.commands.backup.session.get_active_chroot_pids", return_value=[])
@patch("chroot_distro.commands.backup.mount_manager.get_active_mounts", return_value=[])
@patch("chroot_distro.commands.backup.ContainerLock")
@patch("chroot_distro.commands.restore.mount_manager.ensure_no_mounts")
@patch("chroot_distro.commands.restore.ContainerLock")
def test_backup_and_restore_zstd(
    mock_restore_lock,
    mock_ensure_no_mounts,
    mock_backup_lock,
    mock_get_active_mounts,
    mock_get_active_chroot_pids,
    tmp_path,
):
    containers_dir = tmp_path / "containers_zst"
    containers_dir.mkdir()

    container_name = "testcontzst"
    cont_dir = containers_dir / container_name
    rootfs_dir = cont_dir / "rootfs"
    rootfs_dir.mkdir(parents=True)

    manifest_data = {"image": "alpine:latest", "architecture": "x86_64"}
    manifest_file = cont_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest_data))

    usr_bin = rootfs_dir / "usr" / "bin"
    usr_bin.mkdir(parents=True)

    test_file = usr_bin / "hello"
    test_file.write_text("echo hello")
    test_file.chmod(0o755)

    link_file = rootfs_dir / "bin_link"
    link_file.symlink_to("usr/bin/hello")

    backup_archive = tmp_path / "testcont_backup.tar.zst"

    parser = build_parser()
    backup_args = parser.parse_args(["backup", container_name, "--output", str(backup_archive)])

    with (
        patch("chroot_distro.paths.CONTAINERS_DIR", str(containers_dir)),
        patch("chroot_distro.commands.restore.CONTAINERS_DIR", str(containers_dir)),
    ):
        command_backup(backup_args)

        assert backup_archive.exists()

        with zstd.ZstdFile(backup_archive, "rb") as zs, tarfile.open(fileobj=zs, mode="r:") as tf:
            names = tf.getnames()
            assert f"{container_name}/manifest.json" in names
            assert f"{container_name}/rootfs/usr/bin/hello" in names
            assert f"{container_name}/rootfs/bin_link" in names

        import shutil
        shutil.rmtree(cont_dir)
        assert not cont_dir.exists()

        restore_args = parser.parse_args(["restore", str(backup_archive)])
        command_restore(restore_args)

        assert cont_dir.exists()
        assert manifest_file.exists()
        assert json.loads(manifest_file.read_text()) == manifest_data
        assert test_file.exists()
        assert test_file.read_text() == "echo hello"
        assert (test_file.stat().st_mode & 0o777) == 0o755
        assert link_file.is_symlink()
        assert os.readlink(link_file) == "usr/bin/hello"
