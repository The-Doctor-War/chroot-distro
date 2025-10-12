# Changelog

### v1.4.2

- fix: correct kali's download urls
- improve: improve the way it use to pass arguments in chroot

### v1.4.1

- remove unnecessary checks
- fix exec_command doesn't work sometime
- improve how it was download the rootfs
    - now it will always download the latest vesion

### v1.4

- docs: update readme
- add: kali linux
- fix: bash: cannot set terminal process group
    - use the `su -P` to fix the below error
      bash: cannot set terminal process group (4979): Inappropriate ioctl for device
      bash: no job control in this shell
      get it from here :- https://serverfault.com/a/1144764
- remove: unnecessary mounts
- remove: unnecessary group register
- add: /dev/pts mount instead of creating a new isolated devpts
- add: more checks
- merge: --force and normal unmount into one
- properly add /etc/group
- restore termux TMPDIR ownership after using it
- improve: change help menus designs
- improve: gid register process
- improve: /dev/shm mount logic
- fix: /dev/shm permission issue

### v1.3

- improve: mount /proc/self/fd folders only if they exist
- fix: remove the if block around suid mount
- improve: always create a new tmpfs then mount to /tmp
- fix: --termux-home permission denied issue
- update: debian to debian 13 (trixie)
- fix: if you use --termux-home make sure it resore the ownership of Termux Home to termux again
- improve: rely more on busybox, add an option to check that all required commands are available

### v1.1.2

- fix: fix wrong permission for /tmp

### v1.1.1

- fs: increase dev/shm size to 512M
    - 256Mb is too low so some app might now run properly that's why i increase it to 512Mb
- fix(archlinux): fix archlinux repo update error
- chor: update fedora to latest version
- docs: update readme
- refactor: use busybox for more task - chnage `curl` to `busybox wget` because some system just doesn't have
  curl on it - chnage `grep` to `busybox grep

### v1.1

- fix: add missing clear cache option, proper handle command_install
- feat: add function to set right permission before mount, fix some mount paths
- docs: update readme
- style: add some comments and rearrange few stuff
- fix: chnage fuser busybox fuser because there is no fuser in toybox
- feat: add a uninstall script to safely unmount the install distro and remove them

### v1.0.1

- fix: error bash: no job control in this shell when using --user flag
- feat: improve the mount and unmount points
- feat: better handle --shared-tmp
- docs: update readme

### v1.0

- fix: --work-dir not working, drop: --env option
- feat: add /data to mount point, so that it can access /data/data/com.termux/
- docs: improve the readme
- fix: the `--` parameter
    - Ex:- `chroot-distro login ubuntu --shared-tmp -- env DISPLAY=:0 apt update`
      `chroot-distro login ubuntu --shared-tmp -- /bin/sh -c 'apt update'`
      `chroot-distro login ubuntu --shared-tmp -- eval "env DISPLAY=:0 apt update"`
      will work now
- fix: mount /dev/pts to fix errors for some programs
- fix: set locale to avoid perl warnings about missing locales
- feat: make some android specific configurations so it can interact better with the android host
- fix: suid issue
- fix: safe_mount directory crate issue
- feat: update command_unmount_system_points to unmount all mount points

### v1.0-beta2

- add: a new option `unmount` to unmount the installed distro
    - Ex:- `chroot-distro unmount ubuntu`
- add: the missing install help menu
- add: the missing main help menu
- fix: busybox checks
- fix: cannot set terminal process group (-1) error when using --user flag

### v1.0-beta

- first test
