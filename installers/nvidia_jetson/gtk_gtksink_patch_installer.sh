#!/usr/bin/env bash
# Targeted Jetson patch installer that rebuilds the Gtk introspection stack
# and the custom GStreamer tree so that gtksink works with the Python viewer.
set -euo pipefail

log() {
    printf '[jetson-gtk-patch] %s\n' "$*"
}

export PATH="$HOME/.local/bin:/usr/local/bin:${PATH}"
export PKG_CONFIG_PATH="/usr/local/lib/pkgconfig:/usr/local/lib/aarch64-linux-gnu/pkgconfig:${PKG_CONFIG_PATH-}"

if [[ "$(id -u)" -eq 0 ]]; then
    SUDO=""
else
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        log "This script requires sudo privileges."
        exit 1
    fi
fi

APT_PACKAGES=(
    build-essential
    ninja-build
    git
    pkg-config
    python3
    python3-pip
    python3-gi
    gir1.2-gtk-3.0
    libgtk-3-dev
    libgirepository1.0-dev
    libglib2.0-dev
    libffi-dev
    libmount-dev
    libselinux1-dev
    libpcre3-dev
    libxml2-dev
    flex
    bison
    libcairo2-dev
    libdrm-dev
    libegl1
    libgles2
    libwayland-dev
    libxkbcommon-dev
    libepoxy-dev
)

SRC_ROOT=${SRC_ROOT:-"$HOME/src/jetson-gtk-patch"}
GLIB_VERSION=${GLIB_VERSION:-"2.76.1"}
GI_VERSION=${GI_VERSION:-"1.76.1"}
GSTREAMER_REF=${GSTREAMER_REF:-"1.23.0"}
GSTREAMER_REPO=${GSTREAMER_REPO:-"https://gitlab.freedesktop.org/gstreamer/gstreamer.git"}
GSTREAMER_DIR=${GSTREAMER_DIR:-"$SRC_ROOT/gstreamer"}
TYPELIB_TARGET=${TYPELIB_TARGET:-"/usr/local/lib/girepository-1.0"}

mkdir -p "${SRC_ROOT}"

ensure_prereqs() {
    if [[ -z "${RN_SKIP_APT:-}" ]]; then
        log "Installing build prerequisites via apt-get…"
        $SUDO apt-get update
        $SUDO apt-get install -y "${APT_PACKAGES[@]}"
    else
        log "Skipping apt-get because RN_SKIP_APT is set."
    fi

    log "Ensuring recent meson and ninja via pip…"
    python3 -m pip install --user --upgrade pip
    python3 -m pip install --user --upgrade meson ninja
}

already_on_version() {
    local pkg=$1
    local want=$2

    if ! command -v pkg-config >/dev/null 2>&1; then
        return 1
    fi

    if ! pkg-config --exists "${pkg}"; then
        return 1
    fi

    local have
    have=$(pkg-config --modversion "${pkg}")
    [[ "${have}" == "${want}" ]]
}

build_glib() {
    if already_on_version "glib-2.0" "${GLIB_VERSION}"; then
        log "glib-2.0 ${GLIB_VERSION} already present; skipping rebuild."
        return
    fi

    local tarball="glib-${GLIB_VERSION}.tar.xz"
    local src_dir="${SRC_ROOT}/glib-${GLIB_VERSION}"

    log "Building glib-${GLIB_VERSION} from source…"
    cd "${SRC_ROOT}"
    rm -rf "${src_dir}"
    wget -q "https://download.gnome.org/sources/glib/${GLIB_VERSION%.*}/${tarball}" -O "${tarball}"
    tar -xf "${tarball}"
    cd "${src_dir}"
    rm -rf build
    meson setup build \
        --prefix=/usr/local \
        --buildtype=release \
        -Dman=false
    ninja -C build
    $SUDO ninja -C build install
    $SUDO ldconfig
}

build_gobject_introspection() {
    if already_on_version "gobject-introspection-1.0" "${GI_VERSION}"; then
        log "gobject-introspection ${GI_VERSION} already present; skipping rebuild."
        return
    fi

    local tarball="gobject-introspection-${GI_VERSION}.tar.xz"
    local src_dir="${SRC_ROOT}/gobject-introspection-${GI_VERSION}"

    log "Building gobject-introspection-${GI_VERSION} from source…"
    cd "${SRC_ROOT}"
    rm -rf "${src_dir}"
    wget -q "https://download.gnome.org/sources/gobject-introspection/${GI_VERSION%.*}/${tarball}" -O "${tarball}"
    tar -xf "${tarball}"
    cd "${src_dir}"
    rm -rf build
    meson setup build \
        --prefix=/usr/local \
        --buildtype=release
    ninja -C build
    $SUDO ninja -C build install
    $SUDO ldconfig
}

