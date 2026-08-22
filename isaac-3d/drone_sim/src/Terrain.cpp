#include "Terrain.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <cstdlib>
#include <algorithm>
#include <random>

Terrain::Terrain(const std::string& heightmapPath, float worldSizeMeters,
                  float maxHeightMeters, int fallbackGridResolution)
    : worldSizeMeters_(worldSizeMeters), maxHeightMeters_(maxHeightMeters) {

    std::vector<float> heights; // normalized 0..1
    int w = 0, h = 0;

    if (!heightmapPath.empty() && loadPGM(heightmapPath, heights, w, h)) {
        std::cout << "Terrain: loaded heightmap '" << heightmapPath
                  << "' (" << w << "x" << h << ")" << std::endl;
    } else {
        std::cout << "Terrain: no valid heightmap at '" << heightmapPath
                  << "', generating procedural fractal terrain instead." << std::endl;
        w = h = fallbackGridResolution;
        generateFractal(heights, fallbackGridResolution);
    }

    gridW_ = w;
    gridH_ = h;
    heightSamples_ = heights;

    buildMeshFromHeights(heights, w, h);
}

Terrain::~Terrain() {
    if (ebo_) glDeleteBuffers(1, &ebo_);
    if (vbo_) glDeleteBuffers(1, &vbo_);
    if (vao_) glDeleteVertexArrays(1, &vao_);
}

// --- PGM (binary P5) loader -------------------------------------------------
bool Terrain::loadPGM(const std::string& path, std::vector<float>& outHeights,
                       int& w, int& h) const {
    std::ifstream f(path, std::ios::binary);
    if (!f.is_open()) return false;

    std::string magic;
    f >> magic;
    if (magic != "P5") {
        std::cerr << "Terrain: '" << path << "' is not a binary PGM (P5)" << std::endl;
        return false;
    }

    auto skipWhitespaceAndComments = [&]() {
        char c;
        while (f.get(c)) {
            if (c == '#') { std::string dummy; std::getline(f, dummy); }
            else if (!std::isspace(static_cast<unsigned char>(c))) { f.unget(); break; }
        }
    };

    int maxVal = 255;
    skipWhitespaceAndComments(); f >> w;
    skipWhitespaceAndComments(); f >> h;
    skipWhitespaceAndComments(); f >> maxVal;
    f.get(); // consume single whitespace byte after maxval

    if (w <= 0 || h <= 0) return false;

    std::vector<unsigned char> raw(static_cast<size_t>(w) * h);
    f.read(reinterpret_cast<char*>(raw.data()), raw.size());
    if (!f) {
        std::cerr << "Terrain: unexpected EOF reading pixel data in " << path << std::endl;
        return false;
    }

    outHeights.resize(raw.size());
    for (size_t i = 0; i < raw.size(); ++i) {
        outHeights[i] = static_cast<float>(raw[i]) / static_cast<float>(maxVal);
    }
    return true;
}

// --- Procedural fallback: midpoint displacement / diamond-square-ish -------
void Terrain::generateFractal(std::vector<float>& outHeights, int resolution) const {
    // Simple layered-noise fallback (sum of sines + randomness), deterministic
    // seed so re-runs are reproducible. Good enough as a placeholder world
    // when no real heightmap is supplied.
    outHeights.assign(static_cast<size_t>(resolution) * resolution, 0.0f);
    std::mt19937 rng(1234);
    std::uniform_real_distribution<float> phase(0.0f, 6.2831853f);
    float p1 = phase(rng), p2 = phase(rng), p3 = phase(rng);

    for (int y = 0; y < resolution; ++y) {
        for (int x = 0; x < resolution; ++x) {
            float u = static_cast<float>(x) / resolution;
            float v = static_cast<float>(y) / resolution;
            float val = 0.5f
                + 0.25f * std::sin(u * 6.0f + p1) * std::cos(v * 6.0f + p2)
                + 0.15f * std::sin((u + v) * 10.0f + p3)
                + 0.10f * std::sin(u * 23.0f) * std::sin(v * 19.0f);
            outHeights[y * resolution + x] = std::clamp(val, 0.0f, 1.0f);
        }
    }
}

