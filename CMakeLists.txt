cmake_minimum_required(VERSION 3.20)

project(magic_geo VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

option(
  MAGIC_GEO_ENABLE_CUDA
  "Build the native CUDA backend when a CUDA 12.8+ compiler is available"
  ON
)
set(
  MAGIC_GEO_CUDA_ARCHITECTURES
  "75-real;75-virtual;80-real;86-real;89-real;90-real;120-real;120-virtual"
  CACHE STRING
  "CUDA architectures for magic-geo (modern NVIDIA SASS, baseline forward PTX, native RTX 50 SASS, and Blackwell PTX)"
)

set(MAGIC_GEO_CUDA_SOURCE cpp/src/cuda_compute_stub.cpp)
set(MAGIC_GEO_CUDA_ENABLED OFF)
if(MAGIC_GEO_ENABLE_CUDA)
  # CUDA 13.1 must see this during compiler identification (before any target
  # exists) on glibc 2.43, whose GNU feature set exposes new C23 rsqrt symbols
  # that collide with CUDA's device declarations. Retain the default, POSIX,
  # and X/Open declarations required by libstdc++ while disabling only GNU
  # extensions for CUDA translation units.
  set(
    CMAKE_CUDA_FLAGS_INIT
    "${CMAKE_CUDA_FLAGS_INIT} -U_GNU_SOURCE -D_DEFAULT_SOURCE=1 -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700"
  )
  include(CheckLanguage)
  check_language(CUDA)
  if(CMAKE_CUDA_COMPILER)
    enable_language(CUDA)
    if(
      CMAKE_CUDA_COMPILER_ID STREQUAL "NVIDIA" AND
      CMAKE_CUDA_COMPILER_VERSION VERSION_GREATER_EQUAL 12.8
    )
      find_package(CUDAToolkit 12.8 QUIET)
      if(CUDAToolkit_FOUND)
        set(MAGIC_GEO_CUDA_SOURCE cpp/src/cuda_compute.cu)
        set(MAGIC_GEO_CUDA_ENABLED ON)
        message(
          STATUS
          "magic-geo CUDA backend: ${CMAKE_CUDA_COMPILER_VERSION}; architectures=${MAGIC_GEO_CUDA_ARCHITECTURES}"
        )
      else()
        message(
          WARNING
          "magic-geo CUDA backend disabled: CUDA runtime development files were not found; building runtime stub"
        )
      endif()
    elseif(CMAKE_CUDA_COMPILER_ID STREQUAL "NVIDIA")
      message(
        WARNING
        "magic-geo CUDA backend disabled: CUDA ${CMAKE_CUDA_COMPILER_VERSION} cannot compile sm_120; CUDA 12.8+ is required"
      )
    else()
      message(
        WARNING
        "magic-geo CUDA backend disabled: compiler '${CMAKE_CUDA_COMPILER_ID}' is not supported; NVIDIA nvcc 12.8+ is required"
      )
    endif()
  else()
    message(STATUS "magic-geo CUDA backend: compiler not found; building runtime stub")
  endif()
else()
  message(STATUS "magic-geo CUDA backend: disabled by MAGIC_GEO_ENABLE_CUDA=OFF")
endif()

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type (default Release)" FORCE)
  set_property(CACHE CMAKE_BUILD_TYPE PROPERTY STRINGS Debug Release RelWithDebInfo MinSizeRel)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenMP)
find_package(Threads REQUIRED)

set(
  MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY
  "${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo"
  CACHE PATH
  "Directory for the native shared library"
)
set(
  _MAGIC_GEO_PACKAGE_LIBRARY_OUTPUT_DIRECTORY
  "${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo"
)

add_library(
  magic_geo_native SHARED
  cpp/src/c_api.cpp
  cpp/src/engine.cpp
  cpp/src/engine/climate.cpp
  cpp/src/engine/climate_transport.cpp
  cpp/src/engine/physical_columns.cpp
  cpp/src/engine/seasonal_climate.cpp
  cpp/src/engine/seasonal_climate_cache.cpp
  cpp/src/engine/seasonal_climate_serialization.cpp
  cpp/src/engine/adaptive_energy_balance.cpp
  cpp/src/engine/periodic_energy_balance.cpp
  cpp/src/engine/seasonal_energy_balance.cpp
  cpp/src/engine/enthalpy_mesh.cpp
  cpp/src/engine/enthalpy_mesh_serialization.cpp
  cpp/src/engine/enthalpy_mesh_sdirk2.cpp
  cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp
  cpp/src/engine/enthalpy_mesh_proof_codec.cpp
  cpp/src/engine/layered_proof_store.cpp
  cpp/src/engine/layered_proof_record.cpp
  cpp/src/engine/layered_ice_column.cpp
  cpp/src/engine/layered_ice_material.cpp
  cpp/src/engine/layered_ice_absorption.cpp
  cpp/src/engine/layered_ice_remap.cpp
  cpp/src/engine/layered_ice_topology.cpp
  cpp/src/engine/layered_ice_owner.cpp
  cpp/src/engine/layered_ice_owner_kernel.cpp
  cpp/src/engine/layered_ice_owner_metadata.cpp
  cpp/src/engine/layered_ice_forcing_history.cpp
  cpp/src/engine/layered_ice_owner_ledger.cpp
  cpp/src/engine/layered_ice_owner_serialization.cpp
  cpp/src/engine/enthalpy_mesh_owner.cpp
  cpp/src/engine/enthalpy_mesh_owner_serialization.cpp
  cpp/src/engine/finalized_enthalpy_context.cpp
  cpp/src/engine/finalized_enthalpy_context_serialization.cpp
  cpp/src/engine/finalized_layered_state.cpp
  cpp/src/engine/finalized_layered_foundation.cpp
  cpp/src/engine/time_integrated_energy.cpp
  cpp/src/engine/solar_insolation.cpp
  cpp/src/engine/solar_calendar.cpp
  cpp/src/engine/solar_calendar_serialization.cpp
  cpp/src/engine/civilization.cpp
  cpp/src/engine/core.cpp
  cpp/src/engine/crust_overlap_candidate_fate.cpp
  cpp/src/engine/crust_material.cpp
  cpp/src/engine/crust_reservoir.cpp
  cpp/src/engine/crust_reservoir_serialization.cpp
  cpp/src/engine/crust_transport.cpp
  cpp/src/engine/earth_system.cpp
  cpp/src/engine/entity_serialization.cpp
  cpp/src/engine/environment.cpp
  cpp/src/engine/history.cpp
  cpp/src/engine/hydrology.cpp
  cpp/src/engine/seasonal_liquid_routing.cpp
  cpp/src/engine/terrestrial_water.cpp
  cpp/src/engine/terrestrial_water_serialization.cpp
  cpp/src/engine/terrestrial_calorimeter_backend.cpp
  cpp/src/engine/terrestrial_coupled.cpp
  cpp/src/engine/terrestrial_coupled_error.cpp
  cpp/src/engine/terrestrial_thermal_backend.cpp
  cpp/src/engine/terrestrial_thermal/phase_segment.cpp
  cpp/src/engine/terrestrial_thermal/hermite_residual.cpp
  cpp/src/engine/terrestrial_thermal/phase_segment_serialization.cpp
  cpp/src/engine/mesh.cpp
  cpp/src/engine/messagepack.cpp
  cpp/src/engine/numeric_serialization.cpp
  cpp/src/engine/ocean.cpp
  cpp/src/engine/oceanic_age_depth.cpp
  cpp/src/engine/initial_oceanic_age.cpp
  cpp/src/engine/pipeline.cpp
  cpp/src/engine/plate_boundary_segments.cpp
  cpp/src/engine/process_serialization.cpp
  cpp/src/engine/sediment_partition.cpp
  cpp/src/engine/settlements.cpp
  cpp/src/engine/summary.cpp
  cpp/src/engine/tectonics.cpp
  cpp/src/engine/water_features.cpp
  cpp/src/engine/world_serialization.cpp
  ${MAGIC_GEO_CUDA_SOURCE}
  cpp/src/crust_overlap_shadow.cpp
  cpp/src/opencl_compute.cpp
)

