#!/usr/bin/env bash
#
# Raspberry Ninja NVIDIA Jetson autostart helper.
# Guides the user through creating a systemd service that launches publish.py
# with a chosen command line and optionally disables the desktop GUI.

set -euo pipefail

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
    echo "Please run this script with sudo (eg. sudo $0)."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(realpath "${SCRIPT_DIR}/../..")"

if [[ ! -f "${REPO_ROOT}/publish.py" ]]; then
    echo "Could not locate publish.py in ${REPO_ROOT}. Aborting."
    exit 1
fi

blanking_status="Not configured"

default_user="${SUDO_USER:-}"
if [[ -z "${default_user}" || "${default_user}" == "root" ]]; then
    default_user="vdo"
fi

read -rp "System user that should run publish.py [${default_user}]: " service_user
service_user="${service_user:-$default_user}"

if ! id "${service_user}" >/dev/null 2>&1; then
    echo "User '${service_user}' does not exist. Aborting."
    exit 1
fi

user_home="$(eval echo "~${service_user}")"

default_cmd="python3 ${REPO_ROOT}/publish.py --view steve123 --stretch-display"
read -rp "Command to run on startup [${default_cmd}]: " start_command
start_command="${start_command:-$default_cmd}"

if [[ -z "${start_command}" ]]; then
    echo "A command is required. Aborting."
    exit 1
fi

read -rp "Keep the desktop GUI running? [y/N]: " keep_gui
keep_gui="$(echo "${keep_gui:-N}" | tr '[:upper:]' '[:lower:]')"

use_x_env="n"
if [[ "${keep_gui}" == "y" ]]; then
    read -rp "Add DISPLAY/XAUTHORITY variables to the service? [y/N]: " use_x_env
    use_x_env="$(echo "${use_x_env:-N}" | tr '[:upper:]' '[:lower:]')"
fi

detect_dm() {
    local candidate
    for candidate in gdm gdm3 lightdm; do
        if systemctl list-unit-files --type=service --no-legend | awk '{print $1}' | grep -qx "${candidate}.service"; then
            echo "${candidate}"
            return
        fi
    done
    echo ""
}

configure_display_blanking() {
    local x11_dir="/etc/X11/xorg.conf.d"
    local x11_conf="${x11_dir}/20-raspberry-ninja-nodpms.conf"
    local systemd_service="/etc/systemd/system/disable-console-blanking.service"
    local extlinux_conf="/boot/extlinux/extlinux.conf"

    echo
    echo "Configuring Jetson screen blanking settings..."
    echo "  - X11 config     : ${x11_conf}"
    echo "  - Console service: ${systemd_service}"

    mkdir -p "${x11_dir}"

    cat <<'X11CONF' > "${x11_conf}"
Section "Extensions"
    Option "DPMS" "Disable"
EndSection

Section "ServerFlags"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
X11CONF

    chmod 644 "${x11_conf}"

    cat <<'SERVICECONF' > "${systemd_service}"
[Unit]
Description=Disable Linux console screen blanking for Raspberry Ninja
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/bin/sh -c 'printf 0 | tee /sys/module/kernel/parameters/consoleblank >/dev/null; for tty in /dev/tty[0-9]*; do TERM=linux setterm --term linux --blank 0 --powerdown 0 --powersave off < "$tty"; done'

[Install]
WantedBy=multi-user.target
SERVICECONF

    chmod 644 "${systemd_service}"

    if [[ -f "${extlinux_conf}" ]] && ! grep -q 'consoleblank=0' "${extlinux_conf}"; then
        sed -i '/^[[:space:]]*APPEND / s/$/ consoleblank=0/' "${extlinux_conf}"
    fi

    systemctl daemon-reload
    systemctl enable disable-console-blanking.service

    local console_service_status="started"
    if systemctl start disable-console-blanking.service; then
        console_service_status="started"
    else
        console_service_status="failed"
    fi

    local display_manager_unit="display-manager.service"
    local display_manager_status="not-found"
    if systemctl list-unit-files --type=service "${display_manager_unit}" >/dev/null 2>&1; then
        display_manager_status="inactive"
        if systemctl is-active --quiet "${display_manager_unit}"; then
            if systemctl restart "${display_manager_unit}"; then
                display_manager_status="restarted"
            else
                display_manager_status="restart-failed"
            fi
        fi
    fi

    echo "Screen blanking timers have been disabled:"
    echo "  - Console blanking service status : ${console_service_status}"

    if [[ "${console_service_status}" == "failed" ]]; then
        echo "The disable-console-blanking service failed to start; run 'systemctl status disable-console-blanking.service' for details." >&2
        blanking_status="Failed (disable-console-blanking service)"
        exit 1
    fi

    case "${display_manager_status}" in
        restarted)
            echo "  - Display manager restarted to load X11 DPMS settings."
            ;;
        inactive)
            echo "  - Display manager not running; restart later to load X11 settings."
            ;;
        restart-failed)
            echo "  - Display manager restart failed; check 'journalctl -u ${display_manager_unit}'."
            ;;
        not-found)
            echo "  - Display manager service not found; reboot if you use a GUI."
            ;;
    esac

    echo
    echo "Rebooting still applies everything cleanly, but the changes should already be in effect."
    echo

    blanking_status="Disabled (console service ${console_service_status}; display manager ${display_manager_status})"
}

