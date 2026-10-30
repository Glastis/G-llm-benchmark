#include "helpers.hpp"

#include <stdlib.h>

#include <stdexcept>

namespace shelfwise {

Library::Library(const Settings& settings) : db(":memory:"), repo(db), service(repo, settings, [this] { return today; }) {
    init(db);
    repo.add_book("9780141439518", "Pride and Prejudice", "Jane Austen", 1813, 2);
    repo.add_book("9780451524935", "Nineteen Eighty-Four", "George Orwell", 1949);
    repo.add_book("9780060850524", "Brave New World", "Aldous Huxley", 1932);
    repo.add_book("9780141182803", "Animal Farm", "George Orwell", 1945);
    repo.add_member("Ada Lovelace", "ada@example.org", make_date(2025, 1, 10));
    repo.add_member("Alan Turing", "alan@example.org", make_date(2025, 6, 1));
    repo.add_member("Grace Hopper", std::nullopt, make_date(2025, 9, 15));
}

TempDir::TempDir() {
    std::string pattern = (std::filesystem::temp_directory_path() / "shelfwise-XXXXXX").string();
    if (mkdtemp(pattern.data()) == nullptr) {
        throw std::runtime_error("cannot create a temporary directory");
    }
    path_ = pattern;
}

TempDir::~TempDir() {
    std::error_code ignored;
    std::filesystem::remove_all(path_, ignored);
}

}  // namespace shelfwise
