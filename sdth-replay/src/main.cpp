#include "sdth_replay/core.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <raylib.h>

namespace {

using sdth::replay::EnuPoint;
using sdth::replay::FlightPath;
using sdth::replay::GeoPoint;
using sdth::replay::Incident;

constexpr float kPanelWidth = 360.0F;
constexpr float kTimelineHeight = 94.0F;
constexpr float kPi = 3.14159265358979323846F;

struct Options {
  std::vector<std::string> files;
  std::vector<std::string> incident_files;
  std::vector<std::string> flight_ids;
  std::string api_url{"http://localhost:8000"};
  std::string token;
  bool latest{};
};

struct RenderPath {
  FlightPath flight;
  std::vector<Vector3> points;
  GeoPoint origin;
  Color color;
};

struct CameraRig {
  Vector3 target{};
  float yaw{-0.75F};
  float pitch{0.55F};
  float distance{180.0F};
  bool follow{};
};

std::string read_text(const std::filesystem::path& path) {
  std::ifstream stream(path);
  if (!stream) {
    throw std::runtime_error("Unable to open " + path.string());
  }
  return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}

nlohmann::json read_json(const std::filesystem::path& path) {
  return nlohmann::json::parse(read_text(path));
}

Options parse_options(int argc, char** argv) {
  Options options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    auto next = [&]() -> std::string {
      if (++index >= argc) {
        throw std::runtime_error("Missing value after " + argument);
      }
      return argv[index];
    };
    if (argument == "--file") {
      options.files.push_back(next());
    } else if (argument == "--incidents") {
      options.incident_files.push_back(next());
    } else if (argument == "--flight") {
      options.flight_ids.push_back(next());
    } else if (argument == "--api") {
      options.api_url = next();
    } else if (argument == "--token") {
      options.token = next();
    } else if (argument == "--latest") {
      options.latest = true;
    } else if (argument == "--help" || argument == "-h") {
      std::cout
          << "sdth-replay [--file path.json]... [--incidents incidents.json]...\n"
          << "            [--flight id]... [--latest] [--api http://host:port] [--token key]\n";
      std::exit(0);
    } else {
      throw std::runtime_error("Unknown argument: " + argument);
    }
  }
  return options;
}

struct ApiAddress {
  std::string host;
  int port{};
};

ApiAddress parse_http_address(std::string url) {
  constexpr std::string_view prefix = "http://";
  if (!url.starts_with(prefix)) {
    throw std::runtime_error("Only http:// API URLs are supported by the demo client");
  }
  url.erase(0, prefix.size());
  if (const auto slash = url.find('/'); slash != std::string::npos) {
    url.erase(slash);
  }
  ApiAddress address{url, 80};
  if (const auto colon = url.rfind(':'); colon != std::string::npos) {
    address.host = url.substr(0, colon);
    address.port = std::stoi(url.substr(colon + 1));
  }
  return address;
}

nlohmann::json api_get(
    const Options& options,
    const std::string& endpoint,
    bool optional = false) {
  const ApiAddress address = parse_http_address(options.api_url);
  httplib::Client client(address.host, address.port);
  client.set_connection_timeout(2);
  client.set_read_timeout(5);
  httplib::Headers headers;
  if (!options.token.empty()) {
    headers.emplace("Authorization", "Bearer " + options.token);
  }
  auto response = client.Get(endpoint, headers);
  if (!response) {
    throw std::runtime_error("API unavailable at " + options.api_url);
  }
  if (response->status != 200) {
    if (optional && response->status == 404) {
      return nlohmann::json::object();
    }
    throw std::runtime_error(
        "API " + endpoint + " returned HTTP " + std::to_string(response->status));
  }
  return nlohmann::json::parse(response->body);
}

