#include "repository.hpp"

#include <format>

namespace shelfwise {

Book Repository::add_book(const std::string& isbn, const std::string& title, const std::string& author,
                          std::optional<int> year, int copies) {
    query(db_, "INSERT INTO books (isbn, title, author, year, copies) VALUES (?, ?, ?, ?, ?)", isbn, title, author,
          year, copies)
        .step();
    return get_book(db_.last_insert_id());
}

Book Repository::get_book(Id book_id) const {
    Statement row = query(db_, "SELECT * FROM books WHERE id = ?", book_id);
    if (!row.step()) {
        throw NotFound(std::format("no book {}", book_id));
    }
    return Book::from_row(row);
}

Book Repository::find_book(const std::string& isbn) const {
    Statement row = query(db_, "SELECT * FROM books WHERE isbn = ?", isbn);
    if (!row.step()) {
        throw NotFound(std::format("no book with ISBN {}", isbn));
    }
    return Book::from_row(row);
}

int Repository::available_copies(Id book_id) const {
    Statement row = query(db_,
                          "SELECT b.copies - COUNT(l.id) FROM books b"
                          " LEFT JOIN loans l ON l.book_id = b.id AND l.returned IS NULL"
                          " WHERE b.id = ? GROUP BY b.id",
                          book_id);
    if (!row.step()) {
        throw NotFound(std::format("no book {}", book_id));
    }
    return static_cast<int>(row.integer(0));
}

Member Repository::add_member(const std::string& name, const std::optional<std::string>& email, Date joined) {
    query(db_, "INSERT INTO members (name, email, joined) VALUES (?, ?, ?)", name, email, iso(joined)).step();
    return get_member(db_.last_insert_id());
}

Member Repository::get_member(Id member_id) const {
    Statement row = query(db_, "SELECT * FROM members WHERE id = ?", member_id);
    if (!row.step()) {
        throw NotFound(std::format("no member {}", member_id));
    }
    return Member::from_row(row);
}

Loan Repository::create_loan(Id book_id, Id member_id, Date borrowed, Date due) {
    query(db_, "INSERT INTO loans (book_id, member_id, borrowed, due) VALUES (?, ?, ?, ?)", book_id, member_id,
          iso(borrowed), iso(due))
        .step();
    return get_loan(db_.last_insert_id());
}

Loan Repository::get_loan(Id loan_id) const {
    Statement row = query(db_, "SELECT * FROM loans WHERE id = ?", loan_id);
    if (!row.step()) {
        throw NotFound(std::format("no loan {}", loan_id));
    }
    return Loan::from_row(row);
}

Loan Repository::close_loan(Id loan_id, Date returned) {
    query(db_, "UPDATE loans SET returned = ? WHERE id = ? AND returned IS NULL", iso(returned), loan_id).step();
    if (db_.changes() != 1) {
        throw NotFound(std::format("no open loan {}", loan_id));
    }
    return get_loan(loan_id);
}

Loan Repository::renew_loan(Id loan_id, Date due) {
    query(db_, "UPDATE loans SET due = ?, renewals = renewals + 1 WHERE id = ? AND returned IS NULL", iso(due), loan_id)
        .step();
    if (db_.changes() != 1) {
        throw NotFound(std::format("no open loan {}", loan_id));
    }
    return get_loan(loan_id);
}

std::vector<Loan> Repository::member_loans(Id member_id, bool open_only) const {
    std::string sql = "SELECT * FROM loans WHERE member_id = ?";
    if (open_only) {
        sql += " AND returned IS NULL";
    }
    Statement rows = query(db_, sql + " ORDER BY borrowed, id", member_id);
    std::vector<Loan> loans;
    while (rows.step()) {
        loans.push_back(Loan::from_row(rows));
    }
    return loans;
}

int Repository::open_loan_count(Id member_id) const {
    Statement row = query(db_, "SELECT COUNT(*) FROM loans WHERE member_id = ? AND returned IS NULL", member_id);
    row.step();
    return static_cast<int>(row.integer(0));
}

std::vector<Loan> Repository::overdue_loans(Date today) const {
    Statement rows = query(db_, "SELECT * FROM loans WHERE returned IS NULL AND due < ? ORDER BY due, id", iso(today));
    std::vector<Loan> loans;
    while (rows.step()) {
        loans.push_back(Loan::from_row(rows));
    }
    return loans;
}

std::vector<LoanDetail> Repository::loan_details(Date start, Date end) const {
    Statement rows = query(db_,
                           "SELECT l.*, m.name AS member_name, b.title AS book_title FROM loans l"
                           " JOIN members m ON m.id = l.member_id JOIN books b ON b.id = l.book_id"
                           " WHERE l.borrowed >= ? AND l.borrowed < ? ORDER BY l.borrowed, l.id",
                           iso(start), iso(end));
    std::vector<LoanDetail> details;
    while (rows.step()) {
        details.push_back({Loan::from_row(rows), rows.text("member_name"), rows.text("book_title")});
    }
    return details;
}

}  // namespace shelfwise
