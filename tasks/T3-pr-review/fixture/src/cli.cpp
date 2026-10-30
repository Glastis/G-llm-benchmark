#include "cli.hpp"

#include "db.hpp"
#include "loans.hpp"
#include "mailer.hpp"
#include "notify.hpp"
#include "reports.hpp"
#include "repository.hpp"
#include "search.hpp"
#include "text.hpp"

#include <algorithm>
#include <charconv>
#include <format>
#include <map>
#include <optional>
#include <ostream>
#include <set>
#include <stdexcept>

namespace shelfwise {

namespace {

struct UsageError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Command {
    std::vector<std::string> positional;
    std::vector<std::string> options;  // each followed by a value
    std::vector<std::string> flags;
    std::string help;
};

std::string sort_keys() {
    return join(std::vector<std::string>(SORT_KEYS.begin(), SORT_KEYS.end()), ", ");
}

const std::map<std::string, Command>& commands() {
    static const std::map<std::string, Command> table{
        {"init", {{}, {}, {}, "create the database"}},
        {"add-book", {{"isbn", "title", "author"}, {"--year", "--copies"}, {}, "add a title to the catalogue"}},
        {"add-member", {{"name"}, {"--email"}, {}, "register a member"}},
        {"borrow", {{"member_id", "isbn"}, {}, {}, "lend a book"}},
        {"return", {{"loan_id"}, {}, {}, "take a book back"}},
        {"renew", {{"loan_id"}, {}, {}, "extend a loan"}},
        {"search", {{"term"}, {"--page", "--per-page", "--sort"}, {}, "search the catalogue, sort by " + sort_keys()}},
        {"report", {{"year", "month"}, {}, {}, "monthly report"}},
        {"overdue", {{}, {}, {}, "list the overdue loans"}},
        {"remind", {{}, {}, {"--dry-run"}, "mail the members whose loans are overdue"}},
    };
    return table;
}

std::string usage() {
    std::string text = "usage: shelfwise [--config FILE] <command> [arguments]\n\ncommands:\n";
    for (const auto& [name, command] : commands()) {
        std::string line = "  " + name;
        for (const std::string& argument : command.positional) {
            line += " <" + argument + ">";
        }
        for (const std::string& option : command.options) {
            line += " [" + option + " VALUE]";
        }
        for (const std::string& flag : command.flags) {
            line += " [" + flag + "]";
        }
        text += std::format("{:<56} {}\n", line, command.help);
    }
    return text;
}

struct Args {
    std::optional<std::string> config;
    std::string command;
    std::map<std::string, std::string> values;  // positional arguments by name, and options
    std::set<std::string> flags;

