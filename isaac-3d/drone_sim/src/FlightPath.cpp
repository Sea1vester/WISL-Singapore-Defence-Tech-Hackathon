#include "FlightPath.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>
#include <cmath>

namespace {
std::vector<std::string> splitCSVLine(const std::string& line) {
    std::vector<std::string> out;
    std::stringstream ss(line);
    std::string field;
    while (std::getline(ss, field, ',')) out.push_back(field);
    return out;
}
}

bool FlightPath::loadCSV(const std::string& path, const GeoOrigin& origin) {
    samples_.clear();
    std::ifstream f(path);
    if (!f.is_open()) {
        std::cerr << "FlightPath: could not open " << path << std::endl;
        return false;
    }

    std::string headerLine;
    if (!std::getline(f, headerLine)) return false;
    auto header = splitCSVLine(headerLine);
    for (auto& h : header) {
        h.erase(std::remove_if(h.begin(), h.end(), [](unsigned char c){ return std::isspace(c); }), h.end());
    }

    int tIdx = -1, northIdx = -1, eastIdx = -1, upIdx = -1;
    int latIdx = -1, lonIdx = -1, altIdx = -1;
    for (size_t i = 0; i < header.size(); ++i) {
        if (header[i] == "t_sec" || header[i] == "t") tIdx = (int)i;
        else if (header[i] == "north") northIdx = (int)i;
        else if (header[i] == "east") eastIdx = (int)i;
        else if (header[i] == "up") upIdx = (int)i;
        else if (header[i] == "lat") latIdx = (int)i;
        else if (header[i] == "lon") lonIdx = (int)i;
        else if (header[i] == "alt") altIdx = (int)i;
    }

    bool useENU = (northIdx >= 0 && eastIdx >= 0 && upIdx >= 0);
    bool useGPS = (latIdx >= 0 && lonIdx >= 0 && altIdx >= 0);

    if (tIdx < 0 || (!useENU && !useGPS)) {
        std::cerr << "FlightPath: CSV header must contain t_sec + (north,east,up) or (lat,lon,alt)\n";
        return false;
    }

    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        auto fields = splitCSVLine(line);
        if (fields.size() < header.size()) continue;

        try {
            float t = std::stof(fields[tIdx]);
            glm::vec3 world;
            if (useENU) {
                glm::vec3 enu(std::stof(fields[eastIdx]), std::stof(fields[northIdx]), std::stof(fields[upIdx]));
                world = GeoUtils::enuToWorld(enu);
            } else {
                double lat = std::stod(fields[latIdx]);
                double lon = std::stod(fields[lonIdx]);
                double alt = std::stod(fields[altIdx]);
                world = GeoUtils::gpsToWorld(lat, lon, alt, origin);
            }
            samples_.push_back({t, world});
        } catch (const std::exception&) {
            continue; // skip malformed rows
        }
    }

    std::sort(samples_.begin(), samples_.end(),
              [](const Sample& a, const Sample& b) { return a.tSec < b.tSec; });

    std::cout << "FlightPath: loaded " << samples_.size() << " samples from " << path
              << " (duration " << duration() << "s)" << std::endl;
    return !samples_.empty();
}

glm::vec3 FlightPath::positionAt(float tSec) const {
    if (samples_.empty()) return glm::vec3(0.0f);
    if (tSec <= samples_.front().tSec) return samples_.front().worldPos;
    if (tSec >= samples_.back().tSec) return samples_.back().worldPos;

    // Binary search for the bracketing pair
    auto it = std::lower_bound(samples_.begin(), samples_.end(), tSec,
        [](const Sample& s, float t) { return s.tSec < t; });
    size_t i1 = std::distance(samples_.begin(), it);
    size_t i0 = i1 > 0 ? i1 - 1 : 0;

    const Sample& a = samples_[i0];
    const Sample& b = samples_[i1];
    float span = b.tSec - a.tSec;
    float alpha = span > 1e-6f ? (tSec - a.tSec) / span : 0.0f;
    return glm::mix(a.worldPos, b.worldPos, alpha);
}

float FlightPath::headingAt(float tSec) const {
    const float dt = 0.05f;
    glm::vec3 p0 = positionAt(std::max(tSec - dt, samples_.empty() ? 0.0f : samples_.front().tSec));
    glm::vec3 p1 = positionAt(std::min(tSec + dt, samples_.empty() ? 0.0f : samples_.back().tSec));
    glm::vec3 dir = p1 - p0;
    if (glm::length(glm::vec2(dir.x, dir.z)) < 1e-4f) return 0.0f;
    // World X=East, Z=-North. Heading 0 = facing +X (East).
    return glm::degrees(std::atan2(-dir.z, dir.x));
}
