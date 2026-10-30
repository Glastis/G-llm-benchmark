// Catalogue search.
#pragma once

#include "db.hpp"
#include "models.hpp"

#include <string>
#include <vector>

namespace shelfwise {

// Books whose title or author contains `term`, case-insensitively, by title.
std::vector<Book> search(const Db& db, const std::string& term, int limit = 50);

}  // namespace shelfwise
