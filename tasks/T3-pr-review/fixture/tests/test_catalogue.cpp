#include "check.hpp"
#include "helpers.hpp"
#include "reports.hpp"
#include "search.hpp"

using namespace shelfwise;
using std::chrono::days;

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
    CHECK(titles(search(lib.db, "orwell").books) == std::vector<std::string>{"Animal Farm", "Nineteen Eighty-Four"});
    CHECK(titles(search(lib.db, "brave").books) == std::vector<std::string>{"Brave New World"});
}

TEST(search_wildcards_are_literal) {
    Library lib;
    CHECK(search(lib.db, "%").books.empty());
    CHECK(search(lib.db, "_").books.empty());
}

TEST(search_pages) {
    Library lib;
    const Page first = search(lib.db, "o", 1, 2);
    CHECK(first.total == 3);
    CHECK(first.pages() == 2);
    CHECK(first.books.size() == 2);
    CHECK(first.has_next());
    const Page second = search(lib.db, "o", 2, 2);
    CHECK(second.books.size() == 1);
    CHECK(!second.has_next());
}

TEST(search_sort_by_year) {
    Library lib;
    std::vector<int> years;
    for (const Book& book : search(lib.db, "", 1, 20, "year").books) {
        years.push_back(book.year.value_or(0));
    }
    CHECK(years == std::vector<int>{1813, 1932, 1945, 1949});
}

TEST(search_bad_page) {
    Library lib;
    CHECK_THROWS(std::invalid_argument, search(lib.db, "orwell", 0));
    CHECK_THROWS(std::invalid_argument, search(lib.db, "orwell", 1, 500));
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

TEST(overdue_report_most_overdue_first) {
    Library lib;
    lib.service.borrow(1, "9780451524935");
    lib.today = START + days{5};
    lib.service.borrow(2, "9780141439518");
    const std::vector<OverdueRow> rows = overdue_report(lib.repo, START + days{30});
    CHECK(rows.size() == 2);
    CHECK(rows[0].member == "Ada Lovelace");
    CHECK(rows[0].days == 9);
    CHECK(rows[1].member == "Alan Turing");
    CHECK(rows[1].days == 4);
    CHECK(format_overdue(rows).starts_with("2 overdue loan(s):"));
    CHECK(format_overdue({}) == "No overdue loan.");
}

TEST(monthly_report_bad_month) {
    Library lib;
    CHECK_THROWS(std::invalid_argument, monthly_report(lib.repo, 2026, 13));
}
