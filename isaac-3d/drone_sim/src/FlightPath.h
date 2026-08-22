#pragma once
#include <glm/glm.hpp>
#include <vector>
#include <string>
#include "GeoUtils.h"

// Loads a flight trajectory from CSV and provides time-based playback,
// meant to be fed by the companion Python script (ulg_3d_flightpath.py)
// which extracts position data from PX4 .ulg logs.
//
// Expected CSV header (either form works):
//   t_sec,north,east,up            (local ENU meters, e.g. from vehicle_local_position)
//   t_sec,lat,lon,alt              (WGS84 GPS, converted via GeoOrigin)
//
// A helper to export this from the earlier Python script:
//   np.savetxt("flightpath.csv",
//              np.column_stack([traj["t_sec"], traj["north"], traj["east"], traj["up"]]),
//              header="t_sec,north,east,up", delimiter=",", comments="")
class FlightPath {
public:
    struct Sample {
        float tSec;
        glm::vec3 worldPos; // already converted to OpenGL world space
    };

    // Returns false (and leaves the path empty) if the file can't be read/parsed.
    bool loadCSV(const std::string& path, const GeoOrigin& origin);

    bool empty() const { return samples_.empty(); }
    float duration() const { return samples_.empty() ? 0.0f : samples_.back().tSec; }

    // Interpolated world-space position and heading (degrees) at time t.
    // Heading is derived from the direction of travel between samples.
    glm::vec3 positionAt(float tSec) const;
    float headingAt(float tSec) const;

    const std::vector<Sample>& samples() const { return samples_; }

private:
    std::vector<Sample> samples_;
};
