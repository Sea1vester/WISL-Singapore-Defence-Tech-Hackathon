#include "sdth_replay/core.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <ctime>
#include <limits>
#include <stdexcept>

#include <nlohmann/json.hpp>

namespace sdth::replay {
namespace {

constexpr double kPi = 3.14159265358979323846;
constexpr double kWgs84A = 6378137.0;
constexpr double kWgs84E2 = 6.69437999014e-3;

struct EcefPoint {
  double x{};
  double y{};
  double z{};
};

EcefPoint to_ecef(const GeoPoint& point) {
  const double latitude = point.latitude_deg * kPi / 180.0;
  const double longitude = point.longitude_deg * kPi / 180.0;
  const double sin_lat = std::sin(latitude);
  const double cos_lat = std::cos(latitude);
  const double radius = kWgs84A / std::sqrt(1.0 - kWgs84E2 * sin_lat * sin_lat);
  return {
      (radius + point.altitude_m) * cos_lat * std::cos(longitude),
      (radius + point.altitude_m) * cos_lat * std::sin(longitude),
      (radius * (1.0 - kWgs84E2) + point.altitude_m) * sin_lat,
  };
}

long long days_from_civil(int year, unsigned month, unsigned day) {
  year -= month <= 2;
  const int era = (year >= 0 ? year : year - 399) / 400;
  const unsigned year_of_era = static_cast<unsigned>(year - era * 400);
  const unsigned shifted_month = month > 2 ? month - 3 : month + 9;
  const unsigned day_of_year = (153 * shifted_month + 2) / 5 + day - 1;
  const unsigned day_of_era =
      year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
  return static_cast<long long>(era) * 146097 + static_cast<long long>(day_of_era) - 719468;
}

double optional_number(const nlohmann::json& value, std::string_view key, double fallback = 0.0) {
  const auto found = value.find(key);
  if (found == value.end() || found->is_null()) {
    return fallback;
  }
  if (!found->is_number()) {
    throw std::runtime_error("Expected numeric field: " + std::string(key));
  }
  return found->get<double>();
}

std::string optional_string(
    const nlohmann::json& value,
    std::string_view key,
    std::string fallback = {}) {
  const auto found = value.find(key);
  return found != value.end() && found->is_string() ? found->get<std::string>() : fallback;
}

std::optional<double> nullable_number(const nlohmann::json& value, std::string_view key) {
  const auto found = value.find(key);
  if (found == value.end() || found->is_null()) {
    return std::nullopt;
  }
  if (!found->is_number()) {
    throw std::runtime_error("Expected numeric field: " + std::string(key));
  }
  return found->get<double>();
}

double mix(double from, double to, double amount) {
  return from + (to - from) * amount;
}

double mix_angle(double from, double to, double amount) {
  double delta = std::fmod(to - from + 540.0, 360.0) - 180.0;
  return from + delta * amount;
}

std::optional<double> mix_optional(
    const std::optional<double>& from,
    const std::optional<double>& to,
    double amount) {
  if (from && to) {
    return mix(*from, *to, amount);
  }
  return from ? from : to;
}

}  // namespace

double parse_iso8601_utc(std::string_view timestamp) {
  int year{};
  int month{};
  int day{};
  int hour{};
  int minute{};
  double second{};
  char suffix{};
  const std::string input(timestamp);
  const int matched = std::sscanf(
      input.c_str(),
      "%4d-%2d-%2dT%2d:%2d:%lf%c",
      &year,
      &month,
      &day,
      &hour,
      &minute,
      &second,
      &suffix);
  if (matched < 6 || (matched == 7 && suffix != 'Z')) {
    throw std::runtime_error("Unsupported timestamp (expected ISO-8601 UTC): " + input);
  }
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour < 0 || hour > 23 ||
      minute < 0 || minute > 59 || second < 0.0 || second >= 61.0) {
    throw std::runtime_error("Invalid ISO-8601 timestamp: " + input);
  }
  const long long days =
      days_from_civil(year, static_cast<unsigned>(month), static_cast<unsigned>(day));
  return static_cast<double>(days * 86400LL + hour * 3600 + minute * 60) + second;
}

