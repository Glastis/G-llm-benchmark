// SQLite storage: connection, statements, schema and transactions.
#pragma once

#include <cstdint>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>

struct sqlite3;
struct sqlite3_stmt;

namespace shelfwise {

using Id = std::int64_t;

struct DbError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

// A prepared statement. Parameters are numbered from 1; columns are read by name.
class Statement {
public:
    Statement(sqlite3* db, std::string_view sql);
    Statement(Statement&& other) noexcept;
    Statement(const Statement&) = delete;
    Statement& operator=(const Statement&) = delete;
    Statement& operator=(Statement&&) = delete;
    ~Statement();

    Statement& bind(int index, std::int64_t value);
    Statement& bind(int index, std::string_view value);
    Statement& bind(int index, std::nullopt_t);
    template <typename T>
    Statement& bind(int index, const std::optional<T>& value) {
        return value ? bind(index, *value) : bind(index, std::nullopt);
    }

    bool step();  // true while there is a row to read

    std::int64_t integer(int column) const;
    std::int64_t integer(std::string_view name) const;
    std::string text(std::string_view name) const;
    std::optional<std::int64_t> optional_integer(std::string_view name) const;
    std::optional<std::string> optional_text(std::string_view name) const;

private:
    int column(std::string_view name) const;

    sqlite3* db_;
    sqlite3_stmt* stmt_ = nullptr;
};

// A connection in autocommit mode: writes that must go together use a Transaction.
class Db {
public:
    explicit Db(const std::string& path);
    Db(const Db&) = delete;
    Db& operator=(const Db&) = delete;
    ~Db();

    void exec(const std::string& sql);  // one or more statements, without parameters
    Statement prepare(std::string_view sql) const;
    Id last_insert_id() const;
    int changes() const;
    bool in_transaction() const;

private:
    sqlite3* db_ = nullptr;
};

// Prepares `sql` and binds `params` to its parameters, in order.
template <typename... Params>
Statement query(const Db& db, std::string_view sql, const Params&... params) {
    Statement statement = db.prepare(sql);
    int index = 0;
    (statement.bind(++index, params), ...);
    return statement;
}

// BEGIN IMMEDIATE on construction, ROLLBACK on destruction unless commit() was called.
class Transaction {
public:
    explicit Transaction(Db& db);
    Transaction(const Transaction&) = delete;
    Transaction& operator=(const Transaction&) = delete;
    ~Transaction();

    void commit();

private:
    Db& db_;
    bool open_ = true;
};

void init(Db& db);

}  // namespace shelfwise
