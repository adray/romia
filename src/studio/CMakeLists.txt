
# Studio

cmake_minimum_required (VERSION 3.8)

set (SOURCES
    "roStudio.h"
    "roStudio.cpp"
    "roServer.h"
    "roServer.cpp"
    "../sun/Sun.h"
    "../sun/Sun.cpp"
    "../sun/SunScript.h"
    "../sun/SunScript.cpp"
    "../sun/SunJIT.h"
    "../sun/SunJIT.cpp"
    "../sun/SunOpt.h"
    "../sun/SunOpt.cpp"
)

project ("studio")

# Add source to this project's executable.
add_executable(studio ${SOURCES})

include_directories ("../sun")
include_directories ("../cpp-httplib-0.54.1")
include_directories ("../json")

if (CMAKE_VERSION VERSION_GREATER 3.12)
  set_property(TARGET studio PROPERTY CXX_STANDARD 20)
endif()