std::string format_iso8601_utc(double epoch_seconds) {
  const std::time_t whole = static_cast<std::time_t>(std::floor(epoch_seconds));
  std::tm utc{};
#if defined(_WIN32)
  gmtime_s(&utc, &whole);
#else
  gmtime_r(&whole, &utc);
#endif
  char buffer[32]{};
  std::strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &utc);
  return buffer;
}

EnuPoint wgs84_to_enu(const GeoPoint& point, const GeoPoint& origin) {
  const EcefPoint target = to_ecef(point);
  const EcefPoint reference = to_ecef(origin);
  const double dx = target.x - reference.x;
  const double dy = target.y - reference.y;
  const double dz = target.z - reference.z;
  const double latitude = origin.latitude_deg * kPi / 180.0;
  const double longitude = origin.longitude_deg * kPi / 180.0;
  const double sin_lat = std::sin(latitude);
  const double cos_lat = std::cos(latitude);
  const double sin_lon = std::sin(longitude);
  const double cos_lon = std::cos(longitude);
  return {
      -sin_lon * dx + cos_lon * dy,
      -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz,
      cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz,
  };
}

FlightPath parse_flight_path(const nlohmann::json& document) {
  if (!document.is_object()) {
    throw std::runtime_error("Flight path must be a JSON object");
  }
  if (!document.contains("samples") || !document.at("samples").is_array()) {
    throw std::runtime_error("Flight path is missing a samples array");
  }

  FlightPath path;
  path.contract_version = optional_string(document, "contract_version", "1.0");
  path.flight_id = optional_string(document, "flight_id");
  path.source = optional_string(document, "source", "unknown");
  path.frame = optional_string(document, "frame", "wgs84");
  path.data_origin = optional_string(document, "data_origin", "offline_file");
  if (path.flight_id.empty()) {
    throw std::runtime_error("Flight path is missing flight_id");
  }

  double previous_time = 0.0;
  bool have_time = false;
  for (const auto& item : document.at("samples")) {
    if (!item.is_object() || !item.contains("lat") || !item.contains("lon")) {
      throw std::runtime_error("Each path sample requires lat and lon");
    }
    TelemetrySample sample;
    sample.timestamp = optional_string(item, "t");
    if (!sample.timestamp.empty()) {
      sample.time_s = parse_iso8601_utc(sample.timestamp);
      previous_time = sample.time_s;
      have_time = true;
    } else {
      sample.time_s = have_time ? previous_time + 1.0 : static_cast<double>(path.samples.size());
      sample.timestamp = format_iso8601_utc(sample.time_s);
      previous_time = sample.time_s;
      have_time = true;
    }
    sample.position = {
        optional_number(item, "lat"),
        optional_number(item, "lon"),
        optional_number(item, "alt_m"),
    };
    sample.roll_deg = optional_number(item, "roll_deg");
    sample.pitch_deg = optional_number(item, "pitch_deg");
    sample.yaw_deg = optional_number(item, "yaw_deg");
    sample.battery_pct = nullable_number(item, "battery_pct");
    sample.battery_v = nullable_number(item, "battery_v");
    sample.flight_mode = optional_string(item, "flight_mode");
    sample.warning = optional_string(item, "warning");
    sample.tip = optional_string(item, "tip");
    path.samples.push_back(std::move(sample));
  }
  if (path.samples.empty()) {
    throw std::runtime_error("Flight path has no samples");
  }
  if (!std::is_sorted(
          path.samples.begin(),
          path.samples.end(),
          [](const auto& left, const auto& right) { return left.time_s <= right.time_s; })) {
    throw std::runtime_error("Flight path timestamps must be ordered");
  }
  return path;
}