void attach_live_overlays(FlightPath& flight, const Options& options) {
  const auto incidents =
      api_get(options, "/v1/flights/" + flight.flight_id + "/incidents", true);
  if (!incidents.empty()) {
    flight.incidents = sdth::replay::parse_incidents(incidents);
    sdth::replay::align_incidents(flight);
  }
  const auto report =
      api_get(options, "/v1/flights/" + flight.flight_id + "/incident-report", true);
  if (report.contains("report") && report.at("report").is_string()) {
    flight.report_text = report.at("report").get<std::string>();
  } else if (report.contains("mission_summary") && report.at("mission_summary").is_string()) {
    flight.report_text = report.at("mission_summary").get<std::string>();
  }
  flight.upload_status = "ready";
}

std::vector<FlightPath> load_flights(const Options& options) {
  std::vector<FlightPath> flights;
  for (std::size_t index = 0; index < options.files.size(); ++index) {
    auto flight = sdth::replay::parse_flight_path(read_json(options.files[index]));
    if (index < options.incident_files.size()) {
      flight.incidents = sdth::replay::parse_incidents(read_json(options.incident_files[index]));
    }
    sdth::replay::align_incidents(flight);
    flight.upload_status = "offline-demo";
    flights.push_back(std::move(flight));
  }
  auto flight_ids = options.flight_ids;
  if (options.latest) {
    const auto listed = api_get(options, "/v1/flights?limit=5");
    if (listed.contains("items") && listed.at("items").is_array() && !listed.at("items").empty()) {
      flight_ids.push_back(listed.at("items").front().at("id").get<std::string>());
    }
  }
  for (const auto& flight_id : flight_ids) {
    auto flight = sdth::replay::parse_flight_path(
        api_get(options, "/v1/flights/" + flight_id + "/path"));
    attach_live_overlays(flight, options);
    flights.push_back(std::move(flight));
  }
  if (flights.empty()) {
    const std::filesystem::path assets = SDTH_REPLAY_ASSET_DIR;
    auto flight = sdth::replay::parse_flight_path(read_json(assets / "demo_path.json"));
    flight.incidents =
        sdth::replay::parse_incidents(read_json(assets / "demo_incidents.json"));
    sdth::replay::align_incidents(flight);
    flights.push_back(std::move(flight));
  }
  return flights;
}

Vector3 to_world(const EnuPoint& point) {
  return {
      static_cast<float>(point.east_m),
      static_cast<float>(point.up_m),
      static_cast<float>(-point.north_m),
  };
}

std::vector<RenderPath> make_render_paths(std::vector<FlightPath> flights) {
  if (flights.empty() || flights.front().samples.empty()) {
    throw std::runtime_error("No flight samples to render");
  }
  const GeoPoint origin = flights.front().samples.front().position;
  constexpr Color colors[] = {SKYBLUE, ORANGE, LIME, VIOLET, GOLD, PINK};
  std::vector<RenderPath> result;
  for (std::size_t index = 0; index < flights.size(); ++index) {
    RenderPath render{std::move(flights[index]), {}, origin, colors[index % std::size(colors)]};
    render.points.reserve(render.flight.samples.size());
    for (const auto& sample : render.flight.samples) {
      render.points.push_back(to_world(sdth::replay::wgs84_to_enu(sample.position, origin)));
    }
    result.push_back(std::move(render));
  }
  return result;
}

float terrain_height(float x, float z) {
  return 0.65F * std::sin(x * 0.025F) * std::cos(z * 0.022F);
}

void draw_terrain_grid() {
  constexpr int extent = 300;
  constexpr int spacing = 10;
  for (int coordinate = -extent; coordinate <= extent; coordinate += spacing) {
    const Color color = coordinate % 50 == 0 ? Color{64, 92, 91, 255} : Color{39, 59, 61, 255};
    for (int value = -extent; value < extent; value += spacing) {
      DrawLine3D(
          {static_cast<float>(coordinate), terrain_height(coordinate, value), static_cast<float>(value)},
          {static_cast<float>(coordinate), terrain_height(coordinate, value + spacing),
           static_cast<float>(value + spacing)},
          color);
      DrawLine3D(
          {static_cast<float>(value), terrain_height(value, coordinate), static_cast<float>(coordinate)},
          {static_cast<float>(value + spacing), terrain_height(value + spacing, coordinate),
           static_cast<float>(coordinate)},
          color);
    }
  }
}

