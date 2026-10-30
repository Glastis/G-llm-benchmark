// Domain records, read from database rows.
#pragma once

#include "date.hpp"
#include "db.hpp"

#include <optional>
#include <string>

namespace shelfwise {

struct Book {
    Id id;
    std::string isbn;
    std::string title;
    std::string author;
    std::optional<int> year;
    int copies;

    static Book from_row(const Statement& row);
};

struct Member {
    Id id;
    std::string name;
    std::optional<std::string> email;
    Date joined;

    static Member from_row(const Statement& row);
};

struct Loan {
    Id id;
    Id book_id;
    Id member_id;
    Date borrowed;
    Date due;
    std::optional<Date> returned;

    bool is_open() const { return !returned; }
    int days_overdue(Date today) const;  // days past the due date, 0 when the loan is not late

    static Loan from_row(const Statement& row);
};

}  // namespace shelfwise
