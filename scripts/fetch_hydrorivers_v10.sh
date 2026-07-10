#!/usr/bin/env bash
set -euo pipefail

source_url="https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_shp.zip"
source_sha256="0cf9e363e4b48ede535787f9e2eecbcff43eb53acad4b9cbf048c9e12453e5b5"

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${repository_root}/calibration_data/hydrorivers_v10"
archive_path="${destination}/HydroRIVERS_v10_shp.zip"

printf '%s\n' 'HydroRIVERS use is governed by the HydroSHEDS license agreement; attribution and other terms apply.'
printf '%s\n' 'https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf'
mkdir -p "${destination}"
if [[ -f "${archive_path}" ]] \
    && printf '%s  %s\n' "${source_sha256}" "${archive_path}" | sha256sum --check --status; then
    printf 'HydroRIVERS v1.0 archive already verified at %s\n' "${archive_path}"
    exit 0
fi

temporary_path="${archive_path}.part"
trap 'rm -f "${temporary_path}"' EXIT
curl -L -fS -o "${temporary_path}" "${source_url}"
printf '%s  %s\n' "${source_sha256}" "${temporary_path}" | sha256sum --check --status
mv "${temporary_path}" "${archive_path}"
trap - EXIT

printf 'HydroRIVERS v1.0 global shapefile archive installed at %s\n' "${archive_path}"
