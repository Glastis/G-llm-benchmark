#include "notify.hpp"

#include "text.hpp"

#include <format>
#include <stdexcept>
#include <utility>

namespace shelfwise {

std::string reminder_body(const std::string& name, const std::string& title, Date due) {
    return std::format("Hello {},\n\n'{}' was due back on {}. Please bring it back or renew it at the desk.\n\n"
                       "The library team",
                       name, title, long_date(due));
}

ReminderDispatcher::ReminderDispatcher(std::string database, Mailer& mailer, int workers)
    : database_(std::move(database)), mailer_(mailer) {
    if (workers < 1) {
        throw std::invalid_argument("at least one worker is needed");
    }
    try {
        for (int i = 0; i < workers; ++i) {
            threads_.emplace_back([this] { work(); });
        }
    } catch (...) {
        close();
        throw;
    }
}

ReminderDispatcher::~ReminderDispatcher() {
    close();
}

int ReminderDispatcher::enqueue_overdue(Date today) {
    Db db(database_);
    const std::vector<Loan> loans = Repository(db).overdue_loans(today);
    {
        const std::lock_guard lock(queue_mutex_);
        for (const Loan& loan : loans) {
            queue_.emplace_back(loan);
        }
    }
    queue_ready_.notify_all();
    return static_cast<int>(loans.size());
}

void ReminderDispatcher::close() {
    {
        const std::lock_guard lock(queue_mutex_);
        for (std::size_t i = 0; i < threads_.size(); ++i) {
            queue_.emplace_back(std::nullopt);
        }
    }
    queue_ready_.notify_all();
    for (std::thread& thread : threads_) {
        if (thread.joinable()) {
            thread.join();
        }
    }
}

int ReminderDispatcher::sent() const {
    const std::lock_guard lock(mutex_);
    return sent_;
}

void ReminderDispatcher::work() {
    Db db(database_);
    const Repository repo(db);
    while (true) {
        std::optional<Loan> loan;
        {
            std::unique_lock lock(queue_mutex_);
            queue_ready_.wait(lock, [this] { return !queue_.empty(); });
            loan = std::move(queue_.front());
            queue_.pop_front();
        }
        if (!loan) {
            return;
        }
        if (reminded_.contains(loan->id)) {
            continue;
        }
        remind(repo, *loan);
        reminded_.insert(loan->id);
    }
}

void ReminderDispatcher::remind(const Repository& repo, const Loan& loan) {
    const Member member = repo.get_member(loan.member_id);
    const Book book = repo.get_book(loan.book_id);
    const std::string address = lower(trim(*member.email));
    try {
        mailer_.send(address, SUBJECT, reminder_body(member.name, book.title, loan.due));
    } catch (const MailError&) {
    }
    const std::lock_guard lock(mutex_);
    ++sent_;
}

}  // namespace shelfwise