Vector3 point_for_elapsed(const RenderPath& path, double elapsed, sdth::replay::TimedPose* pose = nullptr) {
  const double time = std::clamp(
      path.flight.samples.front().time_s + elapsed,
      path.flight.samples.front().time_s,
      path.flight.samples.back().time_s);
  auto current = sdth::replay::interpolate(path.flight, time);
  const Vector3 low = path.points[current.lower_sample];
  const Vector3 high = path.points[current.upper_sample];
  if (pose != nullptr) {
    *pose = current;
  }
  return {
      low.x + (high.x - low.x) * static_cast<float>(current.blend),
      low.y + (high.y - low.y) * static_cast<float>(current.blend),
      low.z + (high.z - low.z) * static_cast<float>(current.blend),
  };
}

void draw_uav(Vector3 position, float yaw_deg, Color color) {
  const float yaw = yaw_deg * kPi / 180.0F;
  const Vector3 forward{std::sin(yaw), 0.0F, -std::cos(yaw)};
  const Vector3 right{std::cos(yaw), 0.0F, std::sin(yaw)};
  const auto endpoint = [&](Vector3 axis, float amount) {
    return Vector3{
        position.x + axis.x * amount,
        position.y + axis.y * amount,
        position.z + axis.z * amount,
    };
  };
  DrawSphere(position, 1.2F, color);
  DrawLine3D(endpoint(forward, -3.2F), endpoint(forward, 3.2F), LIGHTGRAY);
  DrawLine3D(endpoint(right, -3.2F), endpoint(right, 3.2F), LIGHTGRAY);
  DrawCylinderEx(endpoint(forward, 0.8F), endpoint(forward, 3.0F), 0.9F, 0.0F, 8, color);
  for (const float sign : {-1.0F, 1.0F}) {
    const Vector3 rotor = endpoint(right, sign * 3.2F);
    DrawCylinderEx(
        {rotor.x, rotor.y - 0.08F, rotor.z},
        {rotor.x, rotor.y + 0.08F, rotor.z},
        1.25F,
        1.25F,
        16,
        Color{145, 222, 220, 150});
  }
}

Camera3D camera_from_rig(const CameraRig& rig) {
  const float horizontal = std::cos(rig.pitch) * rig.distance;
  Camera3D camera{};
  camera.target = rig.target;
  camera.position = {
      rig.target.x + std::sin(rig.yaw) * horizontal,
      rig.target.y + std::sin(rig.pitch) * rig.distance,
      rig.target.z + std::cos(rig.yaw) * horizontal,
  };
  camera.up = {0.0F, 1.0F, 0.0F};
  camera.fovy = 48.0F;
  camera.projection = CAMERA_PERSPECTIVE;
  return camera;
}

void update_camera(CameraRig& rig, Vector3 uav_position) {
  if (IsKeyPressed(KEY_R)) {
    rig = CameraRig{};
  }
  if (IsKeyPressed(KEY_F)) {
    rig.follow = !rig.follow;
  }
  if (rig.follow) {
    rig.target = uav_position;
  }
  const Vector2 mouse_delta = GetMouseDelta();
  if (IsMouseButtonDown(MOUSE_BUTTON_RIGHT)) {
    if (IsKeyDown(KEY_LEFT_SHIFT) || IsKeyDown(KEY_RIGHT_SHIFT)) {
      const float scale = rig.distance * 0.0025F;
      rig.target.x -= mouse_delta.x * std::cos(rig.yaw) * scale;
      rig.target.z += mouse_delta.x * std::sin(rig.yaw) * scale;
      rig.target.y += mouse_delta.y * scale;
      rig.follow = false;
    } else {
      rig.yaw -= mouse_delta.x * 0.008F;
      rig.pitch = std::clamp(rig.pitch + mouse_delta.y * 0.008F, -0.15F, 1.35F);
    }
  }
  rig.distance =
      std::clamp(rig.distance * std::pow(0.88F, GetMouseWheelMove()), 8.0F, 900.0F);
}

