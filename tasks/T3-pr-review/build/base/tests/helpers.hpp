// Shared test fixtures: an in-memory library with a few books and members.
#pragma once

#include "config.hpp"
#include "db.hpp"
#include "loans.hpp"
#include "repository.hpp"

#include <filesystem>

namespace shelfwise {

inline const Date START = make_date(2026, 3, 2);

// The service's clock is `today`, which the tests move by hand.
struct Library {
    explicit Library(const Settings& settings = Settings());

    Db db;
    Repository repo;
    Date today = START;
    LoanService service;
};

// A temporary directory, removed with its contents on destruction.
class TempDir {
public:
    TempDir();
    TempDir(const TempDir&) = delete;
    TempDir& operator=(const TempDir&) = delete;
    ~TempDir();

    const std::filesystem::path& path() const { return path_; }

private:
    std::filesystem::path path_;
};

}  // namespace shelfwise
