#include "reports.hpp"

#include "text.hpp"

#include <algorithm>
#include <format>
#include <map>
#include <stdexcept>

namespace shelfwise {

namespace {

std::pair<Date, Date> month_bounds(int year, int month) {
    if (month < 1 || month > 12) {
        throw std::invalid_argument(std::format("no month {}", month));
    }
    const Date start = make_date(year, static_cast<unsigned>(month), 1);
    const Date end = month == 12 ? make_date(year + 1, 1, 1) : make_date(year, static_cast<unsigned>(month) + 1, 1);
    return {start, end};
}

// The largest count first, then by name.
std::vector<std::pair<std::string, int>> ranked(const std::map<std::string, int>& counts) {
    std::vector<std::pair<std::string, int>> rows(counts.begin(), counts.end());
    std::ranges::stable_sort(rows, [](const auto& a, const auto& b) { return a.second > b.second; });
    return rows;
}

}  // namespace

MonthlyReport monthly_report(const Repository& repo, int year, int month, int top) {
    const auto [start, end] = month_bounds(year, month);
    const std::vector<LoanDetail> details = repo.loan_details(start, end);
    std::map<std::string, int> by_member;
    std::map<std::string, int> by_book;
    for (const LoanDetail& detail : details) {
        ++by_member[detail.member_name];
        ++by_book[detail.book_title];
    }
    std::vector<std::pair<std::string, int>> top_books = ranked(by_book);
    if (top_books.size() > static_cast<std::size_t>(top)) {
        top_books.resize(static_cast<std::size_t>(top));
    }
    return {year, month, static_cast<int>(details.size()), ranked(by_member), top_books};
}

std::string format_monthly(const MonthlyReport& report) {
    std::vector<std::string> lines{std::format("Loans in {}-{:02}: {}", report.year, report.month, report.loans), "",
                                   "By member:"};
    for (const auto& [name, count] : report.by_member) {
        lines.push_back(std::format("  {:<30} {:>3}", name, count));
    }
    lines.emplace_back("");
    lines.emplace_back("Most borrowed:");
    for (const auto& [title, count] : report.top_books) {
        lines.push_back(std::format("  {:<40} {:>3}", title, count));
    }
    return join(lines, "\n");
}

std::vector<OverdueRow> overdue_report(const Repository& repo, Date today) {
    std::vector<OverdueRow> rows;
    for (const Loan& loan : repo.overdue_loans(today)) {
        const Member member = repo.get_member(loan.member_id);
        const Book book = repo.get_book(loan.book_id);
        rows.push_back({member.name, member.email, book.title, loan.due, loan.days_overdue(today)});
    }
    std::ranges::sort(rows, [](const OverdueRow& a, const OverdueRow& b) {
        return a.days != b.days ? a.days > b.days : a.member < b.member;
    });
    return rows;
}

std::string format_overdue(const std::vector<OverdueRow>& rows) {
    if (rows.empty()) {
        return "No overdue loan.";
    }
    std::vector<std::string> lines{std::format("{} overdue loan(s):", rows.size())};
    for (const OverdueRow& row : rows) {
        lines.push_back(std::format("  {:>3} d  {:<25} {:<40} due {}", row.days, row.member, row.title, iso(row.due)));
    }
    return join(lines, "\n");
}

}  // namespace shelfwise