target_include_directories(magic_geo_native PRIVATE cpp/include)
target_compile_features(magic_geo_native PRIVATE cxx_std_20)

# Keep contraction policy stable in optimized CPU code. This prevents FMA from
# introducing avoidable backend drift; cross-compiler/GPU parity is validated
# with numeric tolerances and physical invariants rather than byte hashes.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(
    magic_geo_native
    PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-ffp-contract=off>
  )
endif()
set_target_properties(
  magic_geo_native
  PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    OUTPUT_NAME "magic_geo_native"
    LIBRARY_OUTPUT_DIRECTORY "${MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY}"
    RUNTIME_OUTPUT_DIRECTORY "${MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY}"
    VISIBILITY_INLINES_HIDDEN YES
)

# The default Release artifact is staged beside the Python package for the
# documented editable workflow. Keep every non-package configuration in its
# own build tree so Debug/RelWithDebInfo/MinSizeRel cannot overwrite that file
# or silently make another build tree test the wrong binary. An explicitly
# supplied output directory remains fully caller-controlled.
if(
  "${MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY}"
  STREQUAL "${_MAGIC_GEO_PACKAGE_LIBRARY_OUTPUT_DIRECTORY}"
)
  # Multi-config generators append a configuration directory unless the
  # per-config property is explicit. Keep the production DLL/dylib beside the
  # Python package on Windows/macOS just like the single-config Linux build.
  set_target_properties(
    magic_geo_native
    PROPERTIES
      LIBRARY_OUTPUT_DIRECTORY_RELEASE
        "${_MAGIC_GEO_PACKAGE_LIBRARY_OUTPUT_DIRECTORY}"
      RUNTIME_OUTPUT_DIRECTORY_RELEASE
        "${_MAGIC_GEO_PACKAGE_LIBRARY_OUTPUT_DIRECTORY}"
  )
  foreach(_magic_geo_isolated_config Debug RelWithDebInfo MinSizeRel)
    string(TOUPPER "${_magic_geo_isolated_config}" _magic_geo_config_upper)
    set_target_properties(
      magic_geo_native
      PROPERTIES
        "LIBRARY_OUTPUT_DIRECTORY_${_magic_geo_config_upper}"
          "${CMAKE_CURRENT_BINARY_DIR}/native/${_magic_geo_isolated_config}"
        "RUNTIME_OUTPUT_DIRECTORY_${_magic_geo_config_upper}"
          "${CMAKE_CURRENT_BINARY_DIR}/native/${_magic_geo_isolated_config}"
        "ARCHIVE_OUTPUT_DIRECTORY_${_magic_geo_config_upper}"
          "${CMAKE_CURRENT_BINARY_DIR}/native/${_magic_geo_isolated_config}"
    )
  endforeach()
endif()

