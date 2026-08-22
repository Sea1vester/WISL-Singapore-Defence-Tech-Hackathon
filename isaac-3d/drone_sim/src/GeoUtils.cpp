#include "GeoUtils.h"
#include <cmath>

static constexpr double DEG2RAD = M_PI / 180.0;
static constexpr double RAD2DEG = 180.0 / M_PI;

glm::vec3 GeoUtils::gpsToENU(double lat, double lon, double alt, const GeoOrigin& origin) {
    double lat0Rad = origin.lat0 * DEG2RAD;

    double east  = (lon - origin.lon0) * DEG2RAD * GeoOrigin::kEarthRadius * std::cos(lat0Rad);
    double north = (lat - origin.lat0) * DEG2RAD * GeoOrigin::kEarthRadius;
    double up    = alt - origin.alt0;

    return glm::vec3(static_cast<float>(east),
                      static_cast<float>(north),
                      static_cast<float>(up));
}

void GeoUtils::enuToGPS(const glm::vec3& enu, const GeoOrigin& origin,
                         double& lat, double& lon, double& alt) {
    double lat0Rad = origin.lat0 * DEG2RAD;

    lat = origin.lat0 + (static_cast<double>(enu.y) / GeoOrigin::kEarthRadius) * RAD2DEG;
    lon = origin.lon0 +
          (static_cast<double>(enu.x) / (GeoOrigin::kEarthRadius * std::cos(lat0Rad))) * RAD2DEG;
    alt = origin.alt0 + static_cast<double>(enu.z);
}

glm::vec3 GeoUtils::enuToWorld(const glm::vec3& enu) {
    // enu = (East, North, Up) -> world = (East, Up, -North)
    return glm::vec3(enu.x, enu.z, -enu.y);
}

glm::vec3 GeoUtils::worldToENU(const glm::vec3& world) {
    // world = (X=East, Y=Up, Z=-North) -> enu = (East, North, Up)
    return glm::vec3(world.x, -world.z, world.y);
}

glm::vec3 GeoUtils::gpsToWorld(double lat, double lon, double alt, const GeoOrigin& origin) {
    return enuToWorld(gpsToENU(lat, lon, alt, origin));
}