bool button(Rectangle bounds, const char* label, bool active = false) {
  const Vector2 mouse = GetMousePosition();
  const bool hovered = CheckCollisionPointRec(mouse, bounds);
  DrawRectangleRec(
      bounds,
      active ? Color{28, 153, 150, 255}
             : hovered ? Color{58, 76, 84, 255} : Color{43, 57, 65, 255});
  const int width = MeasureText(label, 18);
  DrawText(
      label,
      static_cast<int>(bounds.x + (bounds.width - width) * 0.5F),
      static_cast<int>(bounds.y + 8.0F),
      18,
      RAYWHITE);
  return hovered && IsMouseButtonPressed(MOUSE_BUTTON_LEFT);
}

std::string sample_event(const FlightPath& flight, std::size_t index) {
  const auto& sample = flight.samples[index];
  if (!sample.warning.empty()) {
    return sample.warning;
  }
  if (!sample.tip.empty()) {
    return sample.tip;
  }
  return "No event at current sample";
}

void draw_side_panel(
    const RenderPath& path,
    const sdth::replay::TimedPose& pose,
    double elapsed,
    bool playing,
    float speed,
    bool follow,
    std::size_t active_index,
    std::size_t path_count) {
  const int screen_width = GetScreenWidth();
  const int panel_x = screen_width - static_cast<int>(kPanelWidth);
  DrawRectangle(panel_x, 0, static_cast<int>(kPanelWidth), GetScreenHeight(), Color{15, 23, 29, 248});
  DrawLine(panel_x, 0, panel_x, GetScreenHeight(), Color{45, 181, 177, 255});
  int y = 24;
  auto line = [&](const std::string& text, int size = 18, Color color = LIGHTGRAY) {
    DrawText(text.c_str(), panel_x + 22, y, size, color);
    y += size + 9;
  };
  line("SDTH FLIGHT REPLAY", 23, Color{79, 221, 213, 255});
  line("STATUS", 14, GRAY);
  line(path.flight.upload_status, 16, SKYBLUE);
  line(playing ? "PLAYING" : "PAUSED", 19, playing ? LIME : GOLD);
  line("Flight " + std::to_string(active_index + 1) + "/" + std::to_string(path_count) +
       "  " + path.flight.flight_id);
  line("Source: " + path.flight.source, 16);
  line("Origin: " + path.flight.data_origin, 16);
  line("Time: " + sdth::replay::format_iso8601_utc(pose.time_s), 15);
  line(TextFormat("Elapsed: %.1fs   Speed: %.2fx", elapsed, speed), 16);
  y += 6;
  line("TELEMETRY", 14, GRAY);
  line(TextFormat(
      "%.6f, %.6f",
      pose.position.latitude_deg,
      pose.position.longitude_deg), 16);
  line(TextFormat("Altitude: %.1f m", pose.position.altitude_m), 16);
  line(TextFormat(
      "R/P/Y: %.1f  %.1f  %.1f",
      pose.roll_deg,
      pose.pitch_deg,
      pose.yaw_deg), 16);
  line(
      pose.battery_pct ? TextFormat("Battery: %.1f%%", *pose.battery_pct) : "Battery: n/a",
      18,
      pose.battery_pct && *pose.battery_pct < 25.0 ? ORANGE : LIGHTGRAY);
  if (pose.battery_v) {
    line(TextFormat("Voltage: %.2f V", *pose.battery_v), 16);
  }
  y += 6;
  line("EVENT", 14, GRAY);
  line(sample_event(path.flight, pose.lower_sample), 15, GOLD);
  y += 6;
  line("INCIDENTS", 14, GRAY);
  if (path.flight.incidents.empty()) {
    line("No indexed incidents", 15);
  } else {
    const std::size_t shown = std::min<std::size_t>(path.flight.incidents.size(), 5);
    for (std::size_t index = 0; index < shown; ++index) {
      const Incident& incident = path.flight.incidents[index];
      line("[" + incident.severity + "] " + incident.type, 15,
           incident.severity == "critical" ? RED : incident.severity == "warning" ? ORANGE : SKYBLUE);
      if (!incident.summary.empty()) {
        line(incident.summary.substr(0, 40), 13, GRAY);
      }
      if (!incident.report.empty()) {
        line("Report: " + incident.report.substr(0, 34), 13, Color{181, 169, 230, 255});
      }
    }
  }
  if (!path.flight.report_text.empty()) {
    y += 6;
    line("REPORT", 14, GRAY);
    line(path.flight.report_text.substr(0, 42), 13, Color{181, 169, 230, 255});
    if (path.flight.report_text.size() > 42) {
      line(path.flight.report_text.substr(42, 42), 13, Color{181, 169, 230, 255});
    }
  }
  DrawText(
      TextFormat("Camera: %s | RMB orbit | Shift+RMB pan", follow ? "FOLLOW" : "FREE"),
      panel_x + 22,
      GetScreenHeight() - 31,
      13,
      GRAY);
}

}  // namespace

