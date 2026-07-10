cmake_minimum_required(VERSION 3.20)

project(magic_geo VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

find_package(OpenMP)

add_library(
  magic_geo_native SHARED
  cpp/src/c_api.cpp
  cpp/src/engine.cpp
  cpp/src/opencl_probe.cpp
)

target_include_directories(magic_geo_native PRIVATE cpp/include)
target_compile_features(magic_geo_native PRIVATE cxx_std_20)
set_target_properties(
  magic_geo_native
  PROPERTIES
    OUTPUT_NAME "magic_geo_native"
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/src/magic_geo"
)

if(OpenMP_CXX_FOUND)
  target_link_libraries(magic_geo_native PRIVATE OpenMP::OpenMP_CXX)
  target_compile_definitions(magic_geo_native PRIVATE MAGIC_GEO_HAS_OPENMP=1)
endif()

target_link_libraries(magic_geo_native PRIVATE ${CMAKE_DL_LIBS})

install(TARGETS magic_geo_native LIBRARY DESTINATION magic_geo)
