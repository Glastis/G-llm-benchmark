#include "check.hpp"
#include "config.hpp"
#include "helpers.hpp"

#include <fstream>

using namespace shelfwise;

TEST(config_defaults) {
    CHECK(load_settings(std::nullopt, {}).loan_days == 21);
}

TEST(config_file_then_environment) {
    TempDir tmp;
    const std::string path = (tmp.path() / "shelfwise.conf").string();
    std::ofstream(path) << "# desk settings\nloan_days = 14\nsender = desk@example.org\n";
    const Settings settings = load_settings(path, {{"SHELFWISE_LOAN_DAYS", "7"}});
    CHECK(settings.loan_days == 7);
    CHECK(settings.sender == "desk@example.org");
}

TEST(config_unknown_setting) {
    TempDir tmp;
    const std::string path = (tmp.path() / "shelfwise.conf").string();
    std::ofstream(path) << "loan_dayz = 14\n";
    CHECK_THROWS(std::invalid_argument, load_settings(path, {}));
}

TEST(config_bad_integer) {
    CHECK_THROWS(std::invalid_argument, load_settings(std::nullopt, {{"SHELFWISE_MAX_LOANS", "many"}}));
}
