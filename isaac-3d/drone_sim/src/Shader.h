#pragma once
#include <GL/glew.h>
#include <glm/glm.hpp>
#include <string>

// Loads, compiles and links a GLSL vertex+fragment shader pair from files.
// Provides typed uniform setters used throughout the renderer.
class Shader {
public:
    GLuint id = 0;

    Shader() = default;
    Shader(const std::string& vertPath, const std::string& fragPath);
    ~Shader();

    // Non-copyable, movable (owns a GL program handle)
    Shader(const Shader&) = delete;
    Shader& operator=(const Shader&) = delete;
    Shader(Shader&& other) noexcept;
    Shader& operator=(Shader&& other) noexcept;

    void use() const;

    void setMat4(const std::string& name, const glm::mat4& m) const;
    void setVec3(const std::string& name, const glm::vec3& v) const;
    void setFloat(const std::string& name, float v) const;
    void setInt(const std::string& name, int v) const;

private:
    static std::string readFile(const std::string& path);
    static GLuint compile(GLenum type, const std::string& src, const std::string& debugName);
};
