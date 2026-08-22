// Drone Flight Simulator / Log Visualizer
// ------------------------------------------------------------------
// Controls:
//   W A S D        - move camera (fly mode)
//   Space / Ctrl   - move camera up / down
//   Mouse          - look around (click window to capture cursor)
//   Scroll         - zoom (change FOV)
//   F              - toggle follow-cam (orbits the UAV)
//   P              - play/pause flight path playback
//   R              - restart playback from t=0
//   ESC            - release mouse cursor / quit (press again to quit)
//
// This program renders:
//   1. A terrain mesh (from a heightmap image, or procedural fallback)
//   2. A procedural UAV model
//   3. A flight path loaded from CSV (see FlightPath.h for format),
//      typically produced by the companion ulg_3d_flightpath.py script
//      from a PX4 .ulg log.
//
// If no flightpath.csv is present, the UAV instead flies a demo circular
// orbit so you can see the whole system working end to end.
// ------------------------------------------------------------------

#include <GL/glew.h>
#include <GLFW/glfw3.h>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <iostream>
#include <cmath>

#include "Shader.h"
#include "Camera.h"
#include "Terrain.h"
#include "UAV.h"
#include "GeoUtils.h"
#include "FlightPath.h"

// ---------------------------------------------------------------------
// Scene configuration
// ---------------------------------------------------------------------
static const int kWindowWidth = 1280;
static const int kWindowHeight = 720;

static const float kTerrainWorldSize = 2000.0f; // meters, edge length
static const float kTerrainMaxHeight = 250.0f;  // meters

// Anchor GPS coordinate for the scene (edit to match your log's takeoff
// location, or leave as-is if you're only using local ENU data).
static GeoOrigin g_geoOrigin{47.397742, 8.545594, 488.0}; // example: PX4 SITL default (Zurich)

// ---------------------------------------------------------------------
// Globals for input callbacks (kept minimal/simple for a single-window app)
// ---------------------------------------------------------------------
static Camera g_camera;
static bool g_firstMouse = true;
static float g_lastX = kWindowWidth / 2.0f, g_lastY = kWindowHeight / 2.0f;
static bool g_cursorCaptured = true;
static bool g_followCam = false;
static bool g_playing = true;
static float g_playbackTime = 0.0f;

void framebufferSizeCallback(GLFWwindow*, int width, int height) {
    glViewport(0, 0, width, height);
}

void mouseCallback(GLFWwindow*, double xpos, double ypos) {
    if (!g_cursorCaptured) return;
    if (g_firstMouse) {
        g_lastX = (float)xpos;
        g_lastY = (float)ypos;
        g_firstMouse = false;
    }
    float dx = (float)xpos - g_lastX;
    float dy = g_lastY - (float)ypos; // reversed: y goes down on screen
    g_lastX = (float)xpos;
    g_lastY = (float)ypos;
    g_camera.processMouseDelta(dx, dy);
}

void scrollCallback(GLFWwindow*, double, double yoffset) {
    g_camera.processScroll((float)yoffset);
}

void keyCallback(GLFWwindow* window, int key, int, int action, int) {
    if (action != GLFW_PRESS) return;
    if (key == GLFW_KEY_ESCAPE) {
        g_cursorCaptured = !g_cursorCaptured;
        glfwSetInputMode(window, GLFW_CURSOR,
                          g_cursorCaptured ? GLFW_CURSOR_DISABLED : GLFW_CURSOR_NORMAL);
        g_firstMouse = true;
    } else if (key == GLFW_KEY_F) {
        g_followCam = !g_followCam;
    } else if (key == GLFW_KEY_P) {
        g_playing = !g_playing;
    } else if (key == GLFW_KEY_R) {
        g_playbackTime = 0.0f;
    }
}

void processMovementInput(GLFWwindow* window, float dt) {
    if (glfwGetKey(window, GLFW_KEY_W) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::FORWARD, dt);
    if (glfwGetKey(window, GLFW_KEY_S) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::BACKWARD, dt);
    if (glfwGetKey(window, GLFW_KEY_A) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::LEFT, dt);
    if (glfwGetKey(window, GLFW_KEY_D) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::RIGHT, dt);
    if (glfwGetKey(window, GLFW_KEY_SPACE) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::UP, dt);
    if (glfwGetKey(window, GLFW_KEY_LEFT_CONTROL) == GLFW_PRESS) g_camera.processKeyboard(CameraMovement::DOWN, dt);
}

int main(int argc, char** argv) {
    // Optional CLI arg: path to a flight path CSV (see FlightPath.h)
    std::string flightPathCsv = (argc > 1) ? argv[1] : "assets/flightpath.csv";
    std::string heightmapPath = (argc > 2) ? argv[2] : "assets/heightmap.pgm";

    // --- GLFW / GL context setup ---
    if (!glfwInit()) {
        std::cerr << "Failed to initialize GLFW\n";
        return -1;
    }
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
#ifdef __APPLE__
    glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GL_TRUE);
