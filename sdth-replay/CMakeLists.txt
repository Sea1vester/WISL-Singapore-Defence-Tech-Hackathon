cmake_minimum_required(VERSION 3.21)
project(sdth_replay VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(FetchContent)

option(SDTH_REPLAY_BUILD_APP "Build the raylib replay application" ON)

FetchContent_Declare(
  nlohmann_json
  GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG v3.11.3
  GIT_SHALLOW TRUE
)
FetchContent_MakeAvailable(nlohmann_json)

add_library(sdth_replay_core
  src/core.cpp
)
target_include_directories(sdth_replay_core PUBLIC include)
target_link_libraries(sdth_replay_core PUBLIC nlohmann_json::nlohmann_json)
target_compile_options(sdth_replay_core PRIVATE
  $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall;-Wextra;-Wpedantic>
)

if(SDTH_REPLAY_BUILD_APP)
  set(BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
  set(BUILD_GAMES OFF CACHE BOOL "" FORCE)
  FetchContent_Declare(
    raylib
    GIT_REPOSITORY https://github.com/raysan5/raylib.git
    GIT_TAG 5.5
    GIT_SHALLOW TRUE
  )
  FetchContent_Declare(
    httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG v0.18.3
    GIT_SHALLOW TRUE
  )
  FetchContent_MakeAvailable(raylib httplib)

  add_executable(sdth-replay
    src/main.cpp
  )
  target_link_libraries(sdth-replay PRIVATE
    sdth_replay_core
    raylib
    httplib::httplib
  )
  target_compile_definitions(sdth-replay PRIVATE
    SDTH_REPLAY_ASSET_DIR="${CMAKE_CURRENT_SOURCE_DIR}/assets"
  )
  if(APPLE)
    target_link_libraries(sdth-replay PRIVATE
      "-framework IOKit"
      "-framework Cocoa"
      "-framework OpenGL"
    )
  endif()
endif()

include(CTest)
if(BUILD_TESTING)
  add_executable(sdth_replay_tests tests/test_core.cpp)
  target_link_libraries(sdth_replay_tests PRIVATE sdth_replay_core)
  add_test(NAME sdth_replay_core_tests COMMAND sdth_replay_tests)
endif()
