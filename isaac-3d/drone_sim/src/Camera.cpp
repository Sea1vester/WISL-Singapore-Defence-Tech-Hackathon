#include "Camera.h"
#include <glm/gtc/matrix_transform.hpp>
#include <algorithm>

Camera::Camera() { updateVectors(); }

void Camera::updateVectors() {
    glm::vec3 f;
    f.x = cos(glm::radians(yaw)) * cos(glm::radians(pitch));
    f.y = sin(glm::radians(pitch));
    f.z = sin(glm::radians(yaw)) * cos(glm::radians(pitch));
    front = glm::normalize(f);
    right = glm::normalize(glm::cross(front, worldUp));
    up = glm::normalize(glm::cross(right, front));
}

glm::mat4 Camera::viewMatrix() const {
    return glm::lookAt(position, position + front, up);
}

void Camera::processKeyboard(CameraMovement dir, float deltaTime) {
    float velocity = moveSpeed * deltaTime;
    switch (dir) {
        case CameraMovement::FORWARD:  position += front * velocity; break;
        case CameraMovement::BACKWARD: position -= front * velocity; break;
        case CameraMovement::LEFT:     position -= right * velocity; break;
        case CameraMovement::RIGHT:    position += right * velocity; break;
        case CameraMovement::UP:       position += worldUp * velocity; break;
        case CameraMovement::DOWN:     position -= worldUp * velocity; break;
    }
}

void Camera::processMouseDelta(float dx, float dy, bool constrainPitch) {
    yaw += dx * mouseSensitivity;
    pitch += dy * mouseSensitivity;
    if (constrainPitch) {
        pitch = std::clamp(pitch, -89.0f, 89.0f);
    }
    updateVectors();
}

void Camera::processScroll(float yoffset) {
    fovDegrees -= yoffset * 2.0f;
    fovDegrees = std::clamp(fovDegrees, 10.0f, 90.0f);
}

void Camera::followTarget(const glm::vec3& targetPos, float distance, float heightOffset, float orbitYawDeg) {
    float rad = glm::radians(orbitYawDeg);
    glm::vec3 offset(std::sin(rad) * distance, heightOffset, std::cos(rad) * distance);
    position = targetPos + offset;
    front = glm::normalize(targetPos - position);
    pitch = glm::degrees(std::asin(front.y));
    yaw = glm::degrees(std::atan2(front.z, front.x));
    right = glm::normalize(glm::cross(front, worldUp));
    up = glm::normalize(glm::cross(right, front));
}
