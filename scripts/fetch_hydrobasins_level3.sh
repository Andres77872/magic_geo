#!/usr/bin/env bash
set -euo pipefail

regions=(af ar as au eu gr na sa si)
checksums=(
    2a21ec9b349499afa5fe60666ce0395a5658969fd9995f5c0cbf7ed61bb70a5c
    9856e9eed6424a5a7d10a261925ccbdb9fdf9b51ca45cd61a803de87e0b4bfe9
    8685de538821bbfdd3aaa8d215abc93b8ad77ae9d10f909c6bc03a93d80c3e8d
    1b76e59db5e46433e481da4a05b480ab7c11db53870d3c0f23c68474c7a7f0a3
    418df2b925e5774ec64445267de1d3813f807b72b9eb0e90fbbbe809bd98260b
    329cb5bdc911e7890ac6bd5c84336d66337d325fe72ceab218106d0d4fffe830
    9c0a26757743500643fe4c50e4cb6fb23efbe31d212027f2c5a2d38f78e2ded8
    9eedb5240e9c2c77a55586c8b7b736ff34e067798e4a6d0bc1211549af2fe2aa
    af0f99dfce4e5965db3e6e97b9256c2f1f7a341ad0d100fde4803a08c611571b
)

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
destination="${repository_root}/calibration_data/hydrobasins_level3"

printf '%s\n' 'HydroBASINS use is governed by the HydroSHEDS license agreement; attribution and other terms apply.'
printf '%s\n' 'https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf'
mkdir -p "${destination}"
for index in "${!regions[@]}"; do
    region="${regions[index]}"
    archive_path="${destination}/hybas_${region}_lev03_v1c.zip"
    source_url="https://data.hydrosheds.org/file/hydrobasins/standard/hybas_${region}_lev03_v1c.zip"
    curl -L -fS -o "${archive_path}" "${source_url}"
    printf '%s  %s\n' "${checksums[index]}" "${archive_path}" | sha256sum --check --status
done

printf 'HydroBASINS v1.c level-3 archives installed at %s\n' "${destination}"
