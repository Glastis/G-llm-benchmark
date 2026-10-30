// Data access. Every query of the application lives here.
#pragma once

#include "db.hpp"
#include "models.hpp"

#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace shelfwise {

struct NotFound : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct LoanDetail {
    Loan loan;
    std::string member_name;
    std::string book_title;
};

class Repository {
public:
    explicit Repository(Db& db) : db_(db) {}

    Db& db() const { return db_; }

    // Books
    Book add_book(const std::string& isbn, const std::string& title, const std::string& author,
                  std::optional<int> year = std::nullopt, int copies = 1);
    Book get_book(Id book_id) const;
    Book find_book(const std::string& isbn) const;
    int available_copies(Id book_id) const;

    // Members
    Member add_member(const std::string& name, const std::optional<std::string>& email, Date joined);
    Member get_member(Id member_id) const;

    // Loans
    Loan create_loan(Id book_id, Id member_id, Date borrowed, Date due);
    Loan get_loan(Id loan_id) const;
    Loan close_loan(Id loan_id, Date returned);
    Loan renew_loan(Id loan_id, Date due);
    std::vector<Loan> member_loans(Id member_id, bool open_only = false) const;
    int open_loan_count(Id member_id) const;
    std::vector<Loan> overdue_loans(Date today) const;
    std::vector<LoanDetail> loan_details(Date start, Date end) const;  // borrowed in [start, end)

private:
    Db& db_;
};

}  // namespace shelfwise