// --- Mesh building -----------------------------------------------------
void Terrain::buildMeshFromHeights(const std::vector<float>& heights, int gridW, int gridH) {
    struct Vertex {
        glm::vec3 position;
        glm::vec3 normal;
    };

    std::vector<Vertex> vertices(static_cast<size_t>(gridW) * gridH);

    // Vertex positions: mesh spans [-worldSize/2, +worldSize/2] on X and Z,
    // centered on the scene's GeoOrigin. Y = height * maxHeightMeters.
    for (int z = 0; z < gridH; ++z) {
        for (int x = 0; x < gridW; ++x) {
            float u = static_cast<float>(x) / (gridW - 1);
            float v = static_cast<float>(z) / (gridH - 1);
            float worldX = (u - 0.5f) * worldSizeMeters_;
            float worldZ = (v - 0.5f) * worldSizeMeters_;
            float worldY = heights[z * gridW + x] * maxHeightMeters_;
            vertices[z * gridW + x].position = glm::vec3(worldX, worldY, worldZ);
        }
    }

    // Compute smooth normals via central differences on the height grid.
    float dx = worldSizeMeters_ / (gridW - 1);
    float dz = worldSizeMeters_ / (gridH - 1);
    for (int z = 0; z < gridH; ++z) {
        for (int x = 0; x < gridW; ++x) {
            float hL = heights[z * gridW + std::max(x - 1, 0)] * maxHeightMeters_;
            float hR = heights[z * gridW + std::min(x + 1, gridW - 1)] * maxHeightMeters_;
            float hD = heights[std::max(z - 1, 0) * gridW + x] * maxHeightMeters_;
            float hU = heights[std::min(z + 1, gridH - 1) * gridW + x] * maxHeightMeters_;
            glm::vec3 n = glm::normalize(glm::vec3(-(hR - hL) / (2 * dx), 2.0f, -(hU - hD) / (2 * dz)));
            vertices[z * gridW + x].normal = n;
        }
    }

    std::vector<unsigned int> indices;
    indices.reserve(static_cast<size_t>(gridW - 1) * (gridH - 1) * 6);
    for (int z = 0; z < gridH - 1; ++z) {
        for (int x = 0; x < gridW - 1; ++x) {
            unsigned int i0 = z * gridW + x;
            unsigned int i1 = z * gridW + (x + 1);
            unsigned int i2 = (z + 1) * gridW + x;
            unsigned int i3 = (z + 1) * gridW + (x + 1);
            indices.insert(indices.end(), {i0, i2, i1, i1, i2, i3});
        }
    }
    indexCount_ = static_cast<GLsizei>(indices.size());

    glGenVertexArrays(1, &vao_);
    glGenBuffers(1, &vbo_);
    glGenBuffers(1, &ebo_);

    glBindVertexArray(vao_);

    glBindBuffer(GL_ARRAY_BUFFER, vbo_);
    glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(Vertex), vertices.data(), GL_STATIC_DRAW);

    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo_);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.size() * sizeof(unsigned int), indices.data(), GL_STATIC_DRAW);

    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, position));
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, normal));

    glBindVertexArray(0);
}

void Terrain::draw(const Shader& shader) const {
    shader.use();
    glBindVertexArray(vao_);
    glDrawElements(GL_TRIANGLES, indexCount_, GL_UNSIGNED_INT, nullptr);
    glBindVertexArray(0);
}

float Terrain::heightAt(float worldX, float worldZ) const {
    if (heightSamples_.empty()) return 0.0f;

    float u = (worldX / worldSizeMeters_) + 0.5f;
    float v = (worldZ / worldSizeMeters_) + 0.5f;
    u = std::clamp(u, 0.0f, 1.0f);
    v = std::clamp(v, 0.0f, 1.0f);

    float fx = u * (gridW_ - 1);
    float fz = v * (gridH_ - 1);
    int x0 = static_cast<int>(fx), z0 = static_cast<int>(fz);
    int x1 = std::min(x0 + 1, gridW_ - 1);
    int z1 = std::min(z0 + 1, gridH_ - 1);
    float tx = fx - x0, tz = fz - z0;

    auto h = [&](int x, int z) { return heightSamples_[z * gridW_ + x] * maxHeightMeters_; };

    float h00 = h(x0, z0), h10 = h(x1, z0), h01 = h(x0, z1), h11 = h(x1, z1);
    float hTop = h00 * (1 - tx) + h10 * tx;
    float hBot = h01 * (1 - tx) + h11 * tx;
    return hTop * (1 - tz) + hBot * tz;
}
