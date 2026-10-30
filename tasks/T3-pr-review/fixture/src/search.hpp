// Catalogue search, one page at a time.
#pragma once

#include "db.hpp"
#include "models.hpp"

#include <array>
#include <string>
#include <string_view>
#include <vector>

namespace shelfwise {

inline constexpr std::array<std::string_view, 3> SORT_KEYS{"title", "author", "year"};
inline constexpr int MAX_PER_PAGE = 100;

struct Page {
    std::vector<Book> books;
    int page;
    int per_page;
    int total;

    // Number of pages for this search (at least one, even when nothing matches).
    int pages() const {
        if (total == 0) {
            return 1;
        }
        return total / per_page + 1;
    }
    bool has_next() const { return page < pages(); }
};

// Books whose title or author contains `term`, case-insensitively. Pages are numbered from 1.
Page search(const Db& db, const std::string& term, int page = 1, int per_page = 20, const std::string& sort = "title");

}  // namespace shelfwise
