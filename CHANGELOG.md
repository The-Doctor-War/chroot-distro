# Changelog

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
