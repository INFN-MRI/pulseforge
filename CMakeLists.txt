cmake_minimum_required(VERSION 3.18)
project(pulserver_extensions LANGUAGES C CXX)

set(CMAKE_C_STANDARD 90)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

find_package(pybind11 CONFIG REQUIRED)
find_package(Python COMPONENTS Development.Module REQUIRED)

# The scanner compiles src/c as ANSI C: a construct C89 rejects fails this
# build too, before it can reach the interpreter.
add_compile_options($<$<COMPILE_LANGUAGE:C>:-pedantic-errors>)

add_subdirectory(${CMAKE_SOURCE_DIR}/src/c ${CMAKE_BINARY_DIR}/c_build)

pybind11_add_module(_ext
    ${CMAKE_SOURCE_DIR}/src/cpp/module.cpp
    ${CMAKE_SOURCE_DIR}/src/cpp/ir/from_libraries.cpp
)
target_link_libraries(_ext PRIVATE pulseg)

# Built into the build tree, never beside the sources: a binary left in the
# source tree would be swept into wheels built for other interpreters.
set_target_properties(_ext PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/src/pulserver"
)

install(TARGETS _ext DESTINATION pulserver)
