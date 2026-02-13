#!/usr/bin/env python3
"""
serviced.py - Lightweight service manager for systemd .service files
              Runs services as background processes without systemd.

Inspired by systemctl3.py but drastically simplified (~600 lines vs ~7000).
Designed for chroot environments and systems without systemd.

Usage:
    serviced.py <command> [options] [service]

Commands:
    start     <service>   Start a service
    stop      <service>   Stop a service
    restart   <service>   Restart a service
    status    <service>   Show service status
    log       <service>   Show service log (last 50 lines)
    list                  List all discovered services
    list-running          List only currently running services

Options:
    --dry-run             Show what would be done without doing it
    -v, --verbose         Show debug output
    -n, --lines NUM       Number of log lines to show (default: 50)
"""

from __future__ import print_function

import argparse
import datetime
import grp
import json
import os
import pwd
import re
import shlex
import signal
import subprocess
import sys
import time

VERSION = "0.1.0"

UNIT_PATHS = [
    "/etc/systemd/system",
    "/usr/local/lib/systemd/system",
    "/usr/lib/systemd/system",
    "/lib/systemd/system",
]

STATE_DIR = "/tmp/serviced"
PID_DIR = os.path.join(STATE_DIR, "pids")
LOG_DIR = os.path.join(STATE_DIR, "logs")
STATUS_DIR = os.path.join(STATE_DIR, "status")

ENABLED_DIR = "/var/lib/serviced/enabled"
ACTION_LOG_FILE = "/var/lib/serviced/serviced.log"

CRITICAL_SERVICES = {
    # systemd internals
    "systemd-journald",
    "systemd-logind",
    "systemd-udevd",
    "systemd-resolved",
    "systemd-networkd",
    "systemd-timesyncd",
    "systemd-tmpfiles-setup",
    "systemd-tmpfiles-clean",
    "systemd-sysctl",
    "systemd-modules-load",
    "systemd-remount-fs",
    "systemd-update-utmp",
    "systemd-random-seed",
    "systemd-hibernate-resume",
    "systemd-suspend",
    "systemd-halt",
    "systemd-poweroff",
    "systemd-reboot",
    "systemd-kexec",
    "systemd-machine-id-commit",
    "systemd-binfmt",
    "systemd-coredump",
    "systemd-ask-password-console",
    "systemd-ask-password-wall",
    "systemd-boot-random-seed",
    "systemd-fsck",
    "systemd-growfs",
    "systemd-makefs",
    "systemd-pstore",
    "systemd-quotacheck",
    "systemd-vconsole-setup",
    "systemd-firstboot",
    "systemd-sysusers",
    "systemd-homed",
    "systemd-userdbd",
    "systemd-oomd",
    # core system
    "init",
    "dbus",
    "dbus-broker",
    "dbus-daemon",
    "udev",
    "eudev",
    "mdev",
    # login / session
    "getty@tty1",
    "serial-getty@",
    # mount / filesystem
    "local-fs.target",
    "remote-fs.target",
    "swap.target",
    "tmp.mount",
    "dev-hugepages.mount",
    "dev-mqueue.mount",
    "sys-kernel-debug.mount",
    "sys-kernel-tracing.mount",
    "sys-fs-fuse-connections.mount",
}

UNSUPPORTED_TYPES = {"dbus"}

CRITICAL_PREFIXES = (
    "systemd-",
    "initrd-",
    "rescue.",
    "emergency.",
    "halt.",
    "poweroff.",
    "reboot.",
    "kexec.",
)

VERBOSE = False
QUIET = False


def log_info(msg, *args):
    if not QUIET:
        print("[INFO]", msg % args if args else msg)


def log_warn(msg, *args):
    print("[WARN]", msg % args if args else msg, file=sys.stderr)


def log_error(msg, *args):
    print("[ERROR]", msg % args if args else msg, file=sys.stderr)


def log_debug(msg, *args):
    if VERBOSE:
        print("[DEBUG]", msg % args if args else msg, file=sys.stderr)


def log_action(msg, *args):
    """Log an action to the persistent log file."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = msg % args if args else msg
        entry = "[%s] %s\n" % (timestamp, formatted_msg)
        with open(ACTION_LOG_FILE, "a") as f:
            f.write(entry)
    except (IOError, OSError):
        pass  # Best effort logging


def ensure_dirs():
    """Create state directories if they don't exist."""
    for d in [STATE_DIR, PID_DIR, LOG_DIR, STATUS_DIR]:
        os.makedirs(d, mode=0o755, exist_ok=True)

    try:
        os.makedirs(ENABLED_DIR, mode=0o755, exist_ok=True)
    except PermissionError:
        pass


