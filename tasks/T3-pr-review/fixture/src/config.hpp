// Settings, read from an optional file, then overridden by SHELFWISE_* environment variables.
#pragma once

#include <map>
#include <optional>
#include <string>

namespace shelfwise {

struct Settings {
    std::string database = "shelfwise.db";
    int loan_days = 21;
    int max_loans = 5;
    int fine_per_day_cents = 25;
    int grace_days = 2;
    int max_renewals = 2;
    std::string sender = "library@example.org";
    std::string smtp_host;
    int reminder_workers = 4;
};

using Environment = std::map<std::string, std::string>;

// The file holds one `name = value` per line; `#` starts a comment. Throws std::invalid_argument on
// an unknown setting or an integer setting that is not an integer.
Settings load_settings(const std::optional<std::string>& path, const Environment& env);

Environment process_environment();

}  // namespace shelfwise
