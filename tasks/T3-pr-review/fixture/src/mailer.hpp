// Outgoing mail. `Outbox` keeps messages in memory (tests, dry runs); `SmtpMailer` sends them.
#pragma once

#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>

namespace shelfwise {

struct MailError : std::runtime_error {
    using std::runtime_error::runtime_error;
};

struct Message {
    std::string to;
    std::string subject;
    std::string body;
};

class Mailer {
public:
    virtual ~Mailer() = default;
    virtual void send(const std::string& to, const std::string& subject, const std::string& body) = 0;
};

// Safe to share between threads.
class Outbox : public Mailer {
public:
    void send(const std::string& to, const std::string& subject, const std::string& body) override;
    std::vector<Message> sent() const;

private:
    mutable std::mutex mutex_;
    std::vector<Message> sent_;
};

class SmtpMailer : public Mailer {
public:
    SmtpMailer(std::string host, std::string sender, int port = 25);
    void send(const std::string& to, const std::string& subject, const std::string& body) override;  // throws MailError

private:
    std::string host_;
    std::string sender_;
    int port_;
};

}  // namespace shelfwise
