#!/usr/bin/env bash
set -euo pipefail

archive_url="https://naciscdn.org/naturalearth/110m/physical/ne_110m_land.zip"
archive_sha256="1926c621afd6ac67c3f36639bb1236134a48d82226dc675d3e3df53d02d2a3de"
shapefile_sha256="8689e6932b8e370e2ca4587cf3ba21e460b1235db37b6ed3c172c35b4a6088de"
source_version="4.1.0"

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${repository_root}/calibration_data/natural_earth_110m"
temporary_directory="$(mktemp -d)"
trap 'rm -rf "${temporary_directory}"' EXIT

archive_path="${temporary_directory}/ne_110m_land.zip"
curl -L -fS -o "${archive_path}" "${archive_url}"
printf '%s  %s\n' "${archive_sha256}" "${archive_path}" | sha256sum --check --status

mkdir -p "${destination}"
unzip -o "${archive_path}" -d "${destination}"
printf '%s  %s\n' "${shapefile_sha256}" "${destination}/ne_110m_land.shp" | sha256sum --check --status
installed_version="$(tr -d '\r\n' < "${destination}/ne_110m_land.VERSION.txt")"
if [[ "${installed_version}" != "${source_version}" ]]; then
    printf 'Unexpected Natural Earth version: expected %s, got %s\n' "${source_version}" "${installed_version}" >&2
    exit 1
fi

printf 'Natural Earth 110m land installed at %s\n' "${destination}"
