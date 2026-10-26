shader_type spatial;
render_mode cull_disabled;
varying vec3 world_position;
void vertex() {
    world_position = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}
void fragment() {
    float line = sin(world_position.z * 8.0 + sin(world_position.x * 1.9) * 2.0 - TIME * 1.3);
    float ripple = smoothstep(0.93, 1.0, line) * 0.06;
    ALBEDO = vec3(0.10,0.24,0.23) + ripple;
    ROUGHNESS = 0.75;
}
