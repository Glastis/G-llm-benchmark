#include "check.hpp"
#include "cli.hpp"
#include "helpers.hpp"

#include <sstream>

using namespace shelfwise;

namespace {

struct Result {
    int code;
    std::string out;

    bool operator==(const Result&) const = default;
};

// The command line on a fresh database in a temporary directory.
class Cli {
public:
    Cli() : env_{{"SHELFWISE_DATABASE", (tmp_.path() / "lib.db").string()}} { (*this)({"init"}); }

    Result operator()(const std::vector<std::string>& argv) {
        std::ostringstream out;
        std::ostringstream err;
        const int code = run(argv, out, err, env_);
        return {code, out.str()};
    }

private:
    TempDir tmp_;
    Environment env_;
};

}  // namespace

TEST(cli_lend_and_return) {
    Cli shelfwise;
    shelfwise({"add-book", "9780451524935", "Nineteen Eighty-Four", "George Orwell"});
    shelfwise({"add-member", "Ada Lovelace", "--email", "ada@example.org"});
    const Result borrowed = shelfwise({"borrow", "1", "9780451524935"});
    CHECK(borrowed.code == 0);
    CHECK(borrowed.out.starts_with("loan 1, due "));
    const Result returned = shelfwise({"return", "1"});
    CHECK(returned.code == 0);
    CHECK(returned.out.starts_with("loan 1 closed"));
}

TEST(cli_errors_are_reported) {
    Cli shelfwise;
    CHECK(shelfwise({"borrow", "1", "9780451524935"}).code == 1);
    CHECK(shelfwise({"borrow", "one", "9780451524935"}).code == 2);
}

TEST(cli_search) {
    Cli shelfwise;
    shelfwise({"add-book", "9780451524935", "Nineteen Eighty-Four", "George Orwell"});
    CHECK(shelfwise({"search", "eighty"}) ==
          Result{0, "9780451524935  Nineteen Eighty-Four (George Orwell)\npage 1/1, 1 result(s)\n"});
}

TEST(cli_renew) {
    Cli shelfwise;
    shelfwise({"add-book", "9780451524935", "Nineteen Eighty-Four", "George Orwell"});
    shelfwise({"add-member", "Ada Lovelace"});
    shelfwise({"borrow", "1", "9780451524935"});
    const Result renewed = shelfwise({"renew", "1"});
    CHECK(renewed.code == 0);
    CHECK(renewed.out.starts_with("loan 1 renewed, due "));
}

TEST(cli_remind_dry_run_with_nothing_overdue) {
    Cli shelfwise;
    CHECK(shelfwise({"remind", "--dry-run"}) == Result{0, "0 reminder(s) for 0 overdue loan(s)\n"});
}
