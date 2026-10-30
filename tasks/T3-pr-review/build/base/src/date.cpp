#include "date.hpp"

#include <array>
#include <charconv>
#include <format>
#include <stdexcept>

namespace shelfwise {

namespace {

template <typename T>
bool parse_field(std::string_view text, T& value) {
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    return error == std::errc{} && end == text.data() + text.size();
}

}  // namespace

Date make_date(int year, unsigned month, unsigned day) {
    const std::chrono::year_month_day ymd{std::chrono::year{year}, std::chrono::month{month}, std::chrono::day{day}};
    if (!ymd.ok()) {
        throw std::invalid_argument(std::format("no date {}-{:02}-{:02}", year, month, day));
    }
    return std::chrono::sys_days{ymd};
}

Date parse_date(std::string_view iso) {
    int year = 0;
    unsigned month = 0;
    unsigned day = 0;
    if (iso.size() != 10 || iso[4] != '-' || iso[7] != '-' || !parse_field(iso.substr(0, 4), year) ||
        !parse_field(iso.substr(5, 2), month) || !parse_field(iso.substr(8, 2), day)) {
        throw std::invalid_argument(std::format("not an ISO date: {}", iso));
    }
    return make_date(year, month, day);
}

std::string iso(Date date) {
    const std::chrono::year_month_day ymd{date};
    return std::format("{:04}-{:02}-{:02}", static_cast<int>(ymd.year()), static_cast<unsigned>(ymd.month()),
                       static_cast<unsigned>(ymd.day()));
}

std::string long_date(Date date) {
    static constexpr std::array<const char*, 12> months{"January", "February", "March",     "April",   "May",      "June",
                                                        "July",    "August",   "September", "October", "November", "December"};
    const std::chrono::year_month_day ymd{date};
    return std::format("{:02} {} {}", static_cast<unsigned>(ymd.day()), months[static_cast<unsigned>(ymd.month()) - 1],
                       static_cast<int>(ymd.year()));
}

int days_between(Date from, Date to) {
    return static_cast<int>((to - from).count());
}

Date today() {
    return std::chrono::floor<std::chrono::days>(std::chrono::system_clock::now());
}

}  // namespace shelfwise
