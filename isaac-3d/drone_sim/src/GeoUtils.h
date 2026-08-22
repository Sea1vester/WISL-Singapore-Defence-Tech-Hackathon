#pragma once
#include <glm/glm.hpp>

// -----------------------------------------------------------------------
// Coordinate systems used in this project:
//
//   GPS (WGS84)   : latitude (deg), longitude (deg), altitude AMSL (m)
//   Local ENU     : East, North, Up, in meters, relative to a chosen
//                   geographic origin (the "geo-origin" of the scene).
//   World (OpenGL): right-handed, Y-up.  X = East, Y = Up, Z = -North.
//                   (Negating North->Z makes "forward/into the screen"
//                   correspond to increasing North when looking -Z, which
//                   matches the default OpenGL camera convention.)
//
// A single GeoOrigin anchors the whole scene: it's the GPS coordinate that
// maps to world-space (0,0,0). Terrain heightmaps and flight paths should
// all be converted through this same origin so they line up.
// -----------------------------------------------------------------------

struct GeoOrigin {
    double lat0 = 0.0;   // degrees
    double lon0 = 0.0;   // degrees
    double alt0 = 0.0;   // meters AMSL

    static constexpr double kEarthRadius = 6371000.0; // meters (mean)
};

class GeoUtils {
public:
    // WGS84 lat/lon/alt -> local East-North-Up meters, relative to origin.
    // Uses an equirectangular (flat-Earth) approximation, which is accurate
    // to well under 1% for flight areas up to tens of kilometers across.
    static glm::vec3 gpsToENU(double lat, double lon, double alt, const GeoOrigin& origin);

    // Inverse of gpsToENU: local ENU meters -> WGS84 lat/lon/alt.
    static void enuToGPS(const glm::vec3& enu, const GeoOrigin& origin,
                          double& lat, double& lon, double& alt);

    // ENU meters -> OpenGL world space (X=East, Y=Up, Z=-North).
    static glm::vec3 enuToWorld(const glm::vec3& enu);

    // World space -> ENU meters (inverse of enuToWorld).
    static glm::vec3 worldToENU(const glm::vec3& world);

    // Convenience: GPS straight to world space.
    static glm::vec3 gpsToWorld(double lat, double lon, double alt, const GeoOrigin& origin);
};
