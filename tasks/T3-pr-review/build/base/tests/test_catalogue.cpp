#include "check.hpp"
#include "helpers.hpp"
#include "reports.hpp"
#include "search.hpp"

using namespace shelfwise;

namespace {

std::vector<std::string> titles(const std::vector<Book>& books) {
    std::vector<std::string> out;
    for (const Book& book : books) {
        out.push_back(book.title);
    }
    return out;
}

}  // namespace

TEST(search_matches_title_and_author) {
    Library lib;
    CHECK(titles(search(lib.db, "orwell")) == std::vector<std::string>{"Animal Farm", "Nineteen Eighty-Four"});
    CHECK(titles(search(lib.db, "brave")) == std::vector<std::string>{"Brave New World"});
}

TEST(search_wildcards_are_literal) {
    Library lib;
    CHECK(search(lib.db, "%").empty());
    CHECK(search(lib.db, "_").empty());
}

TEST(search_limit) {
    Library lib;
    CHECK(search(lib.db, "", 2).size() == 2);
}

TEST(monthly_report_counts_by_member_and_book) {
    Library lib;
    lib.service.borrow(1, "9780451524935");
    lib.service.borrow(2, "9780141439518");
    lib.service.borrow(1, "9780141439518");
    lib.today = make_date(2026, 4, 1);
    lib.service.borrow(3, "9780060850524");
    const MonthlyReport report = monthly_report(lib.repo, 2026, 3);
    CHECK(report.loans == 3);
    CHECK(report.by_member == std::vector<std::pair<std::string, int>>{{"Ada Lovelace", 2}, {"Alan Turing", 1}});
    CHECK(report.top_books.front() == std::pair<std::string, int>{"Pride and Prejudice", 2});
    CHECK(format_monthly(report).starts_with("Loans in 2026-03: 3"));
}

TEST(monthly_report_bad_month) {
    Library lib;
    CHECK_THROWS(std::invalid_argument, monthly_report(lib.repo, 2026, 13));
}