env_lines=""
if [[ "${use_x_env}" == "y" ]]; then
    read -rp "DISPLAY value [:0]: " display_value
    display_value="${display_value:-:0}"
    read -rp "Path to XAUTHORITY file [${user_home}/.Xauthority]: " xauth_path
    xauth_path="${xauth_path:-${user_home}/.Xauthority}"
    env_lines+="Environment=DISPLAY=${display_value}"$'\n'
    env_lines+="Environment=XAUTHORITY=${xauth_path}"$'\n'
    env_lines+="Environment=XDG_RUNTIME_DIR=/run/user/$(id -u "${service_user}")"$'\n'
fi

read -rp "Disable screen blanking and power saving timers? [Y/n]: " disable_blanking
disable_blanking="$(echo "${disable_blanking:-Y}" | tr '[:upper:]' '[:lower:]')"
if [[ "${disable_blanking}" == "n" ]]; then
    disable_blanking_choice="n"
    blanking_status="Skipped (user opted out)"
else
    disable_blanking_choice="y"
    blanking_status="Pending"
fi

service_name="raspberry-ninja"
service_path="/etc/systemd/system/${service_name}.service"

if [[ -f "${service_path}" ]]; then
    read -rp "${service_path} exists. Overwrite? [y/N]: " overwrite
    overwrite="$(echo "${overwrite:-N}" | tr '[:upper:]' '[:lower:]')"
    if [[ "${overwrite}" != "y" ]]; then
        echo "Aborting without changes."
        exit 1
    fi
fi

escaped_cmd=$(printf "%s" "${start_command}" | sed "s/'/'\"'\"'/g")

{
    echo "[Unit]"
    echo "Description=Raspberry Ninja Autostart (Jetson)"
    echo "After=network-online.target"
    echo "Wants=network-online.target"
    echo
    echo "[Service]"
    echo "Type=simple"
    echo "User=${service_user}"
    echo "Restart=always"
    echo "RestartSec=5"
    if [[ -n "${env_lines}" ]]; then
        printf "%s" "${env_lines}"
    fi
    echo "ExecStart=/bin/bash -lc '${escaped_cmd}'"
    echo
    echo "[Install]"
    echo "WantedBy=multi-user.target"
} > "${service_path}"

chmod 644 "${service_path}"
systemctl daemon-reload
systemctl enable "${service_name}.service"

dm_service="$(detect_dm)"
gui_status="kept"

if [[ "${keep_gui}" != "y" ]]; then
    echo "Configuring system to boot without the desktop GUI..."
    systemctl set-default multi-user.target
    if [[ -n "${dm_service}" ]]; then
        systemctl disable "${dm_service}.service" >/dev/null 2>&1 || true
        systemctl stop "${dm_service}.service" >/dev/null 2>&1 || true
        gui_status="disabled (${dm_service})"
    else
        gui_status="disabled (no display manager detected)"
    fi
else
    systemctl set-default graphical.target
    if [[ -n "${dm_service}" ]]; then
       systemctl enable "${dm_service}.service" >/dev/null 2>&1 || true
    fi
fi

if [[ "${disable_blanking_choice}" == "y" ]]; then
    configure_display_blanking
    if [[ "${blanking_status}" == "Pending" ]]; then
        blanking_status="Disabled"
    fi
fi

cat <<SUMMARY

Configuration complete!
- Systemd service : ${service_path}
- Runs as user    : ${service_user}
- Launch command  : ${start_command}
- Desktop status  : ${gui_status}
- Screen blanking : ${blanking_status}

Next steps:
1. Reboot the Jetson so the boot target and service take effect (sudo reboot).
2. Start now (optional): sudo systemctl start ${service_name}.service
3. Check status: sudo systemctl status ${service_name}.service

Need the GUI again later?
  sudo systemctl set-default graphical.target
  sudo systemctl enable ${dm_service:-gdm}.service
  sudo reboot

Start the desktop temporarily without rebooting:
  sudo systemctl start ${dm_service:-gdm}.service

SUMMARY
