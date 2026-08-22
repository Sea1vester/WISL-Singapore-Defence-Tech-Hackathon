#include "sdth_replay/core.hpp"

#include <cmath>
#include <exception>
#include <iostream>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

namespace {

int failures = 0;

void check(bool condition, const std::string& message) {
  if (!condition) {
    ++failures;
    std::cerr << "FAIL: " << message << '\n';
  }
}

void check_near(double actual, double expected, double tolerance, const std::string& message) {
  check(
      std::abs(actual - expected) <= tolerance,
      message + " (actual " + std::to_string(actual) + ", expected " +
          std::to_string(expected) + ")");
}

nlohmann::json path_json() {
  return {
      {"contract_version", "1.0"},
      {"flight_id", "test-flight"},
      {"source", "unit-test"},
      {"frame", "wgs84"},
      {"data_origin", "l1_ingest"},
      {"samples",
       {
           {
               {"t", "2026-07-11T10:00:00Z"},
               {"lat", 1.3521},
               {"lon", 103.8198},
               {"alt_m", 10.0},
               {"yaw_deg", 350.0},
               {"battery_pct", 90.0},
               {"flight_mode", "AUTO"},
           },
           {
               {"t", "2026-07-11T10:00:10Z"},
               {"lat", 1.3531},
               {"lon", 103.8208},
               {"alt_m", 30.0},
               {"yaw_deg", 10.0},
               {"battery_pct", 70.0},
               {"warning", "wind"},
           },
       }},
  };
}

void test_coordinate_conversion() {
  const sdth::replay::GeoPoint origin{0.0, 0.0, 0.0};
  const auto same = sdth::replay::wgs84_to_enu(origin, origin);
  check_near(same.east_m, 0.0, 1e-6, "origin east is zero");
  check_near(same.north_m, 0.0, 1e-6, "origin north is zero");
  check_near(same.up_m, 0.0, 1e-6, "origin up is zero");

  const auto east =
      sdth::replay::wgs84_to_enu({0.0, 0.001, 0.0}, origin);
  check_near(east.east_m, 111.319, 0.02, "longitude offset maps east");
  check_near(east.north_m, 0.0, 0.02, "longitude offset has no north drift");

  const auto elevated =
      sdth::replay::wgs84_to_enu({0.0, 0.0, 42.0}, origin);
  check_near(elevated.up_m, 42.0, 1e-5, "altitude maps up");
}

void test_json_path_parsing() {
  const auto path = sdth::replay::parse_flight_path(path_json());
  check(path.flight_id == "test-flight", "flight id is parsed");
  check(path.source == "unit-test", "source is parsed");
  check(path.data_origin == "l1_ingest", "data origin is parsed");
  check(path.samples.size() == 2, "all samples are parsed");
  check(path.samples.front().timestamp == "2026-07-11T10:00:00Z", "timestamp text is preserved");
  check(path.samples.front().battery_pct == 90.0, "battery percentage is parsed");
  check(path.samples.back().warning == "wind", "event metadata is parsed");
  check_near(
      path.samples.back().time_s - path.samples.front().time_s,
      10.0,
      1e-9,
      "timestamps retain their real interval");
}

void test_timestamp_interpolation() {
  const auto path = sdth::replay::parse_flight_path(path_json());
  const double midpoint = path.samples.front().time_s + 5.0;
  const auto pose = sdth::replay::interpolate(path, midpoint);
  check_near(pose.position.latitude_deg, 1.3526, 1e-9, "latitude interpolates");
  check_near(pose.position.altitude_m, 20.0, 1e-9, "altitude interpolates");
  check_near(*pose.battery_pct, 80.0, 1e-9, "battery interpolates");
  check_near(std::fmod(pose.yaw_deg, 360.0), 0.0, 1e-9, "yaw uses shortest arc");
  check(pose.lower_sample == 0 && pose.upper_sample == 1, "sample bounds are retained");
  check_near(pose.blend, 0.5, 1e-9, "timestamp-derived blend is retained");
}

void test_incident_alignment() {
  auto path = sdth::replay::parse_flight_path(path_json());
  const auto response = nlohmann::json{
      {"flight_id", "test-flight"},
      {"count", 1},
      {"items",
       {{
           {"id", "incident-1"},
           {"incident_type", "battery_drop"},
           {"severity", "warning"},
           {"detector", "rule"},
           {"started_at", "2026-07-11T10:00:08Z"},
           {"ended_at", "2026-07-11T10:00:09Z"},
           {"summary", "Battery dropped quickly"},
           {"lat", 1.3531},
           {"lon", 103.8208},
           {"alt_m", 30.0},
           {"evidence", {{"delta", 20}}},
       }}},
  };
  path.incidents = sdth::replay::parse_incidents(response);
  sdth::replay::align_incidents(path);
  check(path.incidents.size() == 1, "incident response is parsed");
  check(path.incidents.front().type == "battery_drop", "incident type is parsed");
  check(path.incidents.front().sample_index == 1, "incident aligns to nearest timestamp");
  check(path.incidents.front().lat == 1.3531, "incident latitude is parsed");
  check(path.incidents.front().lon == 103.8208, "incident longitude is parsed");
}

}  // namespace

int main() {
  try {
    check_near(
        sdth::replay::parse_iso8601_utc("1970-01-01T00:00:00Z"),
        0.0,
        1e-9,
        "Unix epoch parses");
    test_coordinate_conversion();
    test_json_path_parsing();
    test_timestamp_interpolation();
    test_incident_alignment();
  } catch (const std::exception& error) {
    std::cerr << "Unexpected exception: " << error.what() << '\n';
    return 1;
  }
  if (failures != 0) {
    std::cerr << failures << " test(s) failed\n";
    return 1;
  }
  std::cout << "All sdth-replay core tests passed\n";
  return 0;
}
