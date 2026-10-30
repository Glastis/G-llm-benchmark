#include "notify.hpp"

#include <format>

namespace shelfwise {

std::string reminder_body(const std::string& name, const std::string& title, Date due) {
    return std::format("Hello {},\n\n'{}' was due back on {}. Please bring it back or renew it at the desk.\n\n"
                       "The library team",
                       name, title, long_date(due));
}

int send_reminders(const Repository& repo, Mailer& mailer, Date today) {
    int sent = 0;
    for (const Loan& loan : repo.overdue_loans(today)) {
        const Member member = repo.get_member(loan.member_id);
        if (!member.email) {
            continue;
        }
        const Book book = repo.get_book(loan.book_id);
        mailer.send(*member.email, SUBJECT, reminder_body(member.name, book.title, loan.due));
        ++sent;
    }
    return sent;
}

}  // namespace shelfwise
