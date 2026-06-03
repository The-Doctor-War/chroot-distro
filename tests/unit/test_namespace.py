"""Unit tests for namespace isolation helpers."""

from unittest.mock import MagicMock, mock_open, patch

import pytest

from chroot_distro.helpers import namespace as ns


def test_long_flags_to_nsenter_short():
    flags = ["--mount", "--pid", "--uts", "--ipc"]
    assert ns.long_flags_to_nsenter(flags, use_long=False) == ["-m", "-p", "-u", "-i"]


def test_holder_unshare_argv_adds_fork_with_pid():
    argv = ns._holder_unshare_argv("unshare", ["--pid", "--mount"])
    assert argv == ["unshare", "--fork", "--pid", "--mount", "sleep", "infinity"]


def test_holder_unshare_argv_no_duplicate_fork():
    argv = ns._holder_unshare_argv("unshare", ["--fork", "--mount"])
    assert argv.count("--fork") == 1
    assert argv[-2:] == ["sleep", "infinity"]


def test_pick_new_holder_pid():
    before = {10, 20}
    with patch.object(ns, "_snapshot_sleep_infinity_pids", return_value={10, 20, 99}):
        assert ns._pick_new_holder_pid(before) == 99


def test_pick_new_holder_pid_from_launcher_child():
    before: set[int] = set()
    with (
        patch.object(ns, "_snapshot_sleep_infinity_pids", return_value=set()),
        patch.object(ns, "_read_host_child_pids", return_value=[12345]),
        patch.object(ns, "_is_sleep_infinity_holder", side_effect=lambda pid: pid == 12345),
    ):
        assert ns._pick_new_holder_pid(before, launcher_pid=999) == 12345


def test_long_flags_to_nsenter_long():
    flags = ["--mount", "--pid"]
    assert ns.long_flags_to_nsenter(flags, use_long=True) == ["--mount", "--pid"]


@patch("chroot_distro.helpers.namespace.subprocess.run")
def test_probe_unshare_flags_requires_mount(mock_run):
    def side_effect(cmd, **kwargs):
        flag = cmd[1] if len(cmd) > 1 else ""
        rc = 0 if flag in ("--mount", "--pid") else 1
        return MagicMock(returncode=rc)

    mock_run.side_effect = side_effect
    flags = ns.probe_unshare_flags()
    assert "--mount" in flags
    assert "--pid" in flags


