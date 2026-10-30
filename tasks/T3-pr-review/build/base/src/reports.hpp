// Reports for the library's volunteers.
#pragma once

#include "repository.hpp"

#include <string>
#include <utility>
#include <vector>

namespace shelfwise {

struct MonthlyReport {
    int year;
    int month;
    int loans;
    std::vector<std::pair<std::string, int>> by_member;  // the most loans first
    std::vector<std::pair<std::string, int>> top_books;
};

MonthlyReport monthly_report(const Repository& repo, int year, int month, int top = 5);
std::string format_monthly(const MonthlyReport& report);

}  // namespace shelfwise
