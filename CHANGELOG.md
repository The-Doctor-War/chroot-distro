# Changelog

### v1.5.1

- swap(chroot-distro): remove awk-jq and add a simple regex inside chroot-distro
- fix(Readme): fix acknowledgments links
- feat(webui): implement log persistence
- fix(chroot-distro): check for /etc folder to consider a distro is fully installed
- feat(webui): only make the middle section scroll
- feat(ci/checkup-and-release): add a option always bbuild a artifact also now use a build.sh to build the module
- style: cleanup
- docs: update readme

### v1.5.0

- feat(ci/checkup-and-release): generate log only from last numbered tag
- feat(webui): add search button
- feat(chroor-distro): improve chroot-distro list loading speed
- fix(webui): add the missing spin animation
- feat(chroot-distro/init_distros_data): compare hash before copy
- chore: update distros.json with latest versions [skip ci]
- feat(ci/update-distro.yml): run on each canges on update-distro.yml
- fix(chroot-distro): pass shellcheck, resolve SC3043 warning
- adddistro: alpine, manjaro, opensuse, rockylinux, trisquel
- feat(webui): add option to show version info in the webui
- feat(chroot-distro): check before and after copy that the file isn't a empty file
- feat: create minimal jq using awk and use that to capture json data
- chore: update distros.json with latest versions [skip ci]
- fix(ci): fix json process issue
- chore: update distros.json with latest versions [skip ci]
- feat: improve how it used to manage distro
- drop: remove ubuntu-lts

### v1.4.9

- feat(chroot-distro): add download_file to first try curl and if doesn't exist then try busybox wget
- feat(webui): implement a settings page and improve the ui
- feat(webui): remove the terminalSpinner
- feat(webui): play a animation when removing a distro
- feat(webui): add a download animation onn the install button
- feat(webui): add refresh button
- fix: remove the check using mount command in list_running as it will not work under webui
- feat: update workflow to build webui
- feat: add initial webui support
- feat: add new list-running option
- feat: add a option to print the data in a json format

### v1.4.8

- feat: add option to dynamically show distro related data in module description
- refactor: run normal user network fixes in command_login instead of command_install, move the unmount message to cleanup_all_mounts
- feat: improve safe_mount to specify fs_type and mount_opts

### v1.4.7

- feat: refactor the code replace all the termux related path with variables, and fix for --termux-home and --work-dir it wasn't restoring the permission of TERMUX_HOME after exit
- feat: better error handling when using --termux-home or --work-dir
- fix: create /run/resolvconf folder if doesn't exist
- style: don't hardcode REPO_NAME and PROGRAM_NAME and REPO_WONER
- fix: command_unmount always saying `Still some mount points found`
- fix: fix when using --work-dir without --termux-home we can't access anything from /data/data/com.termux/files/
- fix: sub directory access issue in --termux-home for non root users
- fix: normal user can't use --termux-home
- fix: fix apt internet connection issue
- feat: simplify the dns setup
- feat: add support for multiple session and auto unmount after all sessions are closed
- ci: don't zip .editorconfig in the module
- style: change default indent_style to tab
- fix: make sure all mounted points are get printed in mount tracker file
- refactor: replace all chroot "${INSTALLED_ROOTFS_DIR}/${distro_name}" COMMAND with run_chroot_cmd
- refactor: simplify resolv.conf setup
- fix(command_install): fix resolv.conf link issue

### v1.4.6

- feat: use separate mount.points for each distro
- fix: shellcheck SC2013
- feat: improve unmount logic, improve network setup, anf few more improvements
- feat: add /apex to mount, add some useful exports to /etc/profile, share termux home on --shared-tmp
- fix(ubuntu): messagebus group and user if missing, add missing root in group
- fix: fix _apt permissions and ownership issue

### v1.4.5

- fix: pass shellcheck
- feat: add a ci/cd to shellcheck and release new version
- feat: add option to run specfic configuration after install
- fix: remove auto unmount after login, it was causing issue

### v1.4.4

- better handle color variables
- adddistro: ubuntu-lts

### v1.4.3

- fix: mount /dev in the install part so fix any cannot create /dev/null error
- refactor: use more busybox

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
