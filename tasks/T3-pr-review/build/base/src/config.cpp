#include "config.hpp"

#include "text.hpp"

#include <unistd.h>

#include <charconv>
#include <format>
#include <fstream>
#include <stdexcept>
#include <type_traits>
#include <variant>
#include <vector>

namespace shelfwise {

namespace {

const std::string ENV_PREFIX = "SHELFWISE_";

using Field = std::variant<std::string Settings::*, int Settings::*>;

const std::map<std::string, Field>& fields() {
    static const std::map<std::string, Field> known{
        {"database", &Settings::database},
        {"loan_days", &Settings::loan_days},
        {"max_loans", &Settings::max_loans},
        {"fine_per_day_cents", &Settings::fine_per_day_cents},
        {"sender", &Settings::sender},
    };
    return known;
}

void assign(Settings& settings, const std::string& name, const std::string& value) {
    std::visit(
        [&](auto member) {
            if constexpr (std::is_same_v<decltype(member), int Settings::*>) {
                int number = 0;
                const auto [end, error] = std::from_chars(value.data(), value.data() + value.size(), number);
                if (error != std::errc{} || end != value.data() + value.size()) {
                    throw std::invalid_argument(std::format("setting {} must be an integer, got '{}'", name, value));
                }
                settings.*member = number;
            } else {
                settings.*member = value;
            }
        },
        fields().at(name));
}

std::map<std::string, std::string> read_file(const std::string& path) {
    std::ifstream file(path);
    if (!file) {
        throw std::invalid_argument(std::format("cannot read {}", path));
    }
    std::map<std::string, std::string> values;
    std::string line;
    while (std::getline(file, line)) {
        const std::string text = trim(line.substr(0, line.find('#')));
        if (text.empty()) {
            continue;
        }
        const auto equals = text.find('=');
        if (equals == std::string::npos) {
            throw std::invalid_argument(std::format("{}: expected name = value, got '{}'", path, text));
        }
        values[trim(text.substr(0, equals))] = trim(text.substr(equals + 1));
    }
    return values;
}

}  // namespace

Settings load_settings(const std::optional<std::string>& path, const Environment& env) {
    std::map<std::string, std::string> values;
    if (path) {
        values = read_file(*path);
    }
    std::vector<std::string> unknown;
    for (const auto& [name, value] : values) {
        if (!fields().contains(name)) {
            unknown.push_back(name);
        }
    }
    if (!unknown.empty()) {
        throw std::invalid_argument("unknown settings: " + join(unknown, ", "));
    }
    for (const auto& [name, field] : fields()) {
        if (const auto found = env.find(ENV_PREFIX + upper(name)); found != env.end()) {
            values[name] = found->second;
        }
    }
    Settings settings;
    for (const auto& [name, value] : values) {
        assign(settings, name, value);
    }
    return settings;
}

Environment process_environment() {
    Environment env;
    for (char** entry = environ; *entry != nullptr; ++entry) {
        const std::string_view text(*entry);
        if (const auto equals = text.find('='); equals != std::string_view::npos) {
            env.emplace(text.substr(0, equals), text.substr(equals + 1));
        }
    }
    return env;
}

}  // namespace shelfwise