@patch("chroot_distro.helpers.namespace.subprocess.run")
def test_probe_unshare_flags_fails_without_mount(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    with pytest.raises(ns.NamespaceError, match="Mount namespace"):
        ns.probe_unshare_flags()


def test_check_isolation_conflicts_namespace_mode_without_flag():
    with (
        patch.object(ns, "get_live_holder", return_value=MagicMock(pid=1)),
        patch.object(ns, "read_isolation_mode", return_value=ns.ISOLATION_MODE_NAMESPACE),
        pytest.raises(ns.NamespaceError, match="isolated namespace mode"),
    ):
        ns.check_isolation_conflicts(
            "alpine",
            use_namespaces=False,
            host_mounts_exist=False,
        )


def test_check_isolation_conflicts_host_mounts_with_isolated():
    with (
        patch.object(ns, "get_live_holder", return_value=None),
        patch.object(ns, "read_isolation_mode", return_value=ns.ISOLATION_MODE_HOST),
        pytest.raises(ns.NamespaceError, match="host mount namespace"),
    ):
        ns.check_isolation_conflicts(
            "alpine",
            use_namespaces=True,
            host_mounts_exist=True,
        )


@patch("chroot_distro.helpers.namespace._pid_alive", return_value=True)
@patch("chroot_distro.helpers.namespace._read_holder_flags", return_value=["--mount"])
@patch("chroot_distro.helpers.namespace._read_holder_pid", return_value=42)
@patch("chroot_distro.helpers.namespace._nsenter_supports_long_flags", return_value=True)
def test_get_live_holder(*_mocks):
    holder = ns.get_live_holder("alpine")
    assert holder is not None
    assert holder.pid == 42
    assert holder.run_argv(["echo", "hi"])[0] == "nsenter"


@patch("chroot_distro.helpers.namespace.get_live_holder")
@patch("chroot_distro.helpers.namespace._create_holder")
@patch("chroot_distro.helpers.namespace.probe_unshare_flags", return_value=["--mount"])
def test_acquire_holder_reuses_existing(mock_probe, mock_create, mock_get):
    existing = MagicMock(pid=99)
    mock_get.return_value = existing
    assert ns.acquire_holder("alpine") is existing
    mock_create.assert_not_called()
    mock_probe.assert_not_called()


@patch("chroot_distro.helpers.namespace._remove_holder_state")
@patch("chroot_distro.helpers.namespace._read_holder_pid", return_value=100)
@patch("chroot_distro.helpers.namespace.os.kill")
def test_release_holder(mock_kill, *_mocks):
    ns.release_holder("alpine")
    assert mock_kill.called


def test_get_process_start_time():
    with patch("chroot_distro.helpers.namespace.os.stat") as mock_stat:
        mock_stat.return_value = MagicMock(st_mtime=12345.67)
        assert ns._get_process_start_time(42) == 12345.67

    with patch("chroot_distro.helpers.namespace.os.stat", side_effect=OSError):
        assert ns._get_process_start_time(42) is None


@patch("chroot_distro.helpers.namespace._remove_holder_state")
@patch("chroot_distro.helpers.namespace.os.path.isfile", return_value=True)
def test_read_holder_pid_success(mock_isfile, mock_remove_state):
    patch("builtins.open", mock_open(read_data="42\n12345.67\n")).start()
    try:
        with (
            patch("chroot_distro.helpers.namespace._pid_alive", return_value=True),
            patch("chroot_distro.helpers.namespace._is_sleep_infinity_holder", return_value=True),
            patch("chroot_distro.helpers.namespace._get_process_start_time", return_value=12345.67),
        ):
            assert ns._read_holder_pid("alpine") == 42
            mock_remove_state.assert_not_called()
    finally:
        patch.stopall()


@patch("chroot_distro.helpers.namespace._remove_holder_state")
@patch("chroot_distro.helpers.namespace.os.path.isfile", return_value=True)
def test_read_holder_pid_stale_start_time(mock_isfile, mock_remove_state):
    patch("builtins.open", mock_open(read_data="42\n12345.67\n")).start()
    try:
        with (
            patch("chroot_distro.helpers.namespace._pid_alive", return_value=True),
            patch("chroot_distro.helpers.namespace._is_sleep_infinity_holder", return_value=True),
            patch("chroot_distro.helpers.namespace._get_process_start_time", return_value=99999.99),
        ):
            assert ns._read_holder_pid("alpine") is None
            mock_remove_state.assert_called_once_with("alpine")
    finally:
        patch.stopall()


@patch("chroot_distro.helpers.namespace._remove_holder_state")
@patch("chroot_distro.helpers.namespace.os.path.isfile", return_value=True)
def test_read_holder_pid_dead_process(mock_isfile, mock_remove_state):
    patch("builtins.open", mock_open(read_data="42\n12345.67\n")).start()
    try:
        with (
            patch("chroot_distro.helpers.namespace._pid_alive", return_value=False),
        ):
            assert ns._read_holder_pid("alpine") is None
            mock_remove_state.assert_called_once_with("alpine")
    finally:
        patch.stopall()


@patch("chroot_distro.helpers.namespace.subprocess.Popen")
@patch("chroot_distro.helpers.namespace._pick_new_holder_pid", return_value=None)
@patch("chroot_distro.helpers.namespace._remove_holder_state")
def test_create_holder_fails_and_cleans_up(mock_remove_state, mock_pick, mock_popen):
    mock_proc = MagicMock()
    mock_popen.return_value = mock_proc

    with pytest.raises(ns.NamespaceError, match="Failed to locate namespace holder"):
        ns._create_holder("alpine", ["--mount"])

    mock_proc.kill.assert_called_once()
    mock_remove_state.assert_called()


@patch("chroot_distro.helpers.namespace._remove_holder_state")
@patch("chroot_distro.helpers.namespace._read_holder_pid", return_value=100)
@patch("chroot_distro.helpers.namespace.os.kill", side_effect=OSError("Permission denied"))
def test_release_holder_exception_safety(mock_kill, mock_read, mock_remove_state):
    ns.release_holder("alpine")
    mock_remove_state.assert_called_once_with("alpine")
