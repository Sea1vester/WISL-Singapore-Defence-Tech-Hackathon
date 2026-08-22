#pragma once
#include <GL/glew.h>
#include <glm/glm.hpp>
#include <vector>
#include <string>
#include "GeoUtils.h"
#include "Shader.h"

// Renders a terrain mesh generated from a heightmap.
//
// Import formats supported:
//   - Binary PGM (P5) grayscale heightmap: trivial to produce from a real
//     DEM/GeoTIFF (e.g. SRTM tiles) with:
//       gdal_translate -of PGM -ot Byte -scale input.tif heightmap.pgm
//     or in Python:  Image.fromarray(dem_array).convert('L').save('h.pgm')
//   - If no file is given / file missing, falls back to procedural
//     fractal (midpoint-displacement) terrain so the app still runs.
//
// The heightmap's real-world footprint is defined by `worldSizeMeters`
// (edge length) and `maxHeightMeters` (grayscale 0..255 -> 0..maxHeight),
// and it is centered on the scene's GeoOrigin so it lines up with any
// GPS-derived flight path rendered via GeoUtils.
class Terrain {
public:
    Terrain(const std::string& heightmapPath,
            float worldSizeMeters,
            float maxHeightMeters,
            int fallbackGridResolution = 256);
    ~Terrain();

    Terrain(const Terrain&) = delete;
    Terrain& operator=(const Terrain&) = delete;

    void draw(const Shader& shader) const;

    // Sample terrain height (world Y, meters) at a given world (X,Z).
    // Useful for clamping the camera or UAV above ground level.
    float heightAt(float worldX, float worldZ) const;

    float worldSize() const { return worldSizeMeters_; }

private:
    void buildMeshFromHeights(const std::vector<float>& heights, int gridW, int gridH);
    bool loadPGM(const std::string& path, std::vector<float>& outHeights, int& w, int& h) const;
    void generateFractal(std::vector<float>& outHeights, int resolution) const;

    GLuint vao_ = 0, vbo_ = 0, ebo_ = 0;
    GLsizei indexCount_ = 0;

    float worldSizeMeters_;
    float maxHeightMeters_;
    int gridW_ = 0, gridH_ = 0;
    std::vector<float> heightSamples_; // normalized 0..1, row-major, size gridW_*gridH_
};
