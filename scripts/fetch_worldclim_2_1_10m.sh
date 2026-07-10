#!/usr/bin/env bash
set -euo pipefail

tavg_url="https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_tavg.zip"
prec_url="https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_prec.zip"
tavg_sha256="5e567dcfe94379b94229492849ce91078b1c6e5210aaf435fba449fae6b95405"
prec_sha256="1090f578f6402672a2b6438e252156f6cf867a25002a8ad6ffcbfa19e516ddc6"

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${repository_root}/calibration_data/worldclim_2_1_10m"
tavg_path="${destination}/wc2.1_10m_tavg.zip"
prec_path="${destination}/wc2.1_10m_prec.zip"

printf '%s\n' 'WorldClim data are licensed for academic and other non-commercial use.'
printf '%s\n' 'Redistribution and commercial use require prior permission: https://www.worldclim.org/about.html'
mkdir -p "${destination}"
curl -L -fS -o "${tavg_path}" "${tavg_url}"
curl -L -fS -o "${prec_path}" "${prec_url}"
printf '%s  %s\n' "${tavg_sha256}" "${tavg_path}" | sha256sum --check --status
printf '%s  %s\n' "${prec_sha256}" "${prec_path}" | sha256sum --check --status

printf 'WorldClim 2.1 10-minute archives installed at %s\n' "${destination}"