def is_critical_service(name):
    """Check if a service name is in the critical blocklist."""
    base = name.replace(".service", "")
    if base in CRITICAL_SERVICES:
        return True
    if name.startswith(CRITICAL_PREFIXES):
        return True
    # template units (e.g. getty@.service)
    if "@." in name:
        return True
    return False


def pid_exists(pid):
    """Check if a PID exists and is not a zombie."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but we can't signal it
    # check zombie
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("State:"):
                    return "Z" not in line
    except (IOError, OSError):
        pass
    return True


class UnitFile:
    """Parses a systemd .service unit file into sections and key-value pairs."""

    def __init__(self, path=None):
        self.path = path
        self._data = {}  # section -> {key -> [values]}
        if path:
            self.parse(path)

    def parse(self, path):
        """Parse a .service file."""
        self.path = path
        self._data = {}
        section = None
        try:
            with open(path, "r") as f:
                prev_line = ""
                for raw_line in f:
                    line = raw_line.rstrip("\n")
                    # Handle line continuation
                    if line.endswith("\\"):
                        prev_line += line[:-1].strip() + " "
                        continue
                    if prev_line:
                        line = prev_line + line.strip()
                        prev_line = ""
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith("#") or line.startswith(";"):
                        continue
                    m = re.match(r"^\[(.+)\]$", line)
                    if m:
                        section = m.group(1)
                        if section not in self._data:
                            self._data[section] = {}
                        continue
                    if section and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if key not in self._data[section]:
                            self._data[section][key] = []
                        # Empty value resets the list (systemd behavior)
                        if value == "":
                            self._data[section][key] = []
                        else:
                            self._data[section][key].append(value)
        except (IOError, OSError) as e:
            log_debug("Failed to parse %s: %s", path, e)

    def get(self, section, key, default=""):
        """Get the last value for a key (most specific)."""
        try:
            values = self._data[section][key]
            return values[-1] if values else default
        except KeyError:
            return default

    def getlist(self, section, key):
        """Get all values for a key (for ExecStart, etc.)."""
        try:
            return list(self._data[section][key])
        except KeyError:
            return []

    def getbool(self, section, key, default=False):
        """Get a boolean value."""
        val = self.get(section, key, "")
        if not val:
            return default
        return val.lower() in ("yes", "true", "1", "on")

    def has_section(self, section):
        return section in self._data

    @property
    def description(self):
        return self.get("Unit", "Description", os.path.basename(self.path or "unknown"))

    @property
    def service_type(self):
        return self.get("Service", "Type", "simple").lower()

    @property
    def exec_start(self):
        return self.getlist("Service", "ExecStart")

    @property
    def exec_stop(self):
        return self.getlist("Service", "ExecStop")

    @property
    def exec_start_pre(self):
        return self.getlist("Service", "ExecStartPre")

    @property
    def exec_start_post(self):
        return self.getlist("Service", "ExecStartPost")

    @property
    def pid_file(self):
        return self.get("Service", "PIDFile", "")

    @property
    def working_directory(self):
        return self.get("Service", "WorkingDirectory", "")

    @property
    def user(self):
        return self.get("Service", "User", "")

    @property
    def group(self):
        return self.get("Service", "Group", "")

    @property
    def environment(self):
        """Return environment variables as a dict."""
        env = {}
        for val in self.getlist("Service", "Environment"):
            # Can be KEY=VAL or "KEY=VAL"
            val = val.strip('"').strip("'")
            if "=" in val:
                k, _, v = val.partition("=")
                env[k.strip()] = v.strip()
        return env

    @property
    def environment_file(self):
        return self.get("Service", "EnvironmentFile", "")

    @property
    def remain_after_exit(self):
        return self.getbool("Service", "RemainAfterExit", False)

    @property
    def requires(self):
        val = self.get("Unit", "Requires", "")
        return val.split() if val else []

    @property
    def wants(self):
        val = self.get("Unit", "Wants", "")
        return val.split() if val else []

    @property
    def after(self):
        val = self.get("Unit", "After", "")
        return val.split() if val else []


def parse_exec_cmd(cmd_str):
    """Parse a systemd ExecStart/ExecStop command string.

    Handles prefixes like -, +, !, !! and returns (check_errors, cmd_list).
    """
    cmd = cmd_str.strip()
    check_errors = True
    # Strip systemd exec prefixes
    while cmd and cmd[0] in "-+!@:":
        if cmd[0] == "-":
            check_errors = False
        cmd = cmd[1:]
    cmd = cmd.strip()
    if not cmd:
        return check_errors, []
    # Use shlex to handle quoting
    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = cmd.split()
    return check_errors, parts


def expand_env(cmd_parts, env):
    """Expand $VAR and ${VAR} references in command arguments.

    After expansion, empty strings are removed to avoid passing
    empty positional arguments (e.g. $OPTIONS='' becoming "").
    """
    result = []
    for part in cmd_parts:
        expanded = part
        # Expand ${VAR} style
        for m in re.finditer(r"\$\{([^}]+)\}", part):
            var = m.group(1)
            val = env.get(var, os.environ.get(var, ""))
            expanded = expanded.replace(m.group(0), val)
        # Expand $VAR style (but not ${ which we already handled)
        for m in re.finditer(r"\$([A-Za-z_][A-Za-z0-9_]*)", expanded):
            var = m.group(1)
            val = env.get(var, os.environ.get(var, ""))
            expanded = expanded.replace(m.group(0), val)
        # If the entire part was a variable that expanded to empty, skip it
        if expanded == "" and part != expanded:
            continue
        result.append(expanded)
    return result


def strip_socket_activation(cmd_parts):
    """Remove -H fd:// from command args since we can't do systemd socket activation.

    Without systemd, 'fd://' listeners don't work because there's no
    socket file descriptor passed by the init system. Services like
    dockerd will fall back to their default socket (e.g. /var/run/docker.sock).
    """
    result = []
    skip_next = False
    for i, part in enumerate(cmd_parts):
        if skip_next:
            skip_next = False
            continue
        # Handle '-H fd://' as two args or combined
        if (
            part == "-H"
            and i + 1 < len(cmd_parts)
            and cmd_parts[i + 1].startswith("fd://")
        ):
            log_debug("Stripping socket activation: -H %s", cmd_parts[i + 1])
            skip_next = True
            continue
        if part.startswith("-H=fd://") or part == "--host=fd://":
            log_debug("Stripping socket activation: %s", part)
            continue
        result.append(part)
    return result


def load_environment_file(path):
    """Load environment variables from a file (EnvironmentFile= directive)."""
    env = {}
    # Handle the - prefix (don't error if file missing)
    optional = False
    if path.startswith("-"):
        optional = True
        path = path[1:].strip()
    if not os.path.isfile(path):
        if not optional:
            log_warn("EnvironmentFile not found: %s", path)
        return env
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    env[key] = value
    except (IOError, OSError) as e:
        if not optional:
            log_warn("Failed to read EnvironmentFile %s: %s", path, e)
    return env


class ServiceManager:
    """Discovers, starts, stops, and monitors services."""

    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self._units = {}  # name -> UnitFile
        self._discovered = False

    def discover_services(self):
        """Scan unit file directories and load all .service files."""
        if self._discovered:
            return
        seen = set()
        for unit_dir in UNIT_PATHS:
            if not os.path.isdir(unit_dir):
                continue
            for fname in sorted(os.listdir(unit_dir)):
                if not fname.endswith(".service"):
                    continue
                if fname in seen:
                    continue  # first match wins (like systemd)
                seen.add(fname)
                fpath = os.path.join(unit_dir, fname)
                # Resolve symlinks
                if os.path.islink(fpath):
                    target = os.readlink(fpath)
                    if target == "/dev/null":
                        continue  # masked service
                    if not os.path.isabs(target):
                        target = os.path.join(unit_dir, target)
                    if not os.path.exists(target):
                        continue
                    fpath = target
                try:
                    unit = UnitFile(fpath)
                    self._units[fname] = unit
                except Exception as e:
                    log_debug("Failed to load %s: %s", fpath, e)
        self._discovered = True
        log_debug("Discovered %d services", len(self._units))

    def get_unit(self, name):
        """Get a unit by name, auto-appending .service if needed."""
        self.discover_services()
        if not name.endswith(".service"):
            name = name + ".service"
        return self._units.get(name)

    def resolve_name(self, name):
        """Normalize service name."""
        if not name.endswith(".service"):
            name = name + ".service"
        return name

    def _pid_path(self, name):
        return os.path.join(PID_DIR, name + ".pid")

    def _log_path(self, name):
        return os.path.join(LOG_DIR, name + ".log")

    def _status_path(self, name):
        return os.path.join(STATUS_DIR, name + ".json")

    def _read_pid(self, name):
        """Read stored PID for a service. Returns 0 if not found."""
        path = self._pid_path(name)
        try:
            with open(path) as f:
                return int(f.read().strip())
        except (IOError, OSError, ValueError):
            return 0

    def _write_pid(self, name, pid):
        """Store PID for a service."""
        ensure_dirs()
        with open(self._pid_path(name), "w") as f:
            f.write(str(pid))

    def _remove_pid(self, name):
        """Remove PID file for a service."""
        try:
            os.unlink(self._pid_path(name))
        except (IOError, OSError):
            pass

    def _write_status(self, name, state, pid=0, msg=""):
        """Write status info as JSON."""
        ensure_dirs()
        data = {
            "state": state,
            "pid": pid,
            "message": msg,
            "timestamp": datetime.datetime.now().isoformat(),
        }
        with open(self._status_path(name), "w") as f:
            json.dump(data, f)

    def _read_status(self, name):
        """Read status JSON. Returns dict or None."""
        try:
            with open(self._status_path(name)) as f:
                return json.load(f)
        except (IOError, OSError, ValueError):
            return None

    def _remove_status(self, name):
        try:
            os.unlink(self._status_path(name))
        except (IOError, OSError):
            pass

    def _build_env(self, unit):
        """Build the environment dict for a service."""
        env = dict(os.environ)
        # Load EnvironmentFile
        env_file = unit.environment_file
        if env_file:
            env.update(load_environment_file(env_file))
        # Load inline Environment=
        env.update(unit.environment)
        return env

    def _pkill_service(self, name, unit):
        """Aggressively kill old processes matching the service."""
        # 1. Kill by tracked PID
        pid = self._read_pid(name)
        if pid and pid_exists(pid):
            log_debug("Killing tracked PID %d for %s", pid, name)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            time.sleep(0.1)
            if pid_exists(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
            self._remove_pid(name)

        cmds = unit.exec_start
        if not cmds:
            return

        cmd_parts = shlex.split(cmds[0]) if cmds else []
        if not cmd_parts:
            return

        binary = os.path.basename(cmd_parts[0])

        if binary in ("bash", "sh", "python", "python3", "perl", "ruby"):
            return

        log_debug("Attempting pkill for '%s'", binary)
        try:
            # pkill -f matches full command line, possibly safer if we include args
            # But stripped binary name is safer to avoid matching random stuff
            subprocess.run(
                ["pkill", "-x", binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def _run_cmd(self, cmd_str, env, unit, wait=True, log_file=None):
        """Run a single command string. Returns (returncode, pid).

        If wait=False, starts the process in background and returns immediately.
        """
        check, parts = parse_exec_cmd(cmd_str)
        if not parts:
            return (0, 0)
        parts = expand_env(parts, env)
        # Strip fd:// socket activation args (requires systemd socket passing)
        parts = strip_socket_activation(parts)
        if not parts:
            return (0, 0)
        log_debug("Running: %s", " ".join(parts))

        if self.dry_run:
            log_info("[DRY RUN] Would execute: %s", " ".join(parts))
            return (0, 12345)

        if cwd and not os.path.isdir(cwd):
            cwd = None

        uid = None
        gid = None
        if unit.user:
            try:
                pw = pwd.getpwnam(unit.user)
                uid = pw.pw_uid
                gid = pw.pw_gid
            except KeyError:
                log_warn("User '%s' not found, running as current user", unit.user)
        if unit.group:
            try:
                gr = grp.getgrnam(unit.group)
                gid = gr.gr_gid
            except KeyError:
                log_warn("Group '%s' not found", unit.group)

        def preexec():
            os.setsid()  # detach from parent process group
            if gid is not None:
                try:
                    os.setgid(gid)
                except OSError:
                    pass
            if uid is not None:
                try:
                    os.setuid(uid)
                except OSError:
                    pass

        try:
            if wait:
                result = subprocess.run(
                    parts,
                    env=env,
                    cwd=cwd,
                    preexec_fn=preexec if (uid or gid) else None,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=120,
                )
                if result.returncode != 0:
                    stderr_out = result.stderr.decode("utf-8", errors="replace").strip()
                    if stderr_out:
                        log_debug("stderr: %s", stderr_out)
                    # Write stderr to log file if available
                    if log_file and stderr_out:
                        try:
                            with open(log_file, "a") as lf:
                                lf.write(stderr_out + "\n")
                        except (IOError, OSError):
                            pass
                return (result.returncode, 0)
            else:
                # Background process with log capture
                if log_file:
                    lf = open(log_file, "a")
                else:
                    lf = open(os.devnull, "w")
                proc = subprocess.Popen(
                    parts,
                    env=env,
                    cwd=cwd,
                    preexec_fn=preexec if (uid or gid) else os.setsid,
                    stdout=lf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                )
                return (None, proc.pid)
        except FileNotFoundError:
            log_error("Command not found: %s", parts[0])
            return (127, 0)
        except PermissionError:
            log_error("Permission denied: %s", parts[0])
            return (126, 0)
        except Exception as e:
            log_error("Failed to execute %s: %s", parts[0], e)
            return (1, 0)

    def _start_dependencies(self, name, unit):
        """Start Requires= and Wants= service dependencies.

        Only starts .service dependencies (skips .socket, .target, etc.).
        Uses a _starting set to prevent circular dependency loops.
        """
        if not hasattr(self, "_starting"):
            self._starting = set()
        if name in self._starting:
            return  # prevent circular deps
        self._starting.add(name)

        deps = []
        # Requires= are mandatory, Wants= are best-effort
        for dep in unit.requires + unit.wants:
            if dep.endswith(".service") and dep != name:
                deps.append(dep)

        for dep in deps:
            dep_pid = self._read_pid(dep)
            if dep_pid and pid_exists(dep_pid):
                log_debug("Dependency %s already running (PID %d)", dep, dep_pid)
                continue
            if is_critical_service(dep):
                log_debug("Skipping critical dependency: %s", dep)
                continue
            dep_unit = self.get_unit(dep)
            if not dep_unit:
                log_debug("Dependency %s not found, skipping", dep)
                continue
            if dep_unit.service_type in UNSUPPORTED_TYPES:
                log_debug("Dependency %s has unsupported type, skipping", dep)
                continue
            log_info("Starting dependency: %s", dep)
            self.start(dep)

        self._starting.discard(name)

    def start(self, name):
        """Start a service."""
        name = self.resolve_name(name)
        log_action("START request for %s", name)

        if is_critical_service(name):
            log_error("Refusing to manage critical service: %s", name)
            return False

        unit = self.get_unit(name)
        if not unit:
            log_error("Service not found: %s", name)
            return False

        stype = unit.service_type
        if stype in UNSUPPORTED_TYPES:
            log_error("Unsupported service type '%s' for %s", stype, name)
            return False

        # Aggressive cleanup before start to ensure fresh state
        self._pkill_service(name, unit)

        if cond_path:
            negate = cond_path.startswith("!")
            check_path = cond_path.lstrip("!")
            exists = os.path.exists(check_path)
            if (negate and exists) or (not negate and not exists):
                if VERBOSE:
                    log_warn("ConditionPathExists failed for %s: %s", name, cond_path)
                return False

        self._start_dependencies(name, unit)

        if VERBOSE:
            log_info("Starting %s (%s)...", name, unit.description)

        env = self._build_env(unit)
        ensure_dirs()

        # Write initial log header
        log_file = self._log_path(name)
        if not self.dry_run:
            with open(log_file, "a") as lf:
                lf.write(
                    "\n--- %s START %s ---\n"
                    % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), name)
                )

        for cmd in unit.exec_start_pre:
            check, _ = parse_exec_cmd(cmd)
            rc, _ = self._run_cmd(cmd, env, unit, wait=True)
            if rc and check:
                log_error("ExecStartPre failed for %s (exit %d)", name, rc)
                if not self.dry_run:
                    self._write_status(name, "failed", msg="ExecStartPre failed")
                return False

        if stype == "oneshot":
            return self._start_oneshot(name, unit, env)
        elif stype == "forking":
            return self._start_forking(name, unit, env)
        else:
            # simple, exec, notify, idle
            return self._start_simple(name, unit, env)

    def _start_simple(self, name, unit, env):
        """Start a simple/exec/notify/idle service."""
        log_file = self._log_path(name)
        cmds = unit.exec_start
        if not cmds:
            log_error("No ExecStart defined for %s", name)
            self._write_status(name, "failed", msg="No ExecStart")
            return False

        cmd = cmds[-1]
        env["MAINPID"] = ""
        rc, pid = self._run_cmd(cmd, env, unit, wait=False, log_file=log_file)

        if pid <= 0 and not self.dry_run:
            log_error("Failed to start %s", name)
            self._write_status(name, "failed", msg="Failed to start process")
            return False

        if not self.dry_run:
            self._write_pid(name, pid)
            self._write_status(name, "active", pid=pid)
        env["MAINPID"] = str(pid)

        if not self.dry_run:
            stype = unit.service_type
            wait_time = 1.5 if stype in ("notify", "notify-reload") else 0.5
            time.sleep(wait_time)
            if not pid_exists(pid):
                # Check if RemainAfterExit is set
                if unit.remain_after_exit:
                    log_info("%s started and exited (RemainAfterExit=yes)", name)
                    if not self.dry_run:
                        self._write_status(
                            name, "active", pid=0, msg="Exited (RemainAfterExit)"
                        )
                else:
                    log_error("%s started but exited immediately", name)
                    if not self.dry_run:
                        self._write_status(
                            name, "failed", pid=0, msg="Exited immediately"
                        )
                        self._remove_pid(name)
                    return False

        if VERBOSE:
            log_info("%s started (PID %d)", name, pid)

        for cmd in unit.exec_start_post:
            self._run_cmd(cmd, env, unit, wait=True)

        return True

    def _start_forking(self, name, unit, env):
        """Start a forking service."""
        log_file = self._log_path(name)
        cmds = unit.exec_start
        if not cmds:
            log_error("No ExecStart defined for %s", name)
            return False

        for cmd in cmds:
            rc, _ = self._run_cmd(cmd, env, unit, wait=True, log_file=log_file)
            check, _ = parse_exec_cmd(cmd)
            if rc and check:
                log_error("ExecStart failed for %s (exit %d)", name, rc)
                self._write_status(name, "failed", msg="ExecStart failed")
                return False

        pid = 0
        pid_file = unit.pid_file
        if pid_file:
            for _ in range(20):
                if os.path.isfile(pid_file):
                    try:
                        with open(pid_file) as f:
                            pid = int(f.read().strip())
                        break
                    except (IOError, ValueError):
                        pass
                if not self.dry_run:
                    time.sleep(0.2)

        if pid and pid_exists(pid):
            if not self.dry_run:
                self._write_pid(name, pid)
                self._write_status(name, "active", pid=pid)
            if VERBOSE:
                log_info("%s started (PID %d from PIDFile)", name, pid)
        else:
            if VERBOSE:
                log_warn("%s: forking service started but no PID tracked", name)
            if not self.dry_run:
                self._write_status(name, "active", pid=0, msg="PID unknown")

        for cmd in unit.exec_start_post:
            self._run_cmd(cmd, env, unit, wait=True)

        return True

    def _start_oneshot(self, name, unit, env):
        """Start a oneshot service (run to completion)."""
        log_file = self._log_path(name)
        cmds = unit.exec_start
        if not cmds:
            log_error("No ExecStart defined for %s", name)
            return False

        for cmd in cmds:
            check, _ = parse_exec_cmd(cmd)
            rc, _ = self._run_cmd(cmd, env, unit, wait=True, log_file=log_file)
            if rc and check:
                log_error("ExecStart failed for %s (exit %d)", name, rc)
                env["EXIT_CODE"] = str(rc)
                env["EXIT_STATUS"] = str(rc)
                self._write_status(
                    name, "failed", msg="ExecStart failed (exit %d)" % rc
                )
                return False

        if unit.remain_after_exit:
            if not self.dry_run:
                self._write_status(
                    name, "active", pid=0, msg="Completed (RemainAfterExit)"
                )
        else:
            if not self.dry_run:
                self._write_status(
                    name, "inactive", pid=0, msg="Completed successfully"
                )

        log_info("%s completed", name)

        for cmd in unit.exec_start_post:
            self._run_cmd(cmd, env, unit, wait=True)

        return True

    def stop(self, name):
        """Stop a service."""
        name = self.resolve_name(name)
        log_action("STOP request for %s", name)

        if is_critical_service(name):
            log_error("Refusing to manage critical service: %s", name)
            return False

        unit = self.get_unit(name)
        if not unit:
            log_error("Service not found: %s", name)
            return False

        pid = self._read_pid(name)
        if not pid or not pid_exists(pid):
            if VERBOSE:
                log_info("%s is not running", name)
            self._remove_pid(name)
            self._write_status(name, "inactive")
            return True

        if pid in (1, 2):
            log_error("Refusing to kill PID %d", pid)
            return False

        if VERBOSE:
            log_info("Stopping %s (PID %d)...", name, pid)

        if self.dry_run:
            log_info("[DRY RUN] Would stop PID %d", pid)
            return True

        if pid_exists(pid):
            try:
                os.kill(pid, signal.SIGTERM)
                log_debug("Sent SIGTERM to PID %d", pid)
            except ProcessLookupError:
                pass
            except PermissionError:
                log_error("Permission denied killing PID %d", pid)
                return False

            for _ in range(25):
                if not pid_exists(pid):
                    break
                time.sleep(0.2)

        if pid_exists(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                log_warn("Sent SIGKILL to PID %d", pid)
            except (ProcessLookupError, PermissionError):
                pass
            time.sleep(0.5)

        if pid_exists(pid):
            log_error("Failed to stop %s (PID %d still alive)", name, pid)
            self._write_status(name, "failed", pid=pid, msg="Could not kill")
            return False

        self._remove_pid(name)
        self._write_status(name, "inactive")
        log_info("%s stopped", name)
        return True

    def restart(self, name):
        """Restart a service."""
        name = self.resolve_name(name)
        self.stop(name)
        time.sleep(0.5)
        return self.start(name)

    def enable(self, name):
        """Enable a service to start automatically."""
        name = self.resolve_name(name)
        unit = self.get_unit(name)
        if not unit:
            log_error("Service not found: %s", name)
            return False

        ensure_dirs()
        target = os.path.join(ENABLED_DIR, name)

        if not os.path.isdir(ENABLED_DIR):
            try:
                os.makedirs(ENABLED_DIR, mode=0o755, exist_ok=True)
            except OSError as e:
                log_error(
                    "Failed to create %s: %s (try running with sudo)", ENABLED_DIR, e
                )
                return False

        if os.path.exists(target):
            log_info("%s is already enabled", name)
            return True

        try:
            if unit.path:
                os.symlink(unit.path, target)
            else:
                with open(target, "w") as f:
                    f.write("# enabled")
            log_info("Enabled %s", name)
            return True
        except PermissionError:
            log_error("Permission denied: cannot enable %s (need root?)", name)
            return False
        except OSError as e:
            log_error("Failed to enable %s: %s", name, e)
            return False

    def disable(self, name):
        """Disable a service."""
        name = self.resolve_name(name)
        target = os.path.join(ENABLED_DIR, name)

        if not os.path.isdir(ENABLED_DIR):
            log_info("%s is not enabled", name)
            return True

        if not os.path.exists(target) and not os.path.islink(target):
            log_info("%s is not enabled", name)
            return True

        try:
            os.unlink(target)
            log_info("Disabled %s", name)
            return True
        except PermissionError:
            log_error("Permission denied: cannot disable %s (need root?)", name)
            return False
        except OSError as e:
            log_error("Failed to disable %s: %s", name, e)
            return False

    def is_enabled(self, name):
        """Check if a service is enabled."""
        return os.path.exists(os.path.join(ENABLED_DIR, name))

    def start_all_enabled(self):
        """Start all enabled services with a boot-style log."""
        global QUIET

        if not os.path.isdir(ENABLED_DIR):
            print("No enabled services found.")
            return

        enabled = sorted(os.listdir(ENABLED_DIR))
        if not enabled:
            print("No enabled services.")
            return

        print("Starting enabled services...")

        QUIET = True
        try:
            for name in enabled:
                if not name.endswith(".service"):
                    continue

                unit = self.get_unit(name)
                desc = unit.description if unit else name

                success = self.start(name)

                if success:
                    print("[\033[32m  OK  \033[0m] Started %s." % desc)
                else:
                    print("[\033[31mFAILED\033[0m] Failed to start %s." % desc)
        finally:
            QUIET = False

    def status(self, name):
        """Get and print status of a service."""
        name = self.resolve_name(name)
        unit = self.get_unit(name)
        if not unit:
            print("%s - not found" % name)
            return 4  # NOT_FOUND

        desc = unit.description
        print("● %s - %s" % (name, desc))
        print("   Loaded: loaded (%s)" % (unit.path or "unknown"))

        pid = self._read_pid(name)
        status_data = self._read_status(name)

        if pid and pid_exists(pid):
            state = "active (running)"
            print("   Active: \033[32m%s\033[0m" % state)
            print("      PID: %d" % pid)
            try:
                stat = os.stat("/proc/%d" % pid)
                started = datetime.datetime.fromtimestamp(stat.st_mtime)
                uptime = datetime.datetime.now() - started
                print(
                    "    Since: %s (%s ago)"
                    % (started.strftime("%Y-%m-%d %H:%M:%S"), str(uptime).split(".")[0])
                )
            except (OSError, IOError):
                pass
            return 0
        elif status_data:
            state = status_data.get("state", "inactive")
            msg = status_data.get("message", "")
            ts = status_data.get("timestamp", "")
            if state == "active":
                print("   Active: \033[32m%s\033[0m" % state)
            elif state == "failed":
                print("   Active: \033[31m%s\033[0m" % state)
            else:
                print("   Active: %s" % state)
            if msg:
                print("   Status: %s" % msg)
            if ts:
                print("    Since: %s" % ts)
            return 0 if state == "active" else 3
        else:
            print("   Active: inactive (dead)")
            return 3

    def show_log(self, name, lines=50):
        """Show the last N lines of a service's log."""
        name = self.resolve_name(name)
        log_file = self._log_path(name)
        if not os.path.isfile(log_file):
            log_info("No logs found for %s", name)
            return
        try:
            with open(log_file) as f:
                all_lines = f.readlines()
            for line in all_lines[-lines:]:
                print(line, end="")
            if not all_lines:
                print("(empty log)")
        except (IOError, OSError) as e:
            log_error("Failed to read log for %s: %s", name, e)

    def list_services(self, running_only=False):
        """List all discovered services with their status."""
        self.discover_services()
        rows = []
        for name in sorted(self._units.keys()):
            unit = self._units[name]
            stype = unit.service_type
            pid = self._read_pid(name)
            is_running = pid > 0 and pid_exists(pid)

            if running_only and not is_running:
                continue

            critical = is_critical_service(name)
            unsupported = stype in UNSUPPORTED_TYPES

            if is_running:
                state = "\033[32mrunning\033[0m"
            else:
                status_data = self._read_status(name)
                if status_data and status_data.get("state") == "failed":
                    state = "\033[31mfailed\033[0m"
                else:
                    state = "stopped"

            flags = ""
            if critical:
                flags = " [CRITICAL]"
            elif unsupported:
                flags = " [UNSUPPORTED:%s]" % stype

            rows.append(
                (
                    name,
                    stype,
                    state,
                    str(pid) if is_running else "-",
                    unit.description[:50],
                    flags,
                )
            )

        if not rows:
            print("No services found." if not running_only else "No running services.")
            return

        print(
            "%-40s %-10s %-12s %-8s %s"
            % ("SERVICE", "TYPE", "STATE", "PID", "DESCRIPTION")
        )
        print("-" * 110)
        for name, stype, state, pid_str, desc, flags in rows:
            enabled_mark = "*" if self.is_enabled(name) else " "
            print(
                "%s %-40s %-10s %-12s %-8s %s%s"
                % (enabled_mark, name, stype, state, pid_str, desc, flags)
            )
        print()
        print("Total: %d services (* = enabled)" % len(rows))


