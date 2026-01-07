#!/system/bin/sh

MODDIR=${0%/*}
RUNTIME_DIR="/data/local/chroot-distro"
INSTALLED_ROOTFS_DIR="${RUNTIME_DIR}/installed-rootfs"

PROP_FILE="$MODDIR/module.prop"
PROP_BAK="$MODDIR/module.prop.bak"

# Ensure busybox is available
BUSYBOXPATH="$(command -v busybox 2>/dev/null)"
if [ -z "$BUSYBOXPATH" ]; then
	exit 1
fi

busybox() { "$BUSYBOXPATH" "$@"; }

set_prop() {
	prop="$1"
	value="$2"
	file="$3"

	# Remove existing prop line and add new one
	if grep -q "^$prop=" "$file"; then
		grep -v "^$prop=" "$file" >"$file.tmp"
		mv "$file.tmp" "$file"
	fi
	printf '%s=%s\n' "$prop" "$value" >>"$file"
}

restore_prop_if_needed() {
	if ! grep -q "^id=" "$PROP_FILE"; then
		if [ -f "$PROP_BAK" ]; then
			cp "$PROP_BAK" "$PROP_FILE"
		fi
	fi
}

get_session_file() {
	distro_name="$1"
	echo "${RUNTIME_DIR}/data/${distro_name}/sessions"
}

get_mount_tracker_file() {
	distro_name="$1"
	echo "${RUNTIME_DIR}/data/${distro_name}/mount.points"
}

# Wait for boot completion
until [ "$(getprop sys.boot_completed)" = "1" ]; do
	sleep 1
done

# Initialize status variables
installed_count=0
mounted_count=0
total_sessions=0
distro_details=""
mounted_distros=""
installed_distros=""

# Check if chroot-distro is installed and working
if [ ! -d "$INSTALLED_ROOTFS_DIR" ]; then
	string="Status: Not initialized ⚠️"
else
	# Count installed distributions and gather info
	if [ -d "$INSTALLED_ROOTFS_DIR" ]; then
		for distro_dir in "$INSTALLED_ROOTFS_DIR"/*; do
			if [ -d "$distro_dir" ] && [ -e "$distro_dir/etc" ]; then
				installed_count=$((installed_count + 1))
				distro_name=$(basename "$distro_dir")
				if [ -z "$installed_distros" ]; then
					installed_distros="$distro_name"
				else
					installed_distros="$installed_distros, $distro_name"
				fi
			fi
		done
	fi

	# Check for mounted distributions and active sessions
	if [ -d "${RUNTIME_DIR}/data" ]; then
		for distro_data in "${RUNTIME_DIR}/data"/*; do
			if [ -d "$distro_data" ]; then
				distro_name=$(basename "$distro_data")
				is_mounted=0
				distro_sessions=0

				# Check if it has active mounts
				mount_tracker=$(get_mount_tracker_file "$distro_name")
				if [ -f "$mount_tracker" ] && [ -s "$mount_tracker" ]; then
					# Verify at least one mount is actually active
					while IFS= read -r mount_point; do
						if busybox mount | busybox grep -q " on $mount_point "; then
							is_mounted=1
							break
						fi
					done <"$mount_tracker"
				fi

				# Count active sessions for this distro
				session_file=$(get_session_file "$distro_name")
				if [ -f "$session_file" ]; then
					sessions=$(cat "$session_file" 2>/dev/null || echo "0")
					if echo "$sessions" | busybox grep -qE '^[0-9]+$'; then
						distro_sessions=$sessions
						total_sessions=$((total_sessions + sessions))
					fi
				fi

				# Build per-distro detail if mounted or has sessions
				if [ $is_mounted -eq 1 ]; then
					mounted_count=$((mounted_count + 1))

					# Add to mounted distros list
					if [ -z "$mounted_distros" ]; then
						mounted_distros="$distro_name"
					else
						mounted_distros="$mounted_distros, $distro_name"
					fi

					# Build session text
					if [ "$distro_sessions" -eq 1 ]; then
						session_text="1 session"
					elif [ "$distro_sessions" -gt 1 ]; then
						session_text="${distro_sessions} sessions"
					else
						session_text="no active sessions"
					fi

					# Add distro detail line with literal \n
					if [ -z "$distro_details" ]; then
						distro_details="📦 ${distro_name}: ${session_text}"
					else
						distro_details="${distro_details} \\n 📦 ${distro_name}: ${session_text}"
					fi
				fi
			fi
		done
	fi

	# Build status string
	if [ $installed_count -eq 0 ]; then
		string="Status: No distros installed 📦"
	elif [ $mounted_count -eq 0 ]; then
		if [ $installed_count -eq 1 ]; then
			string="Status: ${installed_count} distro installed, none active 💤 \\n Installed: ${installed_distros}"
		else
			string="Status: ${installed_count} distros installed, none active 💤 \\n Installed: ${installed_distros}"
		fi
	else
		# Build the main status line
		if [ $mounted_count -eq 1 ]; then
			main_status="Status: ${mounted_count}/${installed_count} is activated 🚀 | Mounted: ${mounted_distros}"
		else
			main_status="Status: ${mounted_count}/${installed_count} are activated 🚀 | Mounted: ${mounted_distros}"
		fi

		# Combine main status with distro details on new lines
		string="${main_status} \\n ${distro_details}"
	fi
fi

# Update module.prop
restore_prop_if_needed
set_prop "description" "$string" "$PROP_FILE"
