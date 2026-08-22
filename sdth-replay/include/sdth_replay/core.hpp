#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

#include <nlohmann/json_fwd.hpp>

namespace sdth::replay {

struct GeoPoint {
  double latitude_deg{};
  double longitude_deg{};
  double altitude_m{};
};

struct EnuPoint {
  double east_m{};
  double north_m{};
  double up_m{};
};

struct TelemetrySample {
  std::string timestamp;
  double time_s{};
  GeoPoint position;
  double roll_deg{};
  double pitch_deg{};
  double yaw_deg{};
  std::optional<double> battery_pct;
  std::optional<double> battery_v;
  std::string flight_mode;
  std::string warning;
  std::string tip;
};

struct Incident {
  std::string id;
  std::string type;
  std::string severity{"info"};
  std::string detector;
  std::string started_at;
  std::string ended_at;
  std::string summary;
  std::string report;
  std::optional<double> lat;
  std::optional<double> lon;
  std::optional<double> alt_m;
  std::optional<std::size_t> sample_index;
};

struct FlightPath {
  std::string contract_version;
  std::string flight_id;
  std::string source;
  std::string frame;
  std::string data_origin;
  std::vector<TelemetrySample> samples;
  std::vector<Incident> incidents;
  std::string report_text;
  std::string upload_status{"offline-demo"};
};

struct TimedPose {
  double time_s{};
  GeoPoint position;
  double roll_deg{};
  double pitch_deg{};
  double yaw_deg{};
  std::optional<double> battery_pct;
  std::optional<double> battery_v;
  std::size_t lower_sample{};
  std::size_t upper_sample{};
  double blend{};
};

double parse_iso8601_utc(std::string_view timestamp);
std::string format_iso8601_utc(double epoch_seconds);
EnuPoint wgs84_to_enu(const GeoPoint& point, const GeoPoint& origin);
FlightPath parse_flight_path(const nlohmann::json& document);
std::vector<Incident> parse_incidents(const nlohmann::json& document);
TimedPose interpolate(const FlightPath& path, double time_s);
std::optional<std::size_t> align_incident_to_path(
    const Incident& incident,
    const FlightPath& path);
void align_incidents(FlightPath& path);

}  // namespace sdth::replay
