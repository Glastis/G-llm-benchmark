#include "db.hpp"

#include <sqlite3.h>

#include <array>
#include <format>
#include <set>
#include <utility>

namespace shelfwise {

namespace {

const std::string SCHEMA = R"(
CREATE TABLE IF NOT EXISTS books (
    id      INTEGER PRIMARY KEY,
    isbn    TEXT NOT NULL UNIQUE,
    title   TEXT NOT NULL,
    author  TEXT NOT NULL,
    year    INTEGER,
    copies  INTEGER NOT NULL DEFAULT 1 CHECK (copies >= 0)
);
CREATE TABLE IF NOT EXISTS members (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    email   TEXT,
    joined  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS loans (
    id        INTEGER PRIMARY KEY,
    book_id   INTEGER NOT NULL REFERENCES books(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    borrowed  TEXT NOT NULL,
    due       TEXT NOT NULL,
    returned  TEXT
);
CREATE INDEX IF NOT EXISTS loans_open_by_book ON loans(book_id) WHERE returned IS NULL;
CREATE INDEX IF NOT EXISTS loans_by_member ON loans(member_id);
)";

struct Migration {
    std::string_view table;
    std::string_view column;
    std::string_view definition;
};

// Columns added after the first release.
constexpr std::array<Migration, 1> MIGRATIONS{{
    {"loans", "renewals", "INTEGER NOT NULL DEFAULT 0"},
}};

[[noreturn]] void fail(sqlite3* db, std::string_view what) {
    throw DbError(std::format("{}: {}", what, sqlite3_errmsg(db)));
}

}  // namespace

Statement::Statement(sqlite3* db, std::string_view sql) : db_(db) {
    if (sqlite3_prepare_v2(db, sql.data(), static_cast<int>(sql.size()), &stmt_, nullptr) != SQLITE_OK) {
        fail(db, sql);
    }
}

Statement::Statement(Statement&& other) noexcept : db_(other.db_), stmt_(std::exchange(other.stmt_, nullptr)) {}

Statement::~Statement() {
    sqlite3_finalize(stmt_);
}

Statement& Statement::bind(int index, std::int64_t value) {
    if (sqlite3_bind_int64(stmt_, index, value) != SQLITE_OK) {
        fail(db_, "bind");
    }
    return *this;
}

Statement& Statement::bind(int index, std::string_view value) {
    const char* text = value.data() != nullptr ? value.data() : "";
    if (sqlite3_bind_text(stmt_, index, text, static_cast<int>(value.size()), SQLITE_TRANSIENT) != SQLITE_OK) {
        fail(db_, "bind");
    }
    return *this;
}

Statement& Statement::bind(int index, std::nullopt_t) {
    if (sqlite3_bind_null(stmt_, index) != SQLITE_OK) {
        fail(db_, "bind");
    }
    return *this;
}

bool Statement::step() {
    switch (sqlite3_step(stmt_)) {
    case SQLITE_ROW:
        return true;
    case SQLITE_DONE:
        return false;
    default:
        fail(db_, sqlite3_sql(stmt_));
    }
}

int Statement::column(std::string_view name) const {
    for (int i = 0; i < sqlite3_column_count(stmt_); ++i) {
        if (name == sqlite3_column_name(stmt_, i)) {
            return i;
        }
    }
    throw DbError(std::format("no column {}", name));
}

std::int64_t Statement::integer(int column) const {
    return sqlite3_column_int64(stmt_, column);
}

std::int64_t Statement::integer(std::string_view name) const {
    return integer(column(name));
}

std::string Statement::text(std::string_view name) const {
    const int index = column(name);
    const auto* text = reinterpret_cast<const char*>(sqlite3_column_text(stmt_, index));
    return text != nullptr ? std::string(text, static_cast<std::size_t>(sqlite3_column_bytes(stmt_, index))) : std::string();
}

std::optional<std::int64_t> Statement::optional_integer(std::string_view name) const {
    const int index = column(name);
    if (sqlite3_column_type(stmt_, index) == SQLITE_NULL) {
        return std::nullopt;
    }
    return integer(index);
}

std::optional<std::string> Statement::optional_text(std::string_view name) const {
    if (sqlite3_column_type(stmt_, column(name)) == SQLITE_NULL) {
        return std::nullopt;
    }
    return text(name);
}

Db::Db(const std::string& path) {
    if (sqlite3_open(path.c_str(), &db_) != SQLITE_OK) {
        const std::string message = db_ != nullptr ? sqlite3_errmsg(db_) : "out of memory";
        sqlite3_close(db_);
        throw DbError(std::format("cannot open {}: {}", path, message));
    }
    sqlite3_busy_timeout(db_, 5000);
    try {
        exec("PRAGMA foreign_keys = ON");
    } catch (...) {
        sqlite3_close(db_);
        throw;
    }
}

Db::~Db() {
    sqlite3_close(db_);
}

void Db::exec(const std::string& sql) {
    char* error = nullptr;
    if (sqlite3_exec(db_, sql.c_str(), nullptr, nullptr, &error) != SQLITE_OK) {
        const std::string message = error != nullptr ? error : sqlite3_errmsg(db_);
        sqlite3_free(error);
        throw DbError(message);
    }
}

Statement Db::prepare(std::string_view sql) const {
    return Statement(db_, sql);
}

Id Db::last_insert_id() const {
    return sqlite3_last_insert_rowid(db_);
}

int Db::changes() const {
    return sqlite3_changes(db_);
}

bool Db::in_transaction() const {
    return sqlite3_get_autocommit(db_) == 0;
}

Transaction::Transaction(Db& db) : db_(db) {
    db_.exec("BEGIN IMMEDIATE");
}

Transaction::~Transaction() {
    if (open_ && db_.in_transaction()) {
        try {
            db_.exec("ROLLBACK");
        } catch (const DbError&) {
            // SQLite already rolled back after the error that brought us here.
        }
    }
}

void Transaction::commit() {
    db_.exec("COMMIT");
    open_ = false;
}

void init(Db& db) {
    db.exec(SCHEMA);
    migrate(db);
}

std::vector<std::string> migrate(Db& db) {
    std::vector<std::string> added;
    for (const auto& [table, column, definition] : MIGRATIONS) {
        std::set<std::string, std::less<>> existing;
        Statement info = db.prepare(std::format("PRAGMA table_info({})", table));
        while (info.step()) {
            existing.insert(info.text("name"));
        }
        if (!existing.empty() && !existing.contains(column)) {
            db.exec(std::format("ALTER TABLE {} ADD COLUMN {} {}", table, column, definition));
            added.push_back(std::format("{}.{}", table, column));
        }
    }
    return added;
}

}  // namespace shelfwise
