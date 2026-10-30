#include "check.hpp"
#include "helpers.hpp"

using namespace shelfwise;
using std::chrono::days;

TEST(borrow_sets_the_due_date) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    CHECK(loan.borrowed == START);
    CHECK(loan.due == START + days{21});
}

TEST(all_copies_out) {
    Library lib;
    lib.service.borrow(1, "9780141439518");
    lib.service.borrow(2, "9780141439518");
    CHECK_THROWS(LoanRefused, lib.service.borrow(3, "9780141439518"));
}

TEST(member_limit) {
    Settings settings;
    settings.max_loans = 2;
    Library lib(settings);
    lib.service.borrow(1, "9780451524935");
    lib.service.borrow(1, "9780060850524");
    CHECK_THROWS(LoanRefused, lib.service.borrow(1, "9780141182803"));
}

TEST(unknown_book) {
    Library lib;
    CHECK_THROWS(NotFound, lib.service.borrow(1, "0000000000000"));
}

TEST(refusal_leaves_no_transaction_open) {
    Settings settings;
    settings.max_loans = 0;
    Library lib(settings);
    CHECK_THROWS(LoanRefused, lib.service.borrow(1, "9780451524935"));
    CHECK(!lib.db.in_transaction());
}

TEST(return_within_the_grace_period_has_no_fine) {
    Settings settings;
    settings.grace_days = 2;
    Library lib(settings);
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.today = loan.due + days{2};
    CHECK(lib.service.return_book(loan.id).fine_cents == 0);
}

TEST(late_return_is_fined_per_day_after_the_grace_period) {
    Settings settings;
    settings.fine_per_day_cents = 30;
    settings.grace_days = 2;
    Library lib(settings);
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.today = loan.due + days{6};
    CHECK(lib.service.return_book(loan.id).fine_cents == 120);
}

TEST(cannot_return_twice) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.service.return_book(loan.id);
    CHECK_THROWS(NotFound, lib.service.return_book(loan.id));
}

TEST(returned_copy_is_available_again) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    CHECK(lib.repo.available_copies(loan.book_id) == 0);
    lib.service.return_book(loan.id);
    CHECK(lib.repo.available_copies(loan.book_id) == 1);
}

TEST(renewal_extends_from_the_due_date) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.today = loan.due - days{3};
    const Loan renewed = lib.service.renew(loan.id);
    CHECK(renewed.due == loan.due + days{21});
    CHECK(renewed.renewals == 1);
}

TEST(renewal_limit) {
    Settings settings;
    settings.max_renewals = 2;
    Library lib(settings);
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.service.renew(loan.id);
    lib.service.renew(loan.id);
    CHECK_THROWS(LoanRefused, lib.service.renew(loan.id));
}

TEST(overdue_loan_cannot_be_renewed) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.today = loan.due + days{1};
    CHECK_THROWS(LoanRefused, lib.service.renew(loan.id));
}

TEST(closed_loan_cannot_be_renewed) {
    Library lib;
    const Loan loan = lib.service.borrow(1, "9780451524935");
    lib.service.return_book(loan.id);
    CHECK_THROWS(LoanRefused, lib.service.renew(loan.id));
}