std::vector<Incident> parse_incidents(const nlohmann::json& document) {
  const nlohmann::json* items = &document;
  if (document.is_object() && document.contains("items")) {
    items = &document.at("items");
  }
  if (!items->is_array()) {
    throw std::runtime_error("Incident response must contain an items array");
  }
  std::vector<Incident> incidents;
  for (const auto& item : *items) {
    Incident incident;
    incident.id = optional_string(item, "id");
    incident.type = optional_string(item, "incident_type", optional_string(item, "type", "incident"));
    incident.severity = optional_string(item, "severity", "info");
    incident.detector = optional_string(item, "detector");
    incident.started_at = optional_string(item, "started_at");
    incident.ended_at = optional_string(item, "ended_at");
    incident.summary = optional_string(item, "summary");
    incident.lat = nullable_number(item, "lat");
    incident.lon = nullable_number(item, "lon");
    incident.alt_m = nullable_number(item, "alt_m");
    if (item.contains("evidence") && item.at("evidence").is_object()) {
      incident.report = optional_string(item.at("evidence"), "report");
      if (!incident.lat) {
        incident.lat = nullable_number(item.at("evidence"), "lat");
      }
      if (item.at("evidence").contains("position") && item.at("evidence").at("position").is_object()) {
        const auto& position = item.at("evidence").at("position");
        if (!incident.lat) {
          incident.lat = nullable_number(position, "lat");
        }
        if (!incident.lon) {
          incident.lon = nullable_number(position, "lon");
        }
        if (!incident.alt_m) {
          incident.alt_m = nullable_number(position, "alt_m");
        }
      }
    }
    incidents.push_back(std::move(incident));
  }
  return incidents;
}

TimedPose interpolate(const FlightPath& path, double time_s) {
  if (path.samples.empty()) {
    throw std::runtime_error("Cannot interpolate an empty flight path");
  }
  if (time_s <= path.samples.front().time_s || path.samples.size() == 1) {
    const auto& sample = path.samples.front();
    return {
        time_s,
        sample.position,
        sample.roll_deg,
        sample.pitch_deg,
        sample.yaw_deg,
        sample.battery_pct,
        sample.battery_v,
        0,
        0,
        0.0,
    };
  }
  if (time_s >= path.samples.back().time_s) {
    const auto& sample = path.samples.back();
    const auto last = path.samples.size() - 1;
    return {
        time_s,
        sample.position,
        sample.roll_deg,
        sample.pitch_deg,
        sample.yaw_deg,
        sample.battery_pct,
        sample.battery_v,
        last,
        last,
        0.0,
    };
  }
  const auto upper = std::upper_bound(
      path.samples.begin(),
      path.samples.end(),
      time_s,
      [](double value, const TelemetrySample& sample) { return value < sample.time_s; });
  const std::size_t upper_index = static_cast<std::size_t>(upper - path.samples.begin());
  const std::size_t lower_index = upper_index - 1;
  const auto& lower = path.samples[lower_index];
  const auto& high = path.samples[upper_index];
  const double interval = high.time_s - lower.time_s;
  const double blend = interval > 0.0 ? (time_s - lower.time_s) / interval : 0.0;
  return {
      time_s,
      {
          mix(lower.position.latitude_deg, high.position.latitude_deg, blend),
          mix(lower.position.longitude_deg, high.position.longitude_deg, blend),
          mix(lower.position.altitude_m, high.position.altitude_m, blend),
      },
      mix_angle(lower.roll_deg, high.roll_deg, blend),
      mix_angle(lower.pitch_deg, high.pitch_deg, blend),
      mix_angle(lower.yaw_deg, high.yaw_deg, blend),
      mix_optional(lower.battery_pct, high.battery_pct, blend),
      mix_optional(lower.battery_v, high.battery_v, blend),
      lower_index,
      upper_index,
      blend,
  };
}

std::optional<std::size_t> align_incident_to_path(
    const Incident& incident,
    const FlightPath& path) {
  if (path.samples.empty() || incident.started_at.empty()) {
    return std::nullopt;
  }
  const double target = parse_iso8601_utc(incident.started_at);
  auto found = std::lower_bound(
      path.samples.begin(),
      path.samples.end(),
      target,
      [](const TelemetrySample& sample, double value) { return sample.time_s < value; });
  if (found == path.samples.begin()) {
    return 0;
  }
  if (found == path.samples.end()) {
    return path.samples.size() - 1;
  }
  const auto upper_index = static_cast<std::size_t>(found - path.samples.begin());
  const auto lower_index = upper_index - 1;
  return target - path.samples[lower_index].time_s <= path.samples[upper_index].time_s - target
             ? lower_index
             : upper_index;
}

void align_incidents(FlightPath& path) {
  for (auto& incident : path.incidents) {
    incident.sample_index = align_incident_to_path(incident, path);
  }
}

}  // namespace sdth::replay