sync_typelibs() {
    log "Linking Gtk typelibs into ${TYPELIB_TARGET}…"
    $SUDO mkdir -p "${TYPELIB_TARGET}"

    local sources=(
        "/usr/local/lib/girepository-1.0"
        "/usr/lib/aarch64-linux-gnu/girepository-1.0"
        "/usr/lib/girepository-1.0"
    )

    for src in "${sources[@]}"; do
        if [[ -d "${src}" ]]; then
            while IFS= read -r -d '' typelib; do
                local base
                base=$(basename "${typelib}")
                $SUDO ln -sf "${typelib}" "${TYPELIB_TARGET}/${base}"
            done < <(find "${src}" -maxdepth 1 -name '*.typelib' -print0)
        fi
    done
}

checkout_gstreamer() {
    if [[ ! -d "${GSTREAMER_DIR}/.git" ]]; then
        log "Cloning GStreamer (${GSTREAMER_REF}) into ${GSTREAMER_DIR}…"
        rm -rf "${GSTREAMER_DIR}"
        if ! git clone --depth 1 --branch "${GSTREAMER_REF}" "${GSTREAMER_REPO}" "${GSTREAMER_DIR}"; then
            log "Requested ref ${GSTREAMER_REF} not found; falling back to main."
            git clone --depth 1 "${GSTREAMER_REPO}" "${GSTREAMER_DIR}"
        fi
    else
        log "Updating existing GStreamer checkout…"
        git -C "${GSTREAMER_DIR}" remote set-url origin "${GSTREAMER_REPO}"
        git -C "${GSTREAMER_DIR}" fetch --depth 1 origin "${GSTREAMER_REF}" || git -C "${GSTREAMER_DIR}" fetch --depth 1 origin main
        if ! git -C "${GSTREAMER_DIR}" checkout "${GSTREAMER_REF}"; then
            git -C "${GSTREAMER_DIR}" checkout origin/main
        fi
        git -C "${GSTREAMER_DIR}" reset --hard HEAD
    fi
}

build_gstreamer() {
    checkout_gstreamer

    log "Configuring GStreamer with Gtk sink enabled…"
    cd "${GSTREAMER_DIR}"
    local build_dir="${GSTREAMER_DIR}/build"
    local setup_args=(
        --prefix=/usr/local
        --buildtype=release
        -Ddoc=disabled
        -Dtests=disabled
        -Dexamples=disabled
        -Ddevtools=disabled
        -Dgst-plugins-base:gl_winsys=egl
        -Dgst-plugins-base:gl=enabled
        -Dgst-plugins-bad:gtk=enabled
    )

    if [[ -d "${build_dir}" ]]; then
        meson setup "${build_dir}" "${setup_args[@]}" --reconfigure
    else
        meson setup "${build_dir}" "${setup_args[@]}"
    fi

    log "Building and installing GStreamer…"
    ninja -C "${build_dir}"
    $SUDO ninja -C "${build_dir}" install
    $SUDO ldconfig
}

verify_runtime() {
    log "Verifying Gtk availability from Python…"
    GI_TYPELIB_PATH="${TYPELIB_TARGET}:${GI_TYPELIB_PATH-}" python3 - <<'PY'
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk
print("Gtk bindings OK:", Gtk.MAJOR_VERSION, Gtk.MINOR_VERSION, Gtk.MICRO_VERSION)
print("Gdk display:", bool(Gdk.Display.get_default()))
PY

    log "Checking gtksink plugin…"
    if gst-inspect-1.0 gtksink >/dev/null 2>&1; then
        gst-inspect-1.0 gtksink | awk 'NR<=10 {print}'
    else
        log "gtksink still missing; investigate build logs above."
        return 1
    fi
}

main() {
    ensure_prereqs
    build_glib
    build_gobject_introspection
    sync_typelibs
    build_gstreamer
    verify_runtime
    log "Patch workflow completed."
}

main "$@"
