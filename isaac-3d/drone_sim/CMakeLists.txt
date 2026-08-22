cmake_minimum_required(VERSION 3.16)
project(DroneFlightSim CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ---------------------------------------------------------------------------
# Dependencies
#   Ubuntu/Debian:  sudo apt install libglfw3-dev libglew-dev libglm-dev
#   macOS (brew):   brew install glfw glew glm
#   Windows:        vcpkg install glfw3 glew glm
# ---------------------------------------------------------------------------
find_package(OpenGL REQUIRED)
find_package(glfw3 REQUIRED)
find_package(GLEW REQUIRED)
find_package(glm REQUIRED)

add_executable(drone_sim
    src/main.cpp
    src/Shader.cpp
    src/Camera.cpp
    src/Terrain.cpp
    src/UAV.cpp
    src/GeoUtils.cpp
    src/FlightPath.cpp
)

target_include_directories(drone_sim PRIVATE src)
target_link_libraries(drone_sim PRIVATE OpenGL::GL glfw GLEW::GLEW)

# Copy shaders/assets next to the built binary so relative paths resolve
add_custom_command(TARGET drone_sim POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${CMAKE_SOURCE_DIR}/shaders $<TARGET_FILE_DIR:drone_sim>/shaders
    COMMAND ${CMAKE_COMMAND} -E copy_directory
            ${CMAKE_SOURCE_DIR}/assets $<TARGET_FILE_DIR:drone_sim>/assets
)
