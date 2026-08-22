#pragma once
#include <GL/glew.h>
#include <glm/glm.hpp>
#include <vector>
#include "Shader.h"

// A small procedural quadcopter mesh (body cuboid + 4 arms + 4 rotor discs),
// generated in code so no external model files/importers are needed.
//
// Orientation convention: roll/pitch/yaw in degrees, aircraft convention,
// applied in world space (X=East, Y=Up, Z=-North; see GeoUtils.h):
//   yaw   - rotation about world Y (heading, 0 = facing +X/East)
//   pitch - rotation about the body's right axis (nose up/down)
//   roll  - rotation about the body's forward axis (bank left/right)
class UAV {
public:
    UAV(float bodySize = 1.0f, float armLength = 1.4f);
    ~UAV();

    UAV(const UAV&) = delete;
    UAV& operator=(const UAV&) = delete;

    void setPose(const glm::vec3& worldPosition, float yawDeg, float pitchDeg, float rollDeg);
    glm::mat4 modelMatrix() const;

    void draw(const Shader& shader) const;

    // --- Flight trail (breadcrumb line of past positions) ---
    void pushTrailPoint(const glm::vec3& worldPosition);
    void drawTrail(const Shader& lineShader) const;
    void clearTrail();

    glm::vec3 position() const { return position_; }

private:
    void buildMesh();
    void uploadTrail() const;

    // Body/rotor mesh
    GLuint vao_ = 0, vbo_ = 0;
    GLsizei vertexCount_ = 0;

    // Trail line
    mutable GLuint trailVao_ = 0, trailVbo_ = 0;
    mutable bool trailDirty_ = true;
    std::vector<glm::vec3> trailPoints_;
    size_t maxTrailPoints_ = 20000;

    glm::vec3 position_{0.0f};
    float yawDeg_ = 0.0f, pitchDeg_ = 0.0f, rollDeg_ = 0.0f;

    float bodySize_;
    float armLength_;
};