    const std::string& at(const std::string& name) const { return values.at(name); }
    bool flag(const std::string& name) const { return flags.contains(name); }
};

Args parse(const std::vector<std::string>& argv) {
    Args args;
    std::size_t i = 0;
    if (i < argv.size() && argv[i] == "--config") {
        if (i + 1 >= argv.size()) {
            throw UsageError("--config needs a file");
        }
        args.config = argv[i + 1];
        i += 2;
    }
    if (i >= argv.size()) {
        throw UsageError("a command is required");
    }
    args.command = argv[i++];
    const auto found = commands().find(args.command);
    if (found == commands().end()) {
        throw UsageError(std::format("unknown command {}", args.command));
    }
    const Command& command = found->second;
    std::size_t next = 0;
    for (; i < argv.size(); ++i) {
        const std::string& arg = argv[i];
        if (std::ranges::find(command.flags, arg) != command.flags.end()) {
            args.flags.insert(arg);
        } else if (std::ranges::find(command.options, arg) != command.options.end()) {
            if (i + 1 >= argv.size()) {
                throw UsageError(std::format("{} needs a value", arg));
            }
            args.values[arg] = argv[++i];
        } else if (arg.starts_with("--") || next == command.positional.size()) {
            throw UsageError(std::format("unexpected argument {}", arg));
        } else {
            args.values[command.positional[next++]] = arg;
        }
    }
    if (next < command.positional.size()) {
        throw UsageError(std::format("missing <{}>", command.positional[next]));
    }
    return args;
}

template <typename T>
T number(const Args& args, const std::string& name) {
    const std::string& text = args.at(name);
    T value{};
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size()) {
        throw UsageError(std::format("{} must be an integer, got '{}'", name, text));
    }
    return value;
}

template <typename T>
std::optional<T> optional_number(const Args& args, const std::string& name) {
    return args.values.contains(name) ? std::optional(number<T>(args, name)) : std::nullopt;
}

int execute(const Args& args, std::ostream& out, const Environment& env) {
    const Settings settings = load_settings(args.config, env);
    Db db(settings.database);
    if (args.command == "init") {
        init(db);
        out << std::format("database ready: {}\n", settings.database);
        return 0;
    }
    migrate(db);
    Repository repo(db);
    LoanService service(repo, settings);
    if (args.command == "add-book") {
        const Book book = repo.add_book(args.at("isbn"), args.at("title"), args.at("author"),
                                        optional_number<int>(args, "--year"),
                                        optional_number<int>(args, "--copies").value_or(1));
        out << std::format("book {}: {}\n", book.id, book.title);
    } else if (args.command == "add-member") {
        const auto email = args.values.contains("--email") ? std::optional(args.at("--email")) : std::nullopt;
        const Member member = repo.add_member(args.at("name"), email, today());
        out << std::format("member {}: {}\n", member.id, member.name);
    } else if (args.command == "borrow") {
        const Loan loan = service.borrow(number<Id>(args, "member_id"), args.at("isbn"));
        out << std::format("loan {}, due {}\n", loan.id, iso(loan.due));
    } else if (args.command == "return") {
        const Return result = service.return_book(number<Id>(args, "loan_id"));
        const std::string fine = result.fine_cents != 0 ? std::format(", fine {:.2f}", result.fine_cents / 100.0) : "";
        out << std::format("loan {} closed{}\n", result.loan.id, fine);
    } else if (args.command == "renew") {
        const Loan loan = service.renew(number<Id>(args, "loan_id"));
        out << std::format("loan {} renewed, due {}\n", loan.id, iso(loan.due));
    } else if (args.command == "search") {
        const Page page = search(db, args.at("term"), optional_number<int>(args, "--page").value_or(1),
                                 optional_number<int>(args, "--per-page").value_or(20),
                                 args.values.contains("--sort") ? args.at("--sort") : "title");
        for (const Book& book : page.books) {
            out << std::format("{}  {} ({})\n", book.isbn, book.title, book.author);
        }
        out << std::format("page {}/{}, {} result(s)\n", page.page, page.pages(), page.total);
        if (page.has_next()) {
            out << std::format("next: --page {}\n", page.page + 1);
        }
    } else if (args.command == "report") {
        out << format_monthly(monthly_report(repo, number<int>(args, "year"), number<int>(args, "month"))) << '\n';
    } else if (args.command == "overdue") {
        out << format_overdue(overdue_report(repo, today())) << '\n';
    } else if (args.command == "remind") {
        const bool dry_run = args.flag("--dry-run") || settings.smtp_host.empty();
        Outbox outbox;
        SmtpMailer smtp(settings.smtp_host, settings.sender);
        Mailer& mailer = dry_run ? static_cast<Mailer&>(outbox) : smtp;
        ReminderDispatcher dispatcher(settings.database, mailer, settings.reminder_workers);
        const int queued = dispatcher.enqueue_overdue(today());
        dispatcher.close();
        if (dry_run) {
            for (const Message& message : outbox.sent()) {
                out << std::format("{}: {}\n", message.to, message.subject);
            }
        }
        out << std::format("{} reminder(s) for {} overdue loan(s)\n", dispatcher.sent(), queued);
    }
    return 0;
}

}  // namespace

int run(const std::vector<std::string>& argv, std::ostream& out, std::ostream& err, const Environment& env) {
    try {
        return execute(parse(argv), out, env);
    } catch (const UsageError& e) {
        err << usage() << "\nerror: " << e.what() << '\n';
        return 2;
    } catch (const std::runtime_error& e) {  // NotFound, LoanRefused, DbError
        err << "error: " << e.what() << '\n';
        return 1;
    } catch (const std::invalid_argument& e) {
        err << "error: " << e.what() << '\n';
        return 1;
    }
}

}  // namespace shelfwise