if(OpenMP_CXX_FOUND)
  target_link_libraries(magic_geo_native PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(magic_geo_native PRIVATE MAGIC_GEO_HAS_OPENMP=1)
endif()

target_link_libraries(magic_geo_native PRIVATE ${CMAKE_DL_LIBS} Threads::Threads)

if(MAGIC_GEO_CUDA_ENABLED)
  target_compile_definitions(magic_geo_native PRIVATE MAGIC_GEO_HAS_CUDA=1)
  target_compile_options(
    magic_geo_native
    PRIVATE
      $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
  )
  # Embed the small runtime support layer so a CUDA-enabled wheel can still
  # load and use CPU/OpenCL on a host without a separately installed cudart.
  # libcuda itself remains driver-provided and is discovered by the runtime.
  set_target_properties(
    magic_geo_native
    PROPERTIES
      CUDA_ARCHITECTURES "${MAGIC_GEO_CUDA_ARCHITECTURES}"
      CUDA_RUNTIME_LIBRARY Static
      CUDA_SEPARABLE_COMPILATION OFF
      CUDA_STANDARD 20
      CUDA_STANDARD_REQUIRED ON
      CUDA_VISIBILITY_PRESET hidden
  )
endif()

install(
  TARGETS magic_geo_native
  LIBRARY DESTINATION magic_geo
  RUNTIME DESTINATION magic_geo
)

if(BUILD_TESTING)
  add_executable(magic_geo_solar_calendar_test
    cpp/tests/solar_calendar_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_solar_calendar_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_solar_calendar_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_solar_calendar_test PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_solar_calendar COMMAND magic_geo_solar_calendar_test controls)
  add_test(NAME magic_geo_solar_calendar_owner COMMAND magic_geo_solar_calendar_test owner)
  set_tests_properties(magic_geo_solar_calendar magic_geo_solar_calendar_owner PROPERTIES TIMEOUT 30)
  # Reuse the exact production objects for an internal finalized-surface entry
  # test without exporting that implementation through the public shared ABI.
  add_executable(magic_geo_finalized_enthalpy_context_test
    cpp/tests/finalized_enthalpy_context_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_finalized_enthalpy_context_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_finalized_enthalpy_context_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_finalized_enthalpy_context_test PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_finalized_enthalpy_context
    COMMAND magic_geo_finalized_enthalpy_context_test controls)
  add_test(NAME magic_geo_finalized_enthalpy_production
    COMMAND magic_geo_finalized_enthalpy_context_test production
      "${CMAKE_CURRENT_BINARY_DIR}/finalized_enthalpy_production_world.json")
  set_tests_properties(magic_geo_finalized_enthalpy_context PROPERTIES TIMEOUT 30)
  set_tests_properties(magic_geo_finalized_enthalpy_production PROPERTIES TIMEOUT 120 SKIP_RETURN_CODE 77)
  # Test the actual production objects and hidden geographic-stage API.
  add_executable(magic_geo_geographic_foundation_test
    cpp/tests/geographic_foundation_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_geographic_foundation_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_geographic_foundation_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_geographic_foundation_test PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_geographic_foundation
    COMMAND magic_geo_geographic_foundation_test --run "${CMAKE_CURRENT_BINARY_DIR}/geographic_foundation_output")
  set_tests_properties(magic_geo_geographic_foundation PROPERTIES TIMEOUT 120)
  add_executable(magic_geo_finalized_layered_state_test
    cpp/tests/finalized_layered_state_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_finalized_layered_state_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_finalized_layered_state_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_finalized_layered_state_test PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_finalized_layered_state
    COMMAND magic_geo_finalized_layered_state_test --controls)
  set_tests_properties(magic_geo_finalized_layered_state PROPERTIES TIMEOUT 120)
  # Data-only proof qualification uses retained fixtures and an explicitly
  # provisioned file; the large external-store exercise is never an automatic test.
  add_executable(magic_geo_enthalpy_mesh_proof_codec_test
    cpp/tests/enthalpy_mesh_proof_codec_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  add_executable(magic_geo_layered_proof_store_test
    cpp/tests/layered_proof_store_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  add_executable(magic_geo_layered_proof_record_test
    cpp/tests/layered_proof_record_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  add_executable(magic_geo_layered_ice_owner_metadata_test
    cpp/tests/layered_ice_owner_metadata_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  foreach(_target magic_geo_enthalpy_mesh_proof_codec_test magic_geo_layered_proof_store_test
                  magic_geo_layered_proof_record_test magic_geo_layered_ice_owner_metadata_test)
    target_include_directories(${_target} PRIVATE cpp/include cpp/src cpp/src/engine)
    target_link_libraries(${_target} PRIVATE $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
      target_compile_options(${_target} PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
    endif()
  endforeach()
  add_executable(magic_geo_layered_forcing_history_test
    cpp/tests/layered_ice_forcing_history_test.cpp cpp/src/engine/layered_ice_forcing_history.cpp)
  target_include_directories(magic_geo_layered_forcing_history_test PRIVATE cpp/src/engine)
  add_executable(magic_geo_layered_owner_storage_test
    cpp/tests/layered_ice_owner_storage_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_layered_owner_storage_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_layered_owner_storage_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  add_executable(magic_geo_layered_owner_storage_budget_test
    cpp/tests/layered_ice_owner_storage_budget_test.cpp $<TARGET_OBJECTS:magic_geo_native>)
  target_include_directories(magic_geo_layered_owner_storage_budget_test PRIVATE cpp/include cpp/src/engine)
  target_link_libraries(magic_geo_layered_owner_storage_budget_test PRIVATE
    $<TARGET_PROPERTY:magic_geo_native,LINK_LIBRARIES>)
  foreach(_target magic_geo_layered_forcing_history_test magic_geo_layered_owner_storage_test
                  magic_geo_layered_owner_storage_budget_test)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
      target_compile_options(${_target} PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
    endif()
    add_test(NAME ${_target} COMMAND ${_target} --run)
    set_tests_properties(${_target} PROPERTIES TIMEOUT 120)
  endforeach()
  # Explicit interval ownership only: these tests use synthetic fixed cells.
  # No simulation or climate generation is invoked by these executables.
  set(_terrestrial_test_sources
    cpp/src/engine/terrestrial_water.cpp
    cpp/src/engine/terrestrial_water_serialization.cpp
    cpp/src/engine/terrestrial_calorimeter_backend.cpp
    cpp/src/engine/hydrology.cpp cpp/src/engine/climate.cpp
    cpp/src/engine/core.cpp cpp/src/engine/numeric_serialization.cpp)
  set(_coupled_sources
    cpp/src/engine/terrestrial_coupled.cpp
    cpp/src/engine/terrestrial_coupled_error.cpp
    cpp/src/engine/terrestrial_thermal_backend.cpp
    cpp/src/engine/terrestrial_thermal/phase_segment.cpp
    cpp/src/engine/terrestrial_thermal/hermite_residual.cpp
    cpp/src/engine/terrestrial_thermal/phase_segment_serialization.cpp)
  # Pipeline exposes both opt-in owner modes; ordinary generation never calls them.
  list(APPEND _terrestrial_test_sources ${_coupled_sources})
  add_executable(magic_geo_enthalpy_mesh_test cpp/tests/enthalpy_mesh_test.cpp
    cpp/src/engine/enthalpy_mesh.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp
    cpp/src/engine/seasonal_energy_balance.cpp)
  target_include_directories(magic_geo_enthalpy_mesh_test PRIVATE cpp/include cpp/src/engine)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_enthalpy_mesh_test PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_enthalpy_mesh COMMAND magic_geo_enthalpy_mesh_test)
  add_executable(magic_geo_enthalpy_mesh_sdirk2_test cpp/tests/enthalpy_mesh_sdirk2_test.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2.cpp cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp
    cpp/src/engine/enthalpy_mesh.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp)
  add_executable(magic_geo_seasonal_liquid_routing_test cpp/tests/seasonal_liquid_routing_test.cpp
    cpp/src/engine/seasonal_liquid_routing.cpp)
  add_executable(magic_geo_enthalpy_mesh_pure_water_test cpp/tests/enthalpy_mesh_pure_water_test.cpp
    cpp/src/engine/enthalpy_mesh.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2.cpp cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  add_executable(magic_geo_layered_ice_column_test cpp/tests/layered_ice_column_test.cpp
    cpp/src/engine/layered_ice_column.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp)
  add_executable(magic_geo_layered_ice_thermal_test cpp/tests/layered_ice_thermal_test.cpp
    cpp/src/engine/layered_ice_column.cpp cpp/src/engine/enthalpy_mesh.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2.cpp cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  add_executable(magic_geo_layered_ice_material_test cpp/tests/layered_ice_material_test.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp)
  add_executable(magic_geo_layered_ice_remap_test cpp/tests/layered_ice_remap_test.cpp
    cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp)
  add_executable(magic_geo_layered_ice_topology_test cpp/tests/layered_ice_topology_test.cpp
    cpp/src/engine/layered_ice_topology.cpp cpp/src/engine/layered_ice_column.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp)
  add_executable(magic_geo_layered_material_successor_test cpp/tests/layered_material_successor_test.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp cpp/src/engine/enthalpy_mesh.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/enthalpy_mesh_sdirk2.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  add_executable(magic_geo_layered_material_unavailable_test cpp/tests/layered_material_unavailable_test.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_column.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp)
  target_compile_definitions(magic_geo_layered_material_unavailable_test PRIVATE MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER=1)
  add_executable(magic_geo_layered_ice_owner_test cpp/tests/layered_ice_owner_test.cpp
    cpp/src/engine/layered_ice_owner.cpp cpp/src/engine/layered_ice_owner_kernel.cpp cpp/src/engine/layered_ice_forcing_history.cpp cpp/src/engine/layered_ice_owner_ledger.cpp
    cpp/src/engine/layered_ice_absorption.cpp cpp/src/engine/layered_ice_topology.cpp
    cpp/src/engine/layered_ice_owner_serialization.cpp cpp/src/engine/seasonal_liquid_routing.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp cpp/src/engine/enthalpy_mesh.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/enthalpy_mesh_sdirk2.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  target_link_libraries(magic_geo_layered_ice_owner_test PRIVATE Threads::Threads)
  add_executable(magic_geo_layered_ice_absorption_owner_test cpp/tests/layered_ice_absorption_owner_test.cpp
    cpp/src/engine/layered_ice_owner.cpp cpp/src/engine/layered_ice_owner_kernel.cpp cpp/src/engine/layered_ice_forcing_history.cpp cpp/src/engine/layered_ice_owner_ledger.cpp
    cpp/src/engine/layered_ice_absorption.cpp cpp/src/engine/layered_ice_topology.cpp
    cpp/src/engine/layered_ice_owner_serialization.cpp cpp/src/engine/seasonal_liquid_routing.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp cpp/src/engine/enthalpy_mesh.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/enthalpy_mesh_sdirk2.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  target_link_libraries(magic_geo_layered_ice_absorption_owner_test PRIVATE Threads::Threads)
  add_executable(magic_geo_layered_ice_topology_owner_test cpp/tests/layered_ice_topology_owner_test.cpp
    cpp/src/engine/layered_ice_owner.cpp cpp/src/engine/layered_ice_owner_kernel.cpp cpp/src/engine/layered_ice_forcing_history.cpp cpp/src/engine/layered_ice_owner_ledger.cpp
    cpp/src/engine/layered_ice_absorption.cpp cpp/src/engine/layered_ice_topology.cpp
    cpp/src/engine/layered_ice_owner_serialization.cpp cpp/src/engine/seasonal_liquid_routing.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp cpp/src/engine/enthalpy_mesh.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/enthalpy_mesh_sdirk2.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  target_link_libraries(magic_geo_layered_ice_topology_owner_test PRIVATE Threads::Threads)
  add_executable(magic_geo_layered_ice_owner_quota_test cpp/tests/layered_ice_owner_quota_test.cpp
    cpp/src/engine/layered_ice_owner.cpp cpp/src/engine/layered_ice_owner_kernel.cpp cpp/src/engine/layered_ice_forcing_history.cpp cpp/src/engine/layered_ice_owner_ledger.cpp
    cpp/src/engine/layered_ice_absorption.cpp cpp/src/engine/layered_ice_topology.cpp
    cpp/src/engine/layered_ice_owner_serialization.cpp cpp/src/engine/seasonal_liquid_routing.cpp
    cpp/src/engine/layered_ice_material.cpp cpp/src/engine/layered_ice_remap.cpp cpp/src/engine/layered_ice_column.cpp
    cpp/src/engine/terrestrial_calorimeter/cryosphere_enthalpy.cpp cpp/src/engine/enthalpy_mesh.cpp
    cpp/src/engine/enthalpy_mesh_serialization.cpp cpp/src/engine/enthalpy_mesh_sdirk2.cpp
    cpp/src/engine/enthalpy_mesh_sdirk2_serialization.cpp)
  target_link_libraries(magic_geo_layered_ice_owner_quota_test PRIVATE Threads::Threads)
  foreach(_target magic_geo_enthalpy_mesh_sdirk2_test magic_geo_seasonal_liquid_routing_test
      magic_geo_enthalpy_mesh_pure_water_test magic_geo_layered_ice_column_test magic_geo_layered_ice_thermal_test
      magic_geo_layered_ice_material_test magic_geo_layered_ice_remap_test magic_geo_layered_material_successor_test
      magic_geo_layered_material_unavailable_test magic_geo_layered_ice_owner_test magic_geo_layered_ice_absorption_owner_test
      magic_geo_layered_ice_topology_test magic_geo_layered_ice_topology_owner_test magic_geo_layered_ice_owner_quota_test)
    target_include_directories(${_target} PRIVATE cpp/include cpp/src cpp/src/engine)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
      target_compile_options(${_target} PRIVATE -Wall -Wextra -Werror -ffp-contract=off)
    endif()
    if(_target STREQUAL "magic_geo_layered_ice_column_test" OR _target STREQUAL "magic_geo_layered_ice_remap_test" OR _target STREQUAL "magic_geo_layered_ice_owner_test" OR _target STREQUAL "magic_geo_layered_ice_absorption_owner_test" OR _target STREQUAL "magic_geo_layered_ice_topology_test" OR _target STREQUAL "magic_geo_layered_ice_topology_owner_test" OR _target STREQUAL "magic_geo_layered_ice_owner_quota_test")
      add_test(NAME ${_target} COMMAND ${_target} --run)
    else()
      add_test(NAME ${_target} COMMAND ${_target})
    endif()
    set_tests_properties(${_target} PROPERTIES TIMEOUT 30)
  endforeach()
  add_executable(magic_geo_enthalpy_mesh_owner_test cpp/tests/enthalpy_mesh_owner_test.cpp
    cpp/src/engine/enthalpy_mesh_owner.cpp cpp/src/engine/enthalpy_mesh_owner_serialization.cpp
    cpp/src/engine/enthalpy_mesh.cpp cpp/src/engine/enthalpy_mesh_serialization.cpp
    ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_test
    cpp/tests/terrestrial_coupled_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_fixed_duration_test
    cpp/tests/terrestrial_coupled_fixed_duration_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_hermite_residual_test
    cpp/tests/terrestrial_hermite_residual_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_automatic_sources_test
    cpp/tests/terrestrial_coupled_automatic_sources_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_automatic_test
    cpp/tests/terrestrial_coupled_automatic_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_error_test
    cpp/tests/terrestrial_coupled_error_test.cpp
    cpp/src/engine/terrestrial_coupled_error.cpp)
  add_executable(magic_geo_terrestrial_coupled_segment_error_test
    cpp/tests/terrestrial_coupled_segment_error_test.cpp
    cpp/src/engine/terrestrial_coupled_error.cpp)
  add_executable(magic_geo_terrestrial_coupled_pipeline_test
    cpp/tests/terrestrial_coupled_pipeline_test.cpp cpp/src/engine/pipeline.cpp
    cpp/src/engine/seasonal_climate_cache.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_coupled_unavailable_test
    cpp/tests/terrestrial_coupled_pipeline_test.cpp cpp/src/engine/pipeline.cpp
    cpp/src/engine/seasonal_climate_cache.cpp ${_terrestrial_test_sources})
  target_compile_definitions(magic_geo_terrestrial_coupled_unavailable_test
    PRIVATE MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER=1)
  add_executable(magic_geo_terrestrial_water_test
    cpp/tests/terrestrial_water_test.cpp ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_mass_event_test
    cpp/tests/terrestrial_mass_event_test.cpp
    cpp/src/engine/terrestrial_calorimeter_backend.cpp)
  add_executable(magic_geo_terrestrial_water_pipeline_test
    cpp/tests/terrestrial_water_pipeline_test.cpp cpp/src/engine/pipeline.cpp
    cpp/src/engine/seasonal_climate_cache.cpp
    ${_terrestrial_test_sources})
  add_executable(magic_geo_terrestrial_water_unavailable_test
    cpp/tests/terrestrial_water_pipeline_test.cpp cpp/src/engine/pipeline.cpp
    cpp/src/engine/seasonal_climate_cache.cpp
    ${_terrestrial_test_sources})
  target_compile_definitions(magic_geo_terrestrial_water_unavailable_test
    PRIVATE MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER=1)
  add_executable(magic_geo_terrestrial_hydrology_parity_test
    cpp/tests/terrestrial_hydrology_parity_test.cpp cpp/src/engine/hydrology.cpp
    cpp/src/engine/climate.cpp cpp/src/engine/core.cpp
    cpp/src/engine/process_serialization.cpp cpp/src/engine/entity_serialization.cpp
    cpp/src/engine/numeric_serialization.cpp)
  foreach(_terrestrial_target
    magic_geo_enthalpy_mesh_owner_test
    magic_geo_terrestrial_coupled_test magic_geo_terrestrial_coupled_error_test
    magic_geo_terrestrial_coupled_fixed_duration_test
    magic_geo_terrestrial_hermite_residual_test
    magic_geo_terrestrial_coupled_automatic_test
    magic_geo_terrestrial_coupled_automatic_sources_test
    magic_geo_terrestrial_coupled_segment_error_test
    magic_geo_terrestrial_coupled_pipeline_test magic_geo_terrestrial_coupled_unavailable_test
    magic_geo_terrestrial_water_test magic_geo_terrestrial_mass_event_test
    magic_geo_terrestrial_water_pipeline_test
    magic_geo_terrestrial_water_unavailable_test magic_geo_terrestrial_hydrology_parity_test)
    target_include_directories(${_terrestrial_target} PRIVATE cpp/include cpp/src/engine)
    if(OpenMP_CXX_FOUND)
      target_link_libraries(${_terrestrial_target} PRIVATE OpenMP::OpenMP_CXX)
    endif()
    if(MSVC)
      target_compile_options(${_terrestrial_target} PRIVATE /Gy /Gw)
      target_link_options(${_terrestrial_target} PRIVATE /OPT:REF)
    elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
      target_compile_options(${_terrestrial_target} PRIVATE -Wall -Wextra -Werror
        -ffunction-sections -fdata-sections -ffp-contract=off)
      if(APPLE)
        target_link_options(${_terrestrial_target} PRIVATE -Wl,-dead_strip)
      else()
        target_link_options(${_terrestrial_target} PRIVATE -Wl,--gc-sections)
      endif()
    endif()
  endforeach()
  add_test(NAME magic_geo_terrestrial_coupled COMMAND magic_geo_terrestrial_coupled_test)
  add_test(NAME magic_geo_enthalpy_mesh_owner COMMAND magic_geo_enthalpy_mesh_owner_test)
  add_test(NAME magic_geo_terrestrial_coupled_fixed_duration COMMAND magic_geo_terrestrial_coupled_fixed_duration_test)
  add_test(NAME magic_geo_terrestrial_hermite_residual COMMAND magic_geo_terrestrial_hermite_residual_test)
  add_test(NAME magic_geo_terrestrial_coupled_automatic COMMAND magic_geo_terrestrial_coupled_automatic_test)
  add_test(NAME magic_geo_terrestrial_coupled_automatic_sources COMMAND magic_geo_terrestrial_coupled_automatic_sources_test)
  add_test(NAME magic_geo_terrestrial_coupled_error COMMAND magic_geo_terrestrial_coupled_error_test)
  add_test(NAME magic_geo_terrestrial_coupled_segment_error COMMAND magic_geo_terrestrial_coupled_segment_error_test)
  add_test(NAME magic_geo_terrestrial_coupled_pipeline COMMAND magic_geo_terrestrial_coupled_pipeline_test)
  add_test(NAME magic_geo_terrestrial_coupled_unavailable COMMAND magic_geo_terrestrial_coupled_unavailable_test)
  add_test(NAME magic_geo_terrestrial_water COMMAND magic_geo_terrestrial_water_test)
  add_test(NAME magic_geo_terrestrial_mass_event COMMAND magic_geo_terrestrial_mass_event_test)
  add_test(NAME magic_geo_terrestrial_water_pipeline COMMAND magic_geo_terrestrial_water_pipeline_test)
  add_test(NAME magic_geo_terrestrial_water_unavailable COMMAND magic_geo_terrestrial_water_unavailable_test)
  # Parity is checked by the bounded external original/candidate comparison,
  # not by this witness executable's successful exit alone.

  add_executable(magic_geo_grounded_ice_domain_test
    cpp/tests/grounded_ice_domain_test.cpp
    cpp/src/engine/environment.cpp cpp/src/engine/climate.cpp
    cpp/src/engine/core.cpp cpp/src/engine/hydrology.cpp
    cpp/src/engine/sediment_partition.cpp cpp/src/engine/process_serialization.cpp
    cpp/src/engine/entity_serialization.cpp cpp/src/engine/numeric_serialization.cpp)
  target_include_directories(magic_geo_grounded_ice_domain_test PRIVATE cpp/include cpp/src/engine)
  if(OpenMP_CXX_FOUND)
    target_link_libraries(magic_geo_grounded_ice_domain_test PRIVATE OpenMP::OpenMP_CXX)
  endif()
  if(MSVC)
    target_compile_options(magic_geo_grounded_ice_domain_test PRIVATE /Gy /Gw)
    target_link_options(magic_geo_grounded_ice_domain_test PRIVATE /OPT:REF)
  elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_grounded_ice_domain_test PRIVATE -Wall -Wextra -Werror -ffunction-sections -fdata-sections -ffp-contract=off)
    if(APPLE)
      target_link_options(magic_geo_grounded_ice_domain_test PRIVATE -Wl,-dead_strip)
    else()
      target_link_options(magic_geo_grounded_ice_domain_test PRIVATE -Wl,--gc-sections)
    endif()
  endif()
  add_test(NAME magic_geo_grounded_ice_domain COMMAND magic_geo_grounded_ice_domain_test)

  # Compile the real settlement/environment functions into the focused test.
  # Section elimination omits uncalled simulation subsystems without runtime
  # stubs or exporting private engine symbols from the public C library.
  add_executable(magic_geo_social_availability_test
    cpp/tests/social_availability_test.cpp
    cpp/src/engine/civilization.cpp cpp/src/engine/history.cpp cpp/src/engine/settlements.cpp
    cpp/src/engine/environment.cpp cpp/src/engine/climate.cpp
    cpp/src/engine/core.cpp cpp/src/engine/water_features.cpp cpp/src/engine/summary.cpp cpp/src/engine/process_serialization.cpp cpp/src/engine/hydrology.cpp
    cpp/src/engine/entity_serialization.cpp cpp/src/engine/numeric_serialization.cpp)
  target_include_directories(magic_geo_social_availability_test PRIVATE cpp/include cpp/src/engine)
  if(OpenMP_CXX_FOUND)
    target_link_libraries(magic_geo_social_availability_test PRIVATE OpenMP::OpenMP_CXX)
  endif()
  if(MSVC)
    target_compile_options(magic_geo_social_availability_test PRIVATE /Gy /Gw)
    target_link_options(magic_geo_social_availability_test PRIVATE /OPT:REF)
  elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_social_availability_test PRIVATE -Wall -Wextra -Werror -ffunction-sections -fdata-sections -ffp-contract=off)
    if(APPLE)
      target_link_options(magic_geo_social_availability_test PRIVATE -Wl,-dead_strip)
    else()
      target_link_options(magic_geo_social_availability_test PRIVATE -Wl,--gc-sections)
    endif()
  endif()
  add_test(NAME magic_geo_social_availability COMMAND magic_geo_social_availability_test "${CMAKE_CURRENT_BINARY_DIR}/native_social_unit_worlds.json")

  # Exercise real summary/entity serialization without any world generation.
  add_executable(magic_geo_watershed_summary_precision_test
    cpp/tests/watershed_summary_precision_test.cpp
    cpp/src/engine/core.cpp cpp/src/engine/water_features.cpp
    cpp/src/engine/summary.cpp cpp/src/engine/process_serialization.cpp
    cpp/src/engine/hydrology.cpp cpp/src/engine/entity_serialization.cpp
    cpp/src/engine/numeric_serialization.cpp)
  target_include_directories(magic_geo_watershed_summary_precision_test PRIVATE cpp/include cpp/src/engine)
  if(OpenMP_CXX_FOUND)
    target_link_libraries(magic_geo_watershed_summary_precision_test PRIVATE OpenMP::OpenMP_CXX)
  endif()
  if(MSVC)
    target_compile_options(magic_geo_watershed_summary_precision_test PRIVATE /Gy /Gw)
    target_link_options(magic_geo_watershed_summary_precision_test PRIVATE /OPT:REF)
  elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_watershed_summary_precision_test PRIVATE -Wall -Wextra -Werror -ffunction-sections -fdata-sections -ffp-contract=off)
    if(APPLE)
      target_link_options(magic_geo_watershed_summary_precision_test PRIVATE -Wl,-dead_strip)
    else()
      target_link_options(magic_geo_watershed_summary_precision_test PRIVATE -Wl,--gc-sections)
    endif()
  endif()
  add_test(NAME magic_geo_watershed_summary_precision COMMAND magic_geo_watershed_summary_precision_test)

  add_executable(
    magic_geo_settlement_climate_support_test
    cpp/tests/settlement_climate_support_test.cpp
    cpp/src/engine/environment.cpp
    cpp/src/engine/settlements.cpp
    cpp/src/engine/civilization.cpp
    cpp/src/engine/climate.cpp
    cpp/src/engine/core.cpp
    cpp/src/engine/entity_serialization.cpp
    cpp/src/engine/numeric_serialization.cpp
  )
  target_include_directories(magic_geo_settlement_climate_support_test PRIVATE cpp/include cpp/src/engine)
  if(MSVC)
    target_compile_options(magic_geo_settlement_climate_support_test PRIVATE /Gy /Gw)
    target_link_options(magic_geo_settlement_climate_support_test PRIVATE /OPT:REF)
  elseif(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_settlement_climate_support_test PRIVATE
      -ffunction-sections -fdata-sections -ffp-contract=off)
    if(APPLE)
      target_link_options(magic_geo_settlement_climate_support_test PRIVATE -Wl,-dead_strip)
    else()
      target_link_options(magic_geo_settlement_climate_support_test PRIVATE -Wl,--gc-sections)
    endif()
  endif()
  add_test(
    NAME magic_geo_settlement_climate_support
    COMMAND magic_geo_settlement_climate_support_test
      "${CMAKE_CURRENT_BINARY_DIR}/settlement_climate_unit_worlds.json"
  )

  # Keep the four seasonal ABI success routes in one CTest invocation. The
  # older native_api executable is intentionally invoked twice for KNN checks.
  add_executable(magic_geo_c_api_v4_test cpp/tests/c_api_v4_test.cpp)
  target_include_directories(magic_geo_c_api_v4_test PRIVATE cpp/include)
  target_link_libraries(magic_geo_c_api_v4_test PRIVATE magic_geo_native)
  add_test(
    NAME magic_geo_c_api_v4
    COMMAND magic_geo_c_api_v4_test "${CMAKE_CURRENT_BINARY_DIR}/c_api_v4_world.json"
  )

  # Recompile the exact C boundary with cheap generator stubs and executable-
  # local allocation faults; no failure-injection API enters the shared library.
  add_executable(
    magic_geo_c_api_v4_allocation_test
    cpp/tests/c_api_v4_allocation_test.cpp
    cpp/src/c_api.cpp
    cpp/src/engine/messagepack.cpp
  )
  target_include_directories(magic_geo_c_api_v4_allocation_test PRIVATE cpp/include cpp/src)
  target_compile_definitions(magic_geo_c_api_v4_allocation_test PRIVATE magic_geo_native_EXPORTS)
  if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_definitions(magic_geo_c_api_v4_allocation_test PRIVATE MAGIC_GEO_TEST_WRAP_MALLOC=1)
    target_link_options(magic_geo_c_api_v4_allocation_test PRIVATE -Wl,--wrap=malloc)
  endif()
  add_test(NAME magic_geo_c_api_v4_allocation COMMAND magic_geo_c_api_v4_allocation_test)

  add_executable(
    magic_geo_seasonal_climate_pipeline_test
    cpp/tests/seasonal_climate_pipeline_test.cpp
  )
  target_include_directories(magic_geo_seasonal_climate_pipeline_test PRIVATE cpp/include)
  target_link_libraries(magic_geo_seasonal_climate_pipeline_test PRIVATE magic_geo_native Threads::Threads)
  if(OpenMP_CXX_FOUND)
    target_link_libraries(magic_geo_seasonal_climate_pipeline_test PRIVATE OpenMP::OpenMP_CXX)
  endif()
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_seasonal_climate_pipeline_test PRIVATE -ffp-contract=off)
  endif()
  add_test(
    NAME magic_geo_seasonal_climate_pipeline
    COMMAND magic_geo_seasonal_climate_pipeline_test
      "${CMAKE_CURRENT_BINARY_DIR}/seasonal_climate_pipeline_world.json"
  )

  add_executable(
    magic_geo_seasonal_climate_serialization_test
    cpp/tests/seasonal_climate_serialization_test.cpp
    cpp/src/engine/seasonal_climate_serialization.cpp
    cpp/src/engine/seasonal_climate_cache.cpp
    cpp/src/engine/seasonal_climate.cpp
    cpp/src/engine/physical_columns.cpp
    cpp/src/engine/climate_transport.cpp
    cpp/src/engine/mesh.cpp
    cpp/src/engine/core.cpp
    cpp/src/engine/numeric_serialization.cpp
    cpp/src/engine/messagepack.cpp
    cpp/src/engine/adaptive_energy_balance.cpp
    cpp/src/engine/periodic_energy_balance.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
    cpp/src/engine/solar_insolation.cpp
  )
  target_include_directories(magic_geo_seasonal_climate_serialization_test PRIVATE cpp/include cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_seasonal_climate_serialization_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_seasonal_climate_serialization COMMAND magic_geo_seasonal_climate_serialization_test)

  add_executable(
    magic_geo_seasonal_climate_cache_test
    cpp/tests/seasonal_climate_cache_test.cpp
    cpp/src/engine/seasonal_climate_cache.cpp
    cpp/src/engine/seasonal_climate.cpp
    cpp/src/engine/physical_columns.cpp
    cpp/src/engine/climate_transport.cpp
    cpp/src/engine/mesh.cpp
    cpp/src/engine/core.cpp
    cpp/src/engine/adaptive_energy_balance.cpp
    cpp/src/engine/periodic_energy_balance.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
    cpp/src/engine/solar_insolation.cpp
  )
  target_include_directories(magic_geo_seasonal_climate_cache_test PRIVATE cpp/include cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_seasonal_climate_cache_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_seasonal_climate_cache COMMAND magic_geo_seasonal_climate_cache_test)

  add_executable(
    magic_geo_seasonal_climate_test
    cpp/tests/seasonal_climate_test.cpp
    cpp/src/engine/seasonal_climate.cpp
    cpp/src/engine/physical_columns.cpp
    cpp/src/engine/climate_transport.cpp
    cpp/src/engine/mesh.cpp
    cpp/src/engine/core.cpp
    cpp/src/engine/adaptive_energy_balance.cpp
    cpp/src/engine/periodic_energy_balance.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
    cpp/src/engine/solar_insolation.cpp
  )
  target_include_directories(magic_geo_seasonal_climate_test PRIVATE cpp/include cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_seasonal_climate_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_seasonal_climate COMMAND magic_geo_seasonal_climate_test)

  add_executable(
    magic_geo_physical_columns_test
    cpp/tests/physical_columns_test.cpp
    cpp/src/engine/physical_columns.cpp
  )
  target_include_directories(magic_geo_physical_columns_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_physical_columns_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_physical_columns COMMAND magic_geo_physical_columns_test)

  add_executable(
    magic_geo_variable_climate_transport_test
    cpp/tests/variable_climate_transport_test.cpp
    cpp/src/engine/climate_transport.cpp
    cpp/src/engine/mesh.cpp
    cpp/src/engine/core.cpp
  )
  target_include_directories(magic_geo_variable_climate_transport_test PRIVATE cpp/include cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_variable_climate_transport_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_variable_climate_transport COMMAND magic_geo_variable_climate_transport_test)

  add_executable(
    magic_geo_adaptive_energy_balance_test
    cpp/tests/adaptive_energy_balance_test.cpp
    cpp/src/engine/adaptive_energy_balance.cpp
    cpp/src/engine/periodic_energy_balance.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
  )
  target_include_directories(magic_geo_adaptive_energy_balance_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_adaptive_energy_balance_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_adaptive_energy_balance COMMAND magic_geo_adaptive_energy_balance_test)

  add_executable(
    magic_geo_time_integrated_energy_test
    cpp/tests/time_integrated_energy_test.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
  )
  target_include_directories(magic_geo_time_integrated_energy_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_time_integrated_energy_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_time_integrated_energy COMMAND magic_geo_time_integrated_energy_test)

  add_executable(
    magic_geo_periodic_energy_balance_test
    cpp/tests/periodic_energy_balance_test.cpp
    cpp/src/engine/periodic_energy_balance.cpp
    cpp/src/engine/time_integrated_energy.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
  )
  target_include_directories(magic_geo_periodic_energy_balance_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_periodic_energy_balance_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_periodic_energy_balance COMMAND magic_geo_periodic_energy_balance_test)

  add_executable(
    magic_geo_solar_insolation_test
    cpp/tests/solar_insolation_test.cpp
    cpp/src/engine/solar_insolation.cpp
  )
  target_include_directories(magic_geo_solar_insolation_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_solar_insolation_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_solar_insolation COMMAND magic_geo_solar_insolation_test)

  add_executable(
    magic_geo_climate_transport_test
    cpp/tests/climate_transport_test.cpp
    cpp/src/engine/climate_transport.cpp
    cpp/src/engine/mesh.cpp
    cpp/src/engine/core.cpp
  )
  target_include_directories(magic_geo_climate_transport_test PRIVATE cpp/include cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_climate_transport_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_climate_transport COMMAND magic_geo_climate_transport_test)

  add_executable(
    magic_geo_seasonal_energy_balance_test
    cpp/tests/seasonal_energy_balance_test.cpp
    cpp/src/engine/seasonal_energy_balance.cpp
  )
  target_include_directories(magic_geo_seasonal_energy_balance_test PRIVATE cpp/src)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(magic_geo_seasonal_energy_balance_test PRIVATE -ffp-contract=off)
  endif()
  add_test(NAME magic_geo_seasonal_energy_balance COMMAND magic_geo_seasonal_energy_balance_test)

  add_executable(
    magic_geo_initial_oceanic_age_test
    cpp/tests/initial_oceanic_age_test.cpp
    cpp/src/engine/initial_oceanic_age.cpp
  )
  target_include_directories(
    magic_geo_initial_oceanic_age_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_initial_oceanic_age_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_initial_oceanic_age_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_initial_oceanic_age
    COMMAND magic_geo_initial_oceanic_age_test
  )

  add_executable(
    magic_geo_oceanic_age_depth_test
    cpp/tests/oceanic_age_depth_test.cpp
    cpp/src/engine/oceanic_age_depth.cpp
  )
  target_include_directories(
    magic_geo_oceanic_age_depth_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_oceanic_age_depth_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_oceanic_age_depth_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_oceanic_age_depth
    COMMAND magic_geo_oceanic_age_depth_test
  )

  add_executable(
    magic_geo_oceanic_age_depth_integration_test
    cpp/tests/oceanic_age_depth_integration_test.cpp
  )
  target_include_directories(
    magic_geo_oceanic_age_depth_integration_test PRIVATE cpp/include
  )
  target_link_libraries(
    magic_geo_oceanic_age_depth_integration_test
    PRIVATE magic_geo_native Threads::Threads
  )
  if(OpenMP_CXX_FOUND)
    target_link_libraries(
      magic_geo_oceanic_age_depth_integration_test
      PRIVATE OpenMP::OpenMP_CXX
    )
  endif()
  target_compile_features(
    magic_geo_oceanic_age_depth_integration_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_oceanic_age_depth_integration_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_oceanic_age_depth_integration
    COMMAND magic_geo_oceanic_age_depth_integration_test
  )

  add_executable(
    magic_geo_crust_overlap_shadow_test
    cpp/tests/crust_overlap_shadow_test.cpp
    cpp/src/crust_overlap_shadow.cpp
  )
  target_include_directories(
    magic_geo_crust_overlap_shadow_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_crust_overlap_shadow_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_crust_overlap_shadow_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_crust_overlap_shadow
    COMMAND magic_geo_crust_overlap_shadow_test
  )

  add_executable(
    magic_geo_serialization_roundtrip_test
    cpp/tests/serialization_roundtrip_test.cpp
    cpp/src/engine/messagepack.cpp
    cpp/src/engine/numeric_serialization.cpp
    cpp/src/engine/core.cpp
  )
  target_include_directories(
    magic_geo_serialization_roundtrip_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_serialization_roundtrip_test PRIVATE cxx_std_20
  )
  add_test(
    NAME magic_geo_serialization_roundtrip
    COMMAND magic_geo_serialization_roundtrip_test
  )

  add_executable(
    magic_geo_plate_boundary_segments_test
    cpp/tests/plate_boundary_segments_test.cpp
    cpp/src/engine/plate_boundary_segments.cpp
  )
  target_include_directories(
    magic_geo_plate_boundary_segments_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_plate_boundary_segments_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_plate_boundary_segments_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_plate_boundary_segments
    COMMAND magic_geo_plate_boundary_segments_test
  )

  add_executable(
    magic_geo_crust_overlap_candidate_fate_test
    cpp/tests/crust_overlap_candidate_fate_test.cpp
    cpp/src/engine/crust_overlap_candidate_fate.cpp
  )
  target_include_directories(
    magic_geo_crust_overlap_candidate_fate_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(
    magic_geo_crust_overlap_candidate_fate_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_crust_overlap_candidate_fate_test PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_crust_overlap_candidate_fate
    COMMAND magic_geo_crust_overlap_candidate_fate_test
  )

  add_executable(
    magic_geo_crust_reservoir_test
    cpp/tests/crust_reservoir_test.cpp
    cpp/src/engine/crust_reservoir.cpp
  )
  target_include_directories(
    magic_geo_crust_reservoir_test
    PRIVATE cpp/include cpp/src
  )
  target_compile_features(magic_geo_crust_reservoir_test PRIVATE cxx_std_20)
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_crust_reservoir_test
      PRIVATE -ffp-contract=off
    )
  endif()
  add_test(NAME magic_geo_crust_reservoir COMMAND magic_geo_crust_reservoir_test)

  add_executable(
    magic_geo_crust_reservoir_integration_test
    cpp/tests/crust_reservoir_integration_test.cpp
  )
  target_include_directories(
    magic_geo_crust_reservoir_integration_test
    PRIVATE cpp/include
  )
  target_link_libraries(
    magic_geo_crust_reservoir_integration_test
    PRIVATE magic_geo_native Threads::Threads
  )
  if(OpenMP_CXX_FOUND)
    target_link_libraries(
      magic_geo_crust_reservoir_integration_test
      PRIVATE OpenMP::OpenMP_CXX
    )
  endif()
  target_compile_features(
    magic_geo_crust_reservoir_integration_test PRIVATE cxx_std_20
  )
  add_test(
    NAME magic_geo_crust_reservoir_integration
    COMMAND magic_geo_crust_reservoir_integration_test
  )

  add_executable(
    magic_geo_sediment_partition_test
    cpp/tests/sediment_partition_test.cpp
    cpp/src/engine/sediment_partition.cpp
  )
  target_include_directories(
    magic_geo_sediment_partition_test
    PRIVATE cpp/include cpp/src
  )
  target_link_libraries(
    magic_geo_sediment_partition_test
    PRIVATE magic_geo_native Threads::Threads
  )
  if(OpenMP_CXX_FOUND)
    target_link_libraries(
      magic_geo_sediment_partition_test
      PRIVATE OpenMP::OpenMP_CXX
    )
  endif()
  target_compile_features(
    magic_geo_sediment_partition_test PRIVATE cxx_std_20
  )
  if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
    target_compile_options(
      magic_geo_sediment_partition_test
      PRIVATE -ffp-contract=off
    )
  endif()
  add_test(
    NAME magic_geo_sediment_partition
    COMMAND magic_geo_sediment_partition_test
  )

  add_executable(magic_geo_native_api_test cpp/tests/native_api_test.cpp)
  target_include_directories(magic_geo_native_api_test PRIVATE cpp/include)
  target_link_libraries(
    magic_geo_native_api_test
    PRIVATE magic_geo_native Threads::Threads
  )
  if(OpenMP_CXX_FOUND)
    target_link_libraries(magic_geo_native_api_test PRIVATE OpenMP::OpenMP_CXX)
  endif()
  target_compile_features(magic_geo_native_api_test PRIVATE cxx_std_20)
  add_test(NAME magic_geo_native_api COMMAND magic_geo_native_api_test)
  add_test(NAME magic_geo_fibonacci_knn_reference COMMAND magic_geo_native_api_test)
  set_tests_properties(
    magic_geo_fibonacci_knn_reference
    PROPERTIES ENVIRONMENT "MAGIC_GEO_VALIDATE_FIBONACCI_KNN=1"
  )
  if(MAGIC_GEO_CUDA_ENABLED)
    add_executable(
      magic_geo_cuda_compute_test
      cpp/tests/cuda_compute_test.cpp
      cpp/src/cuda_compute.cu
      cpp/src/crust_overlap_shadow.cpp
    )
    target_include_directories(
      magic_geo_cuda_compute_test
      PRIVATE cpp/include cpp/src ${CUDAToolkit_INCLUDE_DIRS}
    )
    target_compile_features(magic_geo_cuda_compute_test PRIVATE cxx_std_20)
    if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
      target_compile_options(
        magic_geo_cuda_compute_test
        PRIVATE $<$<COMPILE_LANGUAGE:CXX>:-ffp-contract=off>
      )
    endif()
    target_compile_options(
      magic_geo_cuda_compute_test
      PRIVATE
        $<$<COMPILE_LANGUAGE:CUDA>:--fmad=false;--ftz=false;--prec-div=true;--prec-sqrt=true;-lineinfo>
    )
    set_target_properties(
      magic_geo_cuda_compute_test
      PROPERTIES
        CUDA_ARCHITECTURES "${MAGIC_GEO_CUDA_ARCHITECTURES}"
        CUDA_RUNTIME_LIBRARY Static
        CUDA_SEPARABLE_COMPILATION OFF
        CUDA_STANDARD 20
        CUDA_STANDARD_REQUIRED ON
    )
    add_test(NAME magic_geo_cuda_compute COMMAND magic_geo_cuda_compute_test)
    set_tests_properties(
      magic_geo_cuda_compute
      PROPERTIES SKIP_RETURN_CODE 77
    )
  endif()
  if(CMAKE_SIZEOF_VOID_P EQUAL 8)
    add_executable(
      magic_geo_c_api_v1_client_test
      cpp/tests/c_api_v1_client_test.cpp
    )
    target_link_libraries(
      magic_geo_c_api_v1_client_test
      PRIVATE magic_geo_native
    )
    target_compile_features(magic_geo_c_api_v1_client_test PRIVATE cxx_std_20)
    add_test(
      NAME magic_geo_c_api_v1_client
      COMMAND magic_geo_c_api_v1_client_test
    )
  endif()
endif()
