#include "UAV.h"
#include <glm/gtc/matrix_transform.hpp>
#include <cmath>

namespace {
struct V { glm::vec3 pos; glm::vec3 color; };

void addBox(std::vector<V>& out, glm::vec3 center, glm::vec3 halfExtents, glm::vec3 color) {
    glm::vec3 c = center, e = halfExtents;
    glm::vec3 corners[8] = {
        {c.x-e.x,c.y-e.y,c.z-e.z}, {c.x+e.x,c.y-e.y,c.z-e.z},
        {c.x+e.x,c.y+e.y,c.z-e.z}, {c.x-e.x,c.y+e.y,c.z-e.z},
        {c.x-e.x,c.y-e.y,c.z+e.z}, {c.x+e.x,c.y-e.y,c.z+e.z},
        {c.x+e.x,c.y+e.y,c.z+e.z}, {c.x-e.x,c.y+e.y,c.z+e.z},
    };
    int faces[6][4] = {
        {0,1,2,3}, {5,4,7,6}, {4,0,3,7}, {1,5,6,2}, {3,2,6,7}, {4,5,1,0}
    };
    for (auto& f : faces) {
        V a{corners[f[0]], color}, b{corners[f[1]], color}, c2{corners[f[2]], color}, d{corners[f[3]], color};
        out.insert(out.end(), {a, b, c2, a, c2, d});
    }
}

// A flat disc approximating a spinning rotor, in the XZ plane at `center`.
void addDisc(std::vector<V>& out, glm::vec3 center, float radius, glm::vec3 color, int segments = 16) {
    for (int i = 0; i < segments; ++i) {
        float a0 = (float)i / segments * 6.2831853f;
        float a1 = (float)(i + 1) / segments * 6.2831853f;
        glm::vec3 p0 = center + glm::vec3(std::cos(a0) * radius, 0.0f, std::sin(a0) * radius);
        glm::vec3 p1 = center + glm::vec3(std::cos(a1) * radius, 0.0f, std::sin(a1) * radius);
        out.insert(out.end(), {V{center, color}, V{p0, color}, V{p1, color}});
    }
}
} // namespace

UAV::UAV(float bodySize, float armLength) : bodySize_(bodySize), armLength_(armLength) {
    buildMesh();
    glGenVertexArrays(1, &trailVao_);
    glGenBuffers(1, &trailVbo_);
}

UAV::~UAV() {
    if (vbo_) glDeleteBuffers(1, &vbo_);
    if (vao_) glDeleteVertexArrays(1, &vao_);
    if (trailVbo_) glDeleteBuffers(1, &trailVbo_);
    if (trailVao_) glDeleteVertexArrays(1, &trailVao_);
}

void UAV::buildMesh() {
    std::vector<V> verts;

    const glm::vec3 bodyColor(0.85f, 0.15f, 0.15f);
    const glm::vec3 armColor(0.2f, 0.2f, 0.2f);
    const glm::vec3 rotorColor(0.1f, 0.5f, 0.9f);
    const glm::vec3 noseColor(1.0f, 1.0f, 1.0f);

    // Central body
    addBox(verts, {0, 0, 0}, {bodySize_ * 0.5f, bodySize_ * 0.25f, bodySize_ * 0.5f}, bodyColor);
    // Nose marker (small white box at +X, i.e. forward/East when yaw=0)
    addBox(verts, {bodySize_ * 0.55f, 0, 0}, {bodySize_ * 0.12f, bodySize_ * 0.12f, bodySize_ * 0.12f}, noseColor);

    // Four arms at 45 degrees (X configuration) with rotor discs at the tips
    float armY = 0.0f;
    glm::vec2 dirs[4] = { {1, 1}, {1, -1}, {-1, -1}, {-1, 1} };
    for (auto d : dirs) {
        glm::vec2 dir = glm::normalize(d);
        glm::vec3 tip(dir.x * armLength_, armY, dir.y * armLength_);
        glm::vec3 mid = tip * 0.5f;
        glm::vec3 armHalfExtents(armLength_ * 0.5f * std::abs(dir.x) + 0.03f,
                                  0.04f,
                                  armLength_ * 0.5f * std::abs(dir.y) + 0.03f);
        addBox(verts, mid, armHalfExtents, armColor);
        addDisc(verts, tip + glm::vec3(0, 0.05f, 0), bodySize_ * 0.35f, rotorColor);
    }

    vertexCount_ = static_cast<GLsizei>(verts.size());

    glGenVertexArrays(1, &vao_);
    glGenBuffers(1, &vbo_);
    glBindVertexArray(vao_);
    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER, verts.size() * sizeof(V), verts.data(), GL_STATIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(V), (void*)offsetof(V, pos));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(V), (void*)offsetof(V, color));
    glBindVertexArray(0);
}

void UAV::setPose(const glm::vec3& worldPosition, float yawDeg, float pitchDeg, float rollDeg) {
    position_ = worldPosition;
    yawDeg_ = yawDeg;
    pitchDeg_ = pitchDeg;
    rollDeg_ = rollDeg;
}

glm::mat4 UAV::modelMatrix() const {
    glm::mat4 m(1.0f);
    m = glm::translate(m, position_);
    // Yaw about world up (Y), then pitch about local right (Z' after yaw... )
    // Simplified: apply yaw (Y), pitch (Z), roll (X) as successive intrinsic
    // rotations - sufficient fidelity for visualization purposes.
    m = glm::rotate(m, glm::radians(yawDeg_), glm::vec3(0, 1, 0));
    m = glm::rotate(m, glm::radians(pitchDeg_), glm::vec3(0, 0, 1));
    m = glm::rotate(m, glm::radians(rollDeg_), glm::vec3(1, 0, 0));
    return m;
}

void UAV::draw(const Shader& shader) const {
    shader.use();
    shader.setMat4("model", modelMatrix());
    glBindVertexArray(vao_);
    glDrawArrays(GL_TRIANGLES, 0, vertexCount_);
    glBindVertexArray(0);
}

void UAV::pushTrailPoint(const glm::vec3& worldPosition) {
    trailPoints_.push_back(worldPosition);
    if (trailPoints_.size() > maxTrailPoints_) {
        trailPoints_.erase(trailPoints_.begin());
    }
    trailDirty_ = true;
}

void UAV::clearTrail() {
    trailPoints_.clear();
    trailDirty_ = true;
}

void UAV::uploadTrail() const {
    glBindVertexArray(trailVao_);
    glBindBuffer(GL_ARRAY_BUFFER, trailVbo_);
    glBufferData(GL_ARRAY_BUFFER, trailPoints_.size() * sizeof(glm::vec3),
                 trailPoints_.data(), GL_DYNAMIC_DRAW);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(glm::vec3), (void*)0);
    glBindVertexArray(0);
    trailDirty_ = false;
}

void UAV::drawTrail(const Shader& lineShader) const {
    if (trailPoints_.size() < 2) return;
    if (trailDirty_) uploadTrail();

    lineShader.use();
    lineShader.setMat4("model", glm::mat4(1.0f));
    glBindVertexArray(trailVao_);
    glDrawArrays(GL_LINE_STRIP, 0, static_cast<GLsizei>(trailPoints_.size()));
    glBindVertexArray(0);
}
