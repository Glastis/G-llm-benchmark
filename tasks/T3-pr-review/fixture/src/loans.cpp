#include "loans.hpp"

#include <format>
#include <utility>

namespace shelfwise {

LoanService::LoanService(Repository& repo, Settings settings, std::function<Date()> today)
    : repo_(repo), settings_(std::move(settings)), today_(std::move(today)) {}

Loan LoanService::borrow(Id member_id, const std::string& isbn) {
    const Member member = repo_.get_member(member_id);
    const Book book = repo_.find_book(isbn);
    Transaction transaction(repo_.db());
    if (repo_.open_loan_count(member.id) >= settings_.max_loans) {
        throw LoanRefused(std::format("{} already has {} books", member.name, settings_.max_loans));
    }
    if (repo_.available_copies(book.id) <= 0) {
        throw LoanRefused(std::format("no copy of '{}' is available", book.title));
    }
    const Date borrowed = today_();
    Loan loan = repo_.create_loan(book.id, member.id, borrowed, borrowed + std::chrono::days{settings_.loan_days});
    transaction.commit();
    return loan;
}

Return LoanService::return_book(Id loan_id) {
    const Loan loan = repo_.close_loan(loan_id, today_());
    return {loan, fine(loan)};
}

Loan LoanService::renew(Id loan_id) {
    Transaction transaction(repo_.db());
    const Loan loan = repo_.get_loan(loan_id);
    if (!loan.is_open()) {
        throw LoanRefused(std::format("loan {} is closed", loan_id));
    }
    if (loan.days_overdue(today_()) > 0) {
        throw LoanRefused(std::format("loan {} is overdue: return the book instead", loan_id));
    }
    if (loan.renewals >= settings_.max_renewals) {
        throw LoanRefused(std::format("loan {} was already renewed {} times", loan_id, loan.renewals));
    }
    Loan renewed = repo_.renew_loan(loan.id, loan.due + std::chrono::days{settings_.loan_days});
    transaction.commit();
    return renewed;
}

// A flat rate per day of delay, once the grace period is over.
int LoanService::fine(const Loan& loan) const {
    const int days_late = days_between(loan.due, *loan.returned) - settings_.grace_days;
    return days_late * settings_.fine_per_day_cents;
}

}  // namespace shelfwise
