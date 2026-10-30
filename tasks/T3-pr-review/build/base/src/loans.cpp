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

// A flat rate per day of delay.
int LoanService::fine(const Loan& loan) const {
    return loan.days_overdue(today_()) * settings_.fine_per_day_cents;
}

}  // namespace shelfwise
