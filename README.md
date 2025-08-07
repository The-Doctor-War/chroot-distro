# chroot-distro (WIP)

**chroot-distro** installs GNU/Linux distributions in a chroot environment on Android.  
- Based on [proot-distro](https://github.com/termux/proot-distro)

---

## ⚠️ Warning

- **Root access is required**.
- This tool may delete files or modify the system. Use with caution.
- **Back up** important files and system partitions before use.
- Recommended: BusyBox **v1.36.1** for Android NDK  
  ❌ Avoid: BusyBox **v1.32.1** (known bugs)

---

## ✅ Requirements

### • Rooted Android Device

All root implementations are compatible.

Use **chroot-distro** from any terminal app (e.g., Termux).

### • BusyBox for Android NDK

Install the [latest BusyBox for Android NDK](https://github.com/osm0sis/android-busybox-ndk) by [osm0sis](https://github.com/osm0sis) as a Magisk module.

- ✅ **Recommended:** v1.36.1  
- ❌ **Avoid:** v1.32.1  
- ℹ️ Outdated versions may cause issues

---

## 📦 Supported Distributions

- **Debian**
- **Ubuntu**
- **Fedora**
- **Arch Linux**

---

## 🚀 Usage

Basic syntax:
```bash
chroot-distro <command> <arguments>
````

Example — install Debian:

```bash
chroot-distro install debian
```

---

## 🧩 Command Aliases

| Full Command  | Aliases                     |
| ------------- | --------------------------- |
| `help`        | `--help`, `-h`, `he`, `hel` |
| `version`     | `--version`, `-v`           |
| `list`        | `li`, `ls`                  |
| `install`     | `i`, `in`, `ins`, `add`     |
| `login`       | `sh`                        |
| `remove`      | `rm`                        |
| `unmount`     | `umount`, `um`              |
| `clear-cache` | `clear`, `cl`               |

---

## 🛠️ Commands

### `help`

Display general or command-specific help:

```bash
chroot-distro help
chroot-distro <command> --help
```

---

### `list` (or `ls`, `li`)

List available distributions, their aliases, installation status, and comments:

```bash
chroot-distro list
```

---

### `install <distro>` (or `i`, `in`, `ins`, `add`)

Install a supported distribution:

```bash
chroot-distro install debian
```

---

### `login <distro>` (or `sh`)

Enter a shell inside the installed distribution:

```bash
chroot-distro login debian
```

#### Options:

* `--user <username>` – Login as a specified user (must already exist inside chroot)
* `--termux-home` – Mount Termux home directory
* `--bind <host_path>:<chroot_path>` – Bind path from host to chroot
* `--work-dir <path>` – Set custom working directory (default: user's home)

#### Run a command inside the chroot:

```bash
chroot-distro login debian -- /usr/local/bin/python3 script.py
```

Use `--` to separate chroot-distro options from the target command.

---

### `unmount <distro>` (or `umount`, `um`)

Unmount all mount points related to a distribution.

#### Options:

* `--force`, `-f` – Force unmount by killing processes
* `--help` – Show help for this command

#### Examples:

```bash
chroot-distro unmount debian
chroot-distro unmount --force debian
```

---

### `remove <distro>` (or `rm`)

Remove the installed distribution.
⚠️ This is **irreversible** and will not ask for confirmation.

```bash
chroot-distro remove fedora
```

---

### `clear-cache` (or `clear`, `cl`)

Remove all downloaded rootfs archives:

```bash
chroot-distro clear-cache
```

---

## 🙏 Acknowledgments

Special thanks to:

* [proot-distro](https://github.com/termux/proot-distro)
* [Magisk-Modules-Alt-Repo/chroot-distro](https://github.com/Magisk-Modules-Alt-Repo/chroot-distro)
