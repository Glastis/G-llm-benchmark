// Reminders for members whose loans are late, sent by a pool of worker threads.
#pragma once

#include "mailer.hpp"
#include "repository.hpp"

#include <condition_variable>
#include <deque>
#include <mutex>
#include <optional>
#include <set>
#include <string>
#include <thread>
#include <vector>

namespace shelfwise {

inline const std::string SUBJECT = "Your library loan is overdue";

std::string reminder_body(const std::string& name, const std::string& title, Date due);

// Sends overdue reminders from `workers` threads, each with its own connection to `database`
// (SQLite connections are not shared between threads). The scheduler queues the overdue loans
// every hour, so a loan can be queued several times: it is reminded at most once per dispatcher.
class ReminderDispatcher {
public:
    ReminderDispatcher(std::string database, Mailer& mailer, int workers = 4);
    ReminderDispatcher(const ReminderDispatcher&) = delete;
    ReminderDispatcher& operator=(const ReminderDispatcher&) = delete;
    ~ReminderDispatcher();

    int enqueue_overdue(Date today);  // queues the loans overdue on `today`, returns how many there are
    void close();                     // waits for the queued reminders, then stops the workers
    int sent() const;

private:
    void work();
    void remind(const Repository& repo, const Loan& loan);

    std::string database_;
    Mailer& mailer_;

    std::mutex queue_mutex_;
    std::condition_variable queue_ready_;
    std::deque<std::optional<Loan>> queue_;  // std::nullopt stops a worker

    mutable std::mutex mutex_;
    std::set<Id> reminded_;
    int sent_ = 0;

    std::vector<std::thread> threads_;
};

}  // namespace shelfwise
