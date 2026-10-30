#include "check.hpp"
#include "helpers.hpp"
#include "notify.hpp"

#include <algorithm>

using namespace shelfwise;

namespace {

// A database file the worker threads can open: two members with one overdue loan each.
struct Overdue {
    Overdue() {
        Db db(database);
        init(db);
        Repository repo(db);
        repo.add_book("9780451524935", "Nineteen Eighty-Four", "George Orwell", std::nullopt, 3);
        repo.add_member("Ada Lovelace", "Ada@Example.org ", START);
        repo.add_member("Alan Turing", "alan@example.org", START);
        LoanService service(repo, Settings(), [] { return START; });
        service.borrow(1, "9780451524935");
        service.borrow(2, "9780451524935");
    }

    TempDir tmp;
    std::string database = (tmp.path() / "lib.db").string();
    Date late = START + std::chrono::days{30};
};

std::vector<std::string> recipients(const Outbox& outbox) {
    std::vector<std::string> to;
    for (const Message& message : outbox.sent()) {
        to.push_back(message.to);
    }
    std::ranges::sort(to);
    return to;
}

}  // namespace

TEST(every_overdue_member_is_reminded) {
    Overdue library;
    Outbox outbox;
    ReminderDispatcher dispatcher(library.database, outbox, 2);
    CHECK(dispatcher.enqueue_overdue(library.late) == 2);
    dispatcher.close();
    CHECK(recipients(outbox) == std::vector<std::string>{"ada@example.org", "alan@example.org"});
    CHECK(dispatcher.sent() == 2);
}

TEST(a_loan_queued_twice_is_reminded_once) {
    Overdue library;
    Outbox outbox;
    ReminderDispatcher dispatcher(library.database, outbox, 1);
    dispatcher.enqueue_overdue(library.late);
    dispatcher.enqueue_overdue(library.late);
    dispatcher.close();
    CHECK(outbox.sent().size() == 2);
}

TEST(nothing_overdue) {
    Overdue library;
    Outbox outbox;
    ReminderDispatcher dispatcher(library.database, outbox, 3);
    CHECK(dispatcher.enqueue_overdue(START) == 0);
    dispatcher.close();
    CHECK(outbox.sent().empty());
}
