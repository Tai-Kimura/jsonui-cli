#!/usr/bin/env bash
# Installs apt packages from a folder of .deb files that actions/cache keeps,
# so a slow apt mirror costs one run per runner image, not every run.
#
#   apt_install_cached.sh <deb folder> <package>...
#
# The folder empty (a cache miss): apt-get update, download the packages and
# whatever of their dependencies this image lacks into it, then install them
# from it. The folder full (a hit): install from it with no apt-get update and
# no download. The cache key carries the runner image's version, so the folder
# holds exactly what that image lacks.
#
# Either way the packages asked for must end up installed; if installing from
# the folder fails (a wrong or partial folder), the
# packages are installed online, as before the cache. The folder is removed
# then, so actions/cache has nothing to save from that run (it saves only on a
# miss, and a hit never writes back).
set -euo pipefail

dir=$1
shift
[ "$#" -gt 0 ] || { echo "apt_install_cached.sh: no packages" >&2; exit 2; }
mkdir -p "$dir/partial"

installed() {
  local p
  for p in "$@"; do
    [ "$(dpkg-query -W -f='${Status}' "$p" 2>/dev/null)" = "install ok installed" ] || return 1
  done
}

from_folder() {
  # Nothing to install: every package (and its dependencies) is already on the image.
  compgen -G "$dir/*.deb" >/dev/null || return 0
  sudo DEBIAN_FRONTEND=noninteractive dpkg -i "$dir"/*.deb >/dev/null
}

if compgen -G "$dir/*.deb" >/dev/null; then
  echo "apt cache: hit, $(ls "$dir"/*.deb | wc -l) .deb files"
else
  echo "apt cache: miss, downloading"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    --download-only -o Dir::Cache::archives="$dir" "$@"
  echo "apt cache: $(ls "$dir"/*.deb 2>/dev/null | wc -l) .deb files downloaded"
fi

if from_folder && installed "$@"; then
  echo "apt cache: installed $# packages from the folder"
else
  echo "::warning::apt cache: installing from the folder failed; installing online and saving nothing"
  sudo rm -rf "$dir"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends "$@"
  installed "$@"
  exit 0
fi
# actions/cache reads the folder as the runner user; apt wrote it as root.
sudo chown -R "$(id -u):$(id -g)" "$dir"
rm -rf "$dir/partial" "$dir/lock"
