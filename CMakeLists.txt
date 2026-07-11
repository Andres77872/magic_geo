cmake_minimum_required(VERSION 3.20)

project(magic_geo VERSION 0.1.0 LANGUAGES CXX)

include(CTest)

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

add_library(
  magic_geo_native SHARED
  cpp/src/c_api.cpp
  cpp/src/engine.cpp
  cpp/src/engine/climate.cpp
  cpp/src/engine/civilization.cpp
  cpp/src/engine/core.cpp
  cpp/src/engine/earth_system.cpp
  cpp/src/engine/entity_serialization.cpp
  cpp/src/engine/environment.cpp
  cpp/src/engine/history.cpp
  cpp/src/engine/hydrology.cpp
  cpp/src/engine/mesh.cpp
  cpp/src/engine/ocean.cpp
  cpp/src/engine/pipeline.cpp
  cpp/src/engine/process_serialization.cpp
  cpp/src/engine/settlements.cpp
  cpp/src/engine/summary.cpp
  cpp/src/engine/tectonics.cpp
  cpp/src/engine/water_features.cpp
  cpp/src/engine/world_serialization.cpp
  cpp/src/opencl_compute.cpp
)

target_include_directories(magic_geo_native PRIVATE cpp/include)
target_compile_features(magic_geo_native PRIVATE cxx_std_20)

# Keep contraction policy stable in optimized CPU code. This prevents FMA from
# introducing avoidable backend drift; cross-compiler/GPU parity is validated
# with numeric tolerances and physical invariants rather than byte hashes.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(magic_geo_native PRIVATE -ffp-contract=off)
endif()
set_target_properties(
  magic_geo_native
  PROPERTIES
    CXX_VISIBILITY_PRESET hidden
    OUTPUT_NAME "magic_geo_native"
    LIBRARY_OUTPUT_DIRECTORY "${MAGIC_GEO_LIBRARY_OUTPUT_DIRECTORY}"
    VISIBILITY_INLINES_HIDDEN YES
)

if(OpenMP_CXX_FOUND)
  target_link_libraries(magic_geo_native PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(magic_geo_native PRIVATE MAGIC_GEO_HAS_OPENMP=1)
endif()

target_link_libraries(magic_geo_native PRIVATE ${CMAKE_DL_LIBS})

install(TARGETS magic_geo_native LIBRARY DESTINATION magic_geo)

if(BUILD_TESTING)
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
