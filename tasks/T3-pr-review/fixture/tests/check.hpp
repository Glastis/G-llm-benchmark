// A minimal test harness: TEST(name) { ... } registers a test, CHECK and CHECK_THROWS fail it.
#pragma once

#include <format>
#include <stdexcept>
#include <string>
#include <vector>

namespace check {

struct Failure : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Test {
    const char* name;
    void (*body)();
};

inline std::vector<Test>& registry() {
    static std::vector<Test> tests;
    return tests;
}

struct Register {
    Register(const char* name, void (*body)()) { registry().push_back({name, body}); }
};

[[noreturn]] inline void fail(const char* file, int line, const std::string& what) {
    throw Failure(std::format("{}:{}: {}", file, line, what));
}

}  // namespace check

#define TEST(name)                                                \
    static void name();                                           \
    static const check::Register name##_registered{#name, &name}; \
    static void name()

#define CHECK(...)                                                             \
    do {                                                                       \
        if (!(__VA_ARGS__)) {                                                  \
            check::fail(__FILE__, __LINE__, "CHECK(" #__VA_ARGS__ ") failed"); \
        }                                                                      \
    } while (false)

#define CHECK_THROWS(type, ...)                                                    \
    do {                                                                           \
        bool thrown = false;                                                       \
        try {                                                                      \
            static_cast<void>(__VA_ARGS__);                                        \
        } catch (const type&) {                                                    \
            thrown = true;                                                         \
        }                                                                          \
        if (!thrown) {                                                             \
            check::fail(__FILE__, __LINE__, #__VA_ARGS__ " did not throw " #type); \
        }                                                                          \
    } while (false)
