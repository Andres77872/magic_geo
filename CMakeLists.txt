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

target_link_libraries(magic_geo_native PRIVATE ${CMAKE_DL_LIBS})

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
      magic_geo_legacy_v1_client_test
      cpp/tests/legacy_v1_client_test.cpp
    )
    target_link_libraries(
      magic_geo_legacy_v1_client_test
      PRIVATE magic_geo_native
    )
    target_compile_features(magic_geo_legacy_v1_client_test PRIVATE cxx_std_20)
    add_test(
      NAME magic_geo_legacy_v1_client
      COMMAND magic_geo_legacy_v1_client_test
    )
  endif()
endif()
