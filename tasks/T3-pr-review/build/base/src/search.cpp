#include "search.hpp"

#include "text.hpp"

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

std::vector<Book> search(const Db& db, const std::string& term, int limit) {
    const std::string pattern = like_pattern(trim(term));
    Statement rows = query(db,
                           "SELECT * FROM books WHERE title LIKE ? ESCAPE '\\' OR author LIKE ? ESCAPE '\\'"
                           " ORDER BY title COLLATE NOCASE LIMIT ?",
                           pattern, pattern, limit);
    std::vector<Book> books;
    while (rows.step()) {
        books.push_back(Book::from_row(rows));
    }
    return books;
}

}  // namespace shelfwise
