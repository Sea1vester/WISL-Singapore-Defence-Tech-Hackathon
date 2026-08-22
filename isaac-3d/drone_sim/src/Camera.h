#pragma once
#include <glm/glm.hpp>

enum class CameraMovement { FORWARD, BACKWARD, LEFT, RIGHT, UP, DOWN };

// A free-fly ("noclip") camera: WASD to move, mouse to look, scroll to zoom.
// Also supports an optional "orbit/follow" target (e.g. the UAV) via
// setFollowTarget(), toggled at the call site.
class Camera {
public:
    glm::vec3 position{0.0f, 30.0f, 60.0f};
    glm::vec3 front{0.0f, 0.0f, -1.0f};
    glm::vec3 up{0.0f, 1.0f, 0.0f};
    glm::vec3 right{1.0f, 0.0f, 0.0f};
    glm::vec3 worldUp{0.0f, 1.0f, 0.0f};

    float yaw = -90.0f;   // facing -Z initially
    float pitch = -15.0f;

    float moveSpeed = 20.0f;      // world units / second
    float mouseSensitivity = 0.12f;
    float fovDegrees = 60.0f;

    Camera();

    glm::mat4 viewMatrix() const;

    void processKeyboard(CameraMovement dir, float deltaTime);
    void processMouseDelta(float dx, float dy, bool constrainPitch = true);
    void processScroll(float yoffset);

    // Optional: fly-behind/orbit follow of a moving target (e.g. the UAV).
    // Call each frame instead of processKeyboard while `following` is true.
    void followTarget(const glm::vec3& targetPos, float distance, float heightOffset, float orbitYawDeg);

private:
    void updateVectors();
};
