#include "models.hpp"

#include <algorithm>

namespace shelfwise {

Book Book::from_row(const Statement& row) {
    const auto year = row.optional_integer("year");
    return {row.integer("id"),
            row.text("isbn"),
            row.text("title"),
            row.text("author"),
            year ? std::optional(static_cast<int>(*year)) : std::nullopt,
            static_cast<int>(row.integer("copies"))};
}

Member Member::from_row(const Statement& row) {
    return {row.integer("id"), row.text("name"), row.optional_text("email"), parse_date(row.text("joined"))};
}

Loan Loan::from_row(const Statement& row) {
    const auto returned = row.optional_text("returned");
    return {row.integer("id"),
            row.integer("book_id"),
            row.integer("member_id"),
            parse_date(row.text("borrowed")),
            parse_date(row.text("due")),
            returned ? std::optional(parse_date(*returned)) : std::nullopt,
            static_cast<int>(row.integer("renewals"))};
}

int Loan::days_overdue(Date today) const {
    return std::max(0, days_between(due, returned.value_or(today)));
}

}  // namespace shelfwise
