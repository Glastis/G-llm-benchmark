// Reports for the library's volunteers.
#pragma once

#include "repository.hpp"

#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace shelfwise {

struct OverdueRow {
    std::string member;
    std::optional<std::string> email;
    std::string title;
    Date due;
    int days;
};

struct MonthlyReport {
    int year;
    int month;
    int loans;
    std::vector<std::pair<std::string, int>> by_member;  // the most loans first
    std::vector<std::pair<std::string, int>> top_books;
};

MonthlyReport monthly_report(const Repository& repo, int year, int month, int top = 5);
std::string format_monthly(const MonthlyReport& report);

// Open loans past their due date, the most overdue first.
std::vector<OverdueRow> overdue_report(const Repository& repo, Date today);
std::string format_overdue(const std::vector<OverdueRow>& rows);

}  // namespace shelfwise
