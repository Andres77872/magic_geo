#!/usr/bin/env bash
set -euo pipefail

source_url='https://www.ngdc.noaa.gov/thredds/dodsC/global/ETOPO2022/60s/60s_surface_elev_netcdf/ETOPO_2022_v1_60s_N90W180_surface.nc.ascii?z[30:60:10770][30:60:21570]'
source_sha256="b7d411642f8cf91de8c4c4d2fe630d5250a7d650cfc4b267e85b3af48306180b"

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${repository_root}/calibration_data/etopo_2022_1deg"
source_path="${destination}/ETOPO_2022_v1_1deg_surface.dap.txt"

mkdir -p "${destination}"
curl -L -fS --globoff -o "${source_path}" "${source_url}"
printf '%s  %s\n' "${source_sha256}" "${source_path}" | sha256sum --check --status

printf 'ETOPO 2022 v1 one-degree OPeNDAP response installed at %s\n' "${source_path}"
