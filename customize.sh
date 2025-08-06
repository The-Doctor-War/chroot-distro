# MODPATH="${MODPATH:-${0%/*}}"
##########################################################################################
# Config Flags
##########################################################################################

# =1 mean take full control over installation
SKIPUNZIP=0

# Set to true if you do *NOT* want Magisk to mount
# any files for you. Most modules would NOT want
# to set this flag to true
SKIPMOUNT=false

# Set to true if you need to load system.prop
PROPFILE=false

# Set to true if you need post-fs-data script
POSTFSDATA=false

# Set to true if you need late_start service script
LATESTARTSERVICE=false

print_modname() {
    ui_print "*******************************"
    ui_print "               chroot-distro                "
    ui_print "*******************************"
}

check_busybox() {
    if ! command -v busybox >/dev/null 2>&1; then
        ui_print "- BusyBox is not installed. Please install BusyBox v1.36.1 or newer."
        exit 1
    fi

    current_version=$(busybox | sed -n 's/.* v\([0-9.]*\).*/\1/p')
    numeric_version=$(echo "$current_version" | tr -d '.')

    if [ "$numeric_version" -lt 1361 ]; then
        ui_print "- The installed BusyBox version ($current_version) is outdated and may cause compatibility issues."
        ui_print "- Upgrade to BusyBox v1.36.1 or newer for optimal performance."
        exit 1
    fi
}

set_permissions() {
    set_perm_recursive $MODPATH 0 0 0755 0644
}