def main():
    global VERBOSE

    parser = argparse.ArgumentParser(
        prog="serviced",
        description="Lightweight service manager for systemd .service files (no systemd required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                 List all services
  %(prog)s list-running         List running services
  %(prog)s start sshd           Start sshd service
  %(prog)s stop sshd            Stop sshd service
  %(prog)s restart sshd         Restart sshd service
  %(prog)s status sshd          Show sshd status
  %(prog)s log sshd             Show sshd logs
  %(prog)s --dry-run start ssh  Preview start without executing
  %(prog)s version              Show version info
  %(prog)s enable sshd          Enable sshd to start on boot
  %(prog)s disable sshd         Disable sshd from starting on boot
  %(prog)s start                Start all enabled services (like boot)
        """,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview actions without executing them"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose/debug output"
    )

    # Subparsers for commands
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_start = subparsers.add_parser(
        "start", help="Start a service or all enabled services"
    )
    p_start.add_argument(
        "service", nargs="?", help="Service name (optional for autostart)"
    )

    p_stop = subparsers.add_parser("stop", help="Stop a service")
    p_stop.add_argument("service", help="Service name")

    p_restart = subparsers.add_parser("restart", help="Restart a service")
    p_restart.add_argument("service", help="Service name")

    p_enable = subparsers.add_parser(
        "enable", help="Enable a service to start automatically"
    )
    p_enable.add_argument("service", help="Service name")

    p_disable = subparsers.add_parser("disable", help="Disable a service")
    p_disable.add_argument("service", help="Service name")

    p_status = subparsers.add_parser("status", help="Show service status")
    p_status.add_argument("service", help="Service name")

    p_log = subparsers.add_parser("log", help="Show service log")
    p_log.add_argument("service", help="Service name")
    p_log.add_argument(
        "-n",
        "--lines",
        type=int,
        default=50,
        help="Number of log lines to show (default: 50)",
    )

    p_list = subparsers.add_parser("list", help="List all services")

    p_list_running = subparsers.add_parser("list-running", help="List running services")

    p_version = subparsers.add_parser("version", help="Show version")

    args = parser.parse_args()
    VERBOSE = args.verbose

    # Dispatch
    mgr = ServiceManager(dry_run=args.dry_run)

    ensure_dirs()

    if args.command == "start":
        if args.service:
            success = mgr.start(args.service)
            if not VERBOSE and not QUIET:
                if success:
                    print("[\033[32m  OK  \033[0m] Started %s." % args.service)
                else:
                    print("[\033[31mFAILED\033[0m] Failed to start %s." % args.service)
            if not success:
                sys.exit(1)
        else:
            mgr.start_all_enabled()
    elif args.command == "stop":
        success = mgr.stop(args.service)
        if not VERBOSE and not QUIET:
            if success:
                print("[\033[32m  OK  \033[0m] Stopped %s." % args.service)
            else:
                print("[\033[31mFAILED\033[0m] Failed to stop %s." % args.service)
        if not success:
            sys.exit(1)
    elif args.command == "restart":
        mgr.stop(args.service)
        success = mgr.start(args.service)
        if not VERBOSE and not QUIET:
            if success:
                print("[\033[32m  OK  \033[0m] Restarted %s." % args.service)
            else:
                print("[\033[31mFAILED\033[0m] Failed to restart %s." % args.service)
        if not success:
            sys.exit(1)
    elif args.command == "enable":
        if not mgr.enable(args.service):
            sys.exit(1)
    elif args.command == "disable":
        if not mgr.disable(args.service):
            sys.exit(1)
    elif args.command == "status":
        sys.exit(mgr.status(args.service))
    elif args.command == "log":
        mgr.show_log(args.service, lines=args.lines)
    elif args.command == "list":
        mgr.list_services(running_only=False)
    elif args.command == "list-running":
        mgr.list_services(running_only=True)
    elif args.command == "version":
        print("serviced v%s - lightweight service manager" % VERSION)


if __name__ == "__main__":
    main()
