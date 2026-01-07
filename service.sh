#!/system/bin/sh

MODDIR=${0%/*}
RUNTIME_DIR="/data/local/chroot-distro"

# Start status monitor in background
nohup sh "$MODDIR/status.sh" &

# Wait for boot completion
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done

# Clean up stale session files on boot (if exist)
# This ensures session counts are accurate after reboots
# if you rebbot then all the distro will be unmounted
# that's why we should do this
if [ -d "${RUNTIME_DIR}/data" ]; then
	for distro_data in "${RUNTIME_DIR}/data"/*; do
		if [ -d "$distro_data" ]; then
			session_file="${distro_data}/sessions"
			if [ -f "$session_file" ]; then
				# Reset session count on boot
				rm -f "$session_file"
			fi
		fi
	done
fi

# # Configure network for chroot environments
# # Enable ping for all users
# if [ -w /proc/sys/net/ipv4/ping_group_range ]; then
# 	echo '0 2147483647' >/proc/sys/net/ipv4/ping_group_range 2>/dev/null
# fi
#
# # Enable USB device authorization if available
# if [ -w /sys/module/usbcore/parameters/authorized_default ]; then
# 	echo 1 >/sys/module/usbcore/parameters/authorized_default 2>/dev/null
# fi
#
exit 0
