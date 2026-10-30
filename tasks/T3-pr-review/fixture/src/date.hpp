// Calendar dates. They are stored as ISO strings (YYYY-MM-DD) in the database.
#pragma once

#include <chrono>
#include <string>
#include <string_view>

namespace shelfwise {

using Date = std::chrono::sys_days;

Date make_date(int year, unsigned month, unsigned day);  // throws std::invalid_argument
Date parse_date(std::string_view iso);                   // throws std::invalid_argument
std::string iso(Date date);
std::string long_date(Date date);  // "02 March 2026"
int days_between(Date from, Date to);
Date today();

}  // namespace shelfwise
