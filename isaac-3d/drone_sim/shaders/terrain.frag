#version 330 core
in vec3 vWorldPos;
in vec3 vNormal;
out vec4 FragColor;

uniform vec3 lightDir;      // directional "sun" light, pointing FROM the sun
uniform float maxHeight;

vec3 heightColor(float h01, float slope) {
    vec3 water  = vec3(0.15, 0.35, 0.55);
    vec3 sand   = vec3(0.76, 0.70, 0.50);
    vec3 grass  = vec3(0.30, 0.55, 0.25);
    vec3 rock   = vec3(0.45, 0.42, 0.40);
    vec3 snow   = vec3(0.95, 0.95, 0.97);

    vec3 c;
    if (h01 < 0.08) c = mix(water, sand, h01 / 0.08);
    else if (h01 < 0.45) c = mix(sand, grass, (h01 - 0.08) / 0.37);
    else if (h01 < 0.75) c = mix(grass, rock, (h01 - 0.45) / 0.30);
    else c = mix(rock, snow, (h01 - 0.75) / 0.25);

    // Steep slopes read as rock regardless of altitude
    c = mix(c, rock, clamp(slope * 1.5, 0.0, 1.0));
    return c;
}

void main() {
    float h01 = clamp(vWorldPos.y / maxHeight, 0.0, 1.0);
    float slope = 1.0 - clamp(dot(normalize(vNormal), vec3(0, 1, 0)), 0.0, 1.0);

    vec3 base = heightColor(h01, slope);

    vec3 N = normalize(vNormal);
    vec3 L = normalize(-lightDir);
    float diff = max(dot(N, L), 0.0);
    float ambient = 0.35;

    vec3 color = base * (ambient + (1.0 - ambient) * diff);
    FragColor = vec4(color, 1.0);
}