#endif

    GLFWwindow* window = glfwCreateWindow(kWindowWidth, kWindowHeight,
                                           "Drone Flight Simulator", nullptr, nullptr);
    if (!window) {
        std::cerr << "Failed to create GLFW window\n";
        glfwTerminate();
        return -1;
    }
    glfwMakeContextCurrent(window);
    glfwSetFramebufferSizeCallback(window, framebufferSizeCallback);
    glfwSetCursorPosCallback(window, mouseCallback);
    glfwSetScrollCallback(window, scrollCallback);
    glfwSetKeyCallback(window, keyCallback);
    glfwSetInputMode(window, GLFW_CURSOR, GLFW_CURSOR_DISABLED);

    glewExperimental = GL_TRUE;
    if (glewInit() != GLEW_OK) {
        std::cerr << "Failed to initialize GLEW\n";
        return -1;
    }

    glEnable(GL_DEPTH_TEST);
    glClearColor(0.53f, 0.75f, 0.92f, 1.0f); // sky blue

    // --- Load shaders ---
    Shader terrainShader, uavShader, lineShader;
    try {
        terrainShader = Shader("shaders/terrain.vert", "shaders/terrain.frag");
        uavShader = Shader("shaders/basic.vert", "shaders/basic.frag");
        lineShader = Shader("shaders/line.vert", "shaders/line.frag");
    } catch (const std::exception& e) {
        std::cerr << "Shader error: " << e.what() << std::endl;
        return -1;
    }

    // --- World content ---
    Terrain terrain(heightmapPath, kTerrainWorldSize, kTerrainMaxHeight);
    UAV uav(2.0f, 2.5f);

    FlightPath flightPath;
    bool haveRealPath = flightPath.loadCSV(flightPathCsv, g_geoOrigin);
    if (!haveRealPath) {
        std::cout << "No flight path CSV found at '" << flightPathCsv
                  << "' - flying a demo orbit instead.\n"
                  << "(Export one from your .ulg via the Python script; see FlightPath.h)\n";
    }

    float lastFrameTime = (float)glfwGetTime();

    while (!glfwWindowShouldClose(window)) {
        float now = (float)glfwGetTime();
        float dt = now - lastFrameTime;
        lastFrameTime = now;

        glfwPollEvents();
        if (!g_followCam) processMovementInput(window, dt);
        if (glfwGetKey(window, GLFW_KEY_Q) == GLFW_PRESS) glfwSetWindowShouldClose(window, true);

        // --- Update UAV pose ---
        glm::vec3 uavWorldPos;
        float headingDeg;
        if (haveRealPath) {
            if (g_playing) {
                g_playbackTime += dt;
                if (g_playbackTime > flightPath.duration()) g_playbackTime = 0.0f; // loop
            }
            uavWorldPos = flightPath.positionAt(g_playbackTime);
            headingDeg = flightPath.headingAt(g_playbackTime);
        } else {
            // Demo circular orbit so the app is meaningful with no data loaded
            if (g_playing) g_playbackTime += dt;
            float radius = 150.0f;
            float angularSpeed = 0.3f; // rad/s
            float a = g_playbackTime * angularSpeed;
            float groundY = terrain.heightAt(std::cos(a) * radius, std::sin(a) * radius);
            uavWorldPos = glm::vec3(std::cos(a) * radius, groundY + 40.0f, std::sin(a) * radius);
            headingDeg = glm::degrees(a) + 90.0f;
        }
        uav.setPose(uavWorldPos, headingDeg, 0.0f, 0.0f);
        uav.pushTrailPoint(uavWorldPos);

        if (g_followCam) {
            static float orbitYaw = 0.0f;
            orbitYaw += dt * 15.0f; // slow auto-orbit; replace with mouse-driven angle if desired
            g_camera.followTarget(uavWorldPos, 25.0f, 12.0f, orbitYaw);
        }

        // --- Render ---
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

        int fbW, fbH;
        glfwGetFramebufferSize(window, &fbW, &fbH);
        glm::mat4 projection = glm::perspective(glm::radians(g_camera.fovDegrees),
                                                 (float)fbW / (float)std::max(fbH, 1),
                                                 0.1f, 5000.0f);
        glm::mat4 view = g_camera.viewMatrix();

        terrainShader.use();
        terrainShader.setMat4("view", view);
        terrainShader.setMat4("projection", projection);
        terrainShader.setVec3("lightDir", glm::normalize(glm::vec3(-0.4f, -1.0f, -0.3f)));
        terrainShader.setFloat("maxHeight", kTerrainMaxHeight);
        terrain.draw(terrainShader);

        uavShader.use();
        uavShader.setMat4("view", view);
        uavShader.setMat4("projection", projection);
        uav.draw(uavShader);

        lineShader.use();
        lineShader.setMat4("view", view);
        lineShader.setMat4("projection", projection);
        lineShader.setVec3("lineColor", glm::vec3(1.0f, 0.85f, 0.1f));
        uav.drawTrail(lineShader);

        glfwSwapBuffers(window);
    }

    glfwTerminate();
    return 0;
}
