#include "search.hpp"

#include "text.hpp"

#include <cstdint>
#include <format>
#include <stdexcept>

namespace shelfwise {

namespace {

std::string like_pattern(const std::string& term) {
    std::string pattern = "%";
    for (const char c : term) {
        if (c == '\\' || c == '%' || c == '_') {
            pattern += '\\';
        }
        pattern += c;
    }
    return pattern + "%";
}

}  // namespace

Page search(const Db& db, const std::string& term, int page, int per_page, const std::string& sort) {
    if (page < 1) {
        throw std::invalid_argument("pages are numbered from 1");
    }
    if (per_page < 1 || per_page > MAX_PER_PAGE) {
        throw std::invalid_argument(std::format("per_page must be between 1 and {}", MAX_PER_PAGE));
    }
    const std::string pattern = like_pattern(trim(term));
    const std::string where = "title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\'";
    Statement count = query(db, "SELECT COUNT(*) FROM books WHERE " + where, pattern, pattern);
    count.step();
    Page result{{}, page, per_page, static_cast<int>(count.integer(0))};
    const std::string order = " ORDER BY " + sort + " COLLATE NOCASE, id";
    const std::int64_t offset = static_cast<std::int64_t>(page - 1) * per_page;
    Statement rows = query(db, "SELECT * FROM books WHERE " + where + order + " LIMIT ? OFFSET ?", pattern, pattern,
                           per_page, offset);
    while (rows.step()) {
        result.books.push_back(Book::from_row(rows));
    }
    return result;
}

}  // namespace shelfwise