int main(int argc, char** argv) {
  try {
    const Options options = parse_options(argc, argv);
    auto paths = make_render_paths(load_flights(options));
    std::size_t active_path = 0;
    double elapsed = 0.0;
    float speed = 1.0F;
    bool playing = false;
    CameraRig camera_rig;

    SetConfigFlags(FLAG_WINDOW_RESIZABLE | FLAG_MSAA_4X_HINT);
    InitWindow(1440, 900, "SDTH Replay");
    SetTargetFPS(60);

    while (!WindowShouldClose()) {
      if (IsKeyPressed(KEY_SPACE)) {
        playing = !playing;
      }
      if (IsKeyPressed(KEY_LEFT_BRACKET) && active_path > 0) {
        --active_path;
        elapsed = 0.0;
      }
      if (IsKeyPressed(KEY_RIGHT_BRACKET) && active_path + 1 < paths.size()) {
        ++active_path;
        elapsed = 0.0;
      }
      const RenderPath& active = paths[active_path];
      const double duration =
          active.flight.samples.back().time_s - active.flight.samples.front().time_s;
      if (playing) {
        elapsed += GetFrameTime() * speed;
        if (elapsed >= duration) {
          elapsed = duration;
          playing = false;
        }
      }

      sdth::replay::TimedPose active_pose;
      const Vector3 active_position = point_for_elapsed(active, elapsed, &active_pose);
      update_camera(camera_rig, active_position);
      const Camera3D camera = camera_from_rig(camera_rig);

      const int view_width = GetScreenWidth() - static_cast<int>(kPanelWidth);
      const int timeline_y = GetScreenHeight() - static_cast<int>(kTimelineHeight);
      const Rectangle timeline{
          144.0F,
          static_cast<float>(timeline_y + 35),
          static_cast<float>(view_width - 174),
          16.0F,
      };
      if (IsMouseButtonDown(MOUSE_BUTTON_LEFT) &&
          CheckCollisionPointRec(GetMousePosition(), timeline)) {
        elapsed = duration * std::clamp(
                                 (GetMousePosition().x - timeline.x) / timeline.width,
                                 0.0F,
                                 1.0F);
      }

      BeginDrawing();
      ClearBackground(Color{10, 18, 22, 255});
      BeginMode3D(camera);
      draw_terrain_grid();
      for (const auto& path : paths) {
        for (std::size_t index = 1; index < path.points.size(); ++index) {
          DrawLine3D(path.points[index - 1], path.points[index], Fade(path.color, 0.85F));
        }
        const Vector3 launch = path.points.front();
        DrawCylinder(
            {launch.x, terrain_height(launch.x, launch.z) + 0.25F, launch.z},
            2.3F,
            2.3F,
            0.5F,
            24,
            Fade(path.color, 0.75F));
        for (const auto& incident : path.flight.incidents) {
          Vector3 marker{};
          if (incident.lat && incident.lon) {
            marker = to_world(sdth::replay::wgs84_to_enu(
                {*incident.lat, *incident.lon, incident.alt_m.value_or(0.0)},
                path.origin));
          } else if (incident.sample_index && *incident.sample_index < path.points.size()) {
            marker = path.points[*incident.sample_index];
          } else {
            continue;
          }
          const Color incident_color =
              incident.severity == "critical" ? RED
              : incident.severity == "warning" ? ORANGE
                                                : GOLD;
          DrawLine3D(
              {marker.x, terrain_height(marker.x, marker.z), marker.z},
              marker,
              Fade(incident_color, 0.75F));
          DrawSphere(marker, 1.5F, incident_color);
        }
        sdth::replay::TimedPose path_pose;
        const Vector3 position = point_for_elapsed(path, elapsed, &path_pose);
        draw_uav(position, static_cast<float>(path_pose.yaw_deg), path.color);
      }
      EndMode3D();

      DrawRectangle(
          0,
          timeline_y,
          view_width,
          static_cast<int>(kTimelineHeight),
          Color{18, 29, 35, 245});
      if (button({16.0F, static_cast<float>(timeline_y + 26), 104.0F, 38.0F},
                 playing ? "PAUSE" : "PLAY",
                 playing)) {
        playing = !playing;
      }
      DrawRectangleRec(timeline, Color{48, 63, 69, 255});
      const float progress = duration > 0.0 ? static_cast<float>(elapsed / duration) : 0.0F;
      DrawRectangle(
          static_cast<int>(timeline.x),
          static_cast<int>(timeline.y),
          static_cast<int>(timeline.width * progress),
          static_cast<int>(timeline.height),
          Color{46, 194, 185, 255});
      DrawCircle(
          static_cast<int>(timeline.x + timeline.width * progress),
          static_cast<int>(timeline.y + timeline.height * 0.5F),
          8.0F,
          RAYWHITE);
      DrawText(TextFormat("%.1fs", elapsed), static_cast<int>(timeline.x), timeline_y + 59, 15, LIGHTGRAY);
      DrawText(
          TextFormat("%.1fs", duration),
          static_cast<int>(timeline.x + timeline.width - 42),
          timeline_y + 59,
          15,
          LIGHTGRAY);
      const float speed_values[] = {0.25F, 0.5F, 1.0F, 2.0F, 4.0F};
      float speed_x = timeline.x;
      for (float value : speed_values) {
        if (button(
                {speed_x, static_cast<float>(timeline_y + 3), 52.0F, 26.0F},
                TextFormat("%gx", value),
                speed == value)) {
          speed = value;
        }
        speed_x += 57.0F;
      }
      draw_side_panel(
          active,
          active_pose,
          elapsed,
          playing,
          speed,
          camera_rig.follow,
          active_path,
          paths.size());
      DrawText(
          "SPACE play/pause  |  [ ] flights  |  F follow  |  R reset  |  Wheel zoom",
          16,
          16,
          15,
          LIGHTGRAY);
      EndDrawing();
    }
    CloseWindow();
    return 0;
  } catch (const std::exception& error) {
    std::cerr << "sdth-replay: " << error.what() << '\n';
    return 1;
  }
}
