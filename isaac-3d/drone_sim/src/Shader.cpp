#include "Shader.h"
#include <fstream>
#include <sstream>
#include <iostream>
#include <glm/gtc/type_ptr.hpp>

std::string Shader::readFile(const std::string& path) {
    std::ifstream f(path);
    if (!f.is_open()) {
        throw std::runtime_error("Shader: could not open file " + path);
    }
    std::stringstream ss;
    ss << f.rdbuf();
    return ss.str();
}

GLuint Shader::compile(GLenum type, const std::string& src, const std::string& debugName) {
    GLuint shader = glCreateShader(type);
    const char* csrc = src.c_str();
    glShaderSource(shader, 1, &csrc, nullptr);
    glCompileShader(shader);

    GLint success = 0;
    glGetShaderiv(shader, GL_COMPILE_STATUS, &success);
    if (!success) {
        char log[1024];
        glGetShaderInfoLog(shader, sizeof(log), nullptr, log);
        std::cerr << "Shader compile error (" << debugName << "):\n" << log << std::endl;
        throw std::runtime_error("Shader compilation failed: " + debugName);
    }
    return shader;
}

Shader::Shader(const std::string& vertPath, const std::string& fragPath) {
    std::string vsrc = readFile(vertPath);
    std::string fsrc = readFile(fragPath);

    GLuint vs = compile(GL_VERTEX_SHADER, vsrc, vertPath);
    GLuint fs = compile(GL_FRAGMENT_SHADER, fsrc, fragPath);

    id = glCreateProgram();
    glAttachShader(id, vs);
    glAttachShader(id, fs);
    glLinkProgram(id);

    GLint success = 0;
    glGetProgramiv(id, GL_LINK_STATUS, &success);
    if (!success) {
        char log[1024];
        glGetProgramInfoLog(id, sizeof(log), nullptr, log);
        std::cerr << "Shader link error:\n" << log << std::endl;
        throw std::runtime_error("Shader program linking failed");
    }

    glDeleteShader(vs);
    glDeleteShader(fs);
}

Shader::~Shader() {
    if (id) glDeleteProgram(id);
}

Shader::Shader(Shader&& other) noexcept : id(other.id) {
    other.id = 0;
}

Shader& Shader::operator=(Shader&& other) noexcept {
    if (this != &other) {
        if (id) glDeleteProgram(id);
        id = other.id;
        other.id = 0;
    }
    return *this;
}

void Shader::use() const { glUseProgram(id); }

void Shader::setMat4(const std::string& name, const glm::mat4& m) const {
    glUniformMatrix4fv(glGetUniformLocation(id, name.c_str()), 1, GL_FALSE, glm::value_ptr(m));
}
void Shader::setVec3(const std::string& name, const glm::vec3& v) const {
    glUniform3fv(glGetUniformLocation(id, name.c_str()), 1, glm::value_ptr(v));
}
void Shader::setFloat(const std::string& name, float v) const {
    glUniform1f(glGetUniformLocation(id, name.c_str()), v);
}
void Shader::setInt(const std::string& name, int v) const {
    glUniform1i(glGetUniformLocation(id, name.c_str()), v);
}
