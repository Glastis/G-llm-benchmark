// Lending rules: borrowing, returning and fines.
#pragma once

#include "config.hpp"
#include "models.hpp"
#include "repository.hpp"

#include <functional>
#include <stdexcept>
#include <string>

namespace shelfwise {

struct LoanRefused : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Return {
    Loan loan;
    int fine_cents;
};

class LoanService {
public:
    LoanService(Repository& repo, Settings settings, std::function<Date()> today = shelfwise::today);

    Loan borrow(Id member_id, const std::string& isbn);
    Return return_book(Id loan_id);
    int fine(const Loan& loan) const;  // in cents, for a returned loan

private:
    Repository& repo_;
    Settings settings_;
    std::function<Date()> today_;
};

}  // namespace shelfwise
