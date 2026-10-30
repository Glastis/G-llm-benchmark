#include "mailer.hpp"

#include <netdb.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <format>
#include <string_view>
#include <utility>

namespace shelfwise {

namespace {

// One SMTP conversation over a TCP connection, closed on destruction.
class Session {
public:
    Session(const std::string& host, int port) {
        addrinfo hints{};
        hints.ai_socktype = SOCK_STREAM;
        addrinfo* found = nullptr;
        if (const int error = getaddrinfo(host.c_str(), std::to_string(port).c_str(), &hints, &found); error != 0) {
            throw MailError(gai_strerror(error));
        }
        for (const addrinfo* address = found; address != nullptr && fd_ < 0; address = address->ai_next) {
            fd_ = socket(address->ai_family, address->ai_socktype, address->ai_protocol);
            if (fd_ < 0) {
                continue;
            }
            const timeval timeout{10, 0};
            setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof timeout);
            setsockopt(fd_, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof timeout);
            if (connect(fd_, address->ai_addr, address->ai_addrlen) != 0) {
                close(fd_);
                fd_ = -1;
            }
        }
        freeaddrinfo(found);
        if (fd_ < 0) {
            throw MailError(std::format("cannot connect to {}:{}", host, port));
        }
    }
    Session(const Session&) = delete;
    Session& operator=(const Session&) = delete;
    ~Session() { close(fd_); }

    // Sends `line` (nothing when empty) and checks that the server answers with `code`.
    void command(std::string_view line, int code) {
        if (!line.empty()) {
            write(std::string(line) + "\r\n");
        }
        const std::string reply = read_reply();
        if (reply.compare(0, 3, std::to_string(code)) != 0) {
            throw MailError(std::format("the server answered '{}'", reply));
        }
    }

private:
    void write(const std::string& data) {
        std::size_t done = 0;
        while (done < data.size()) {
            const ssize_t count = ::send(fd_, data.data() + done, data.size() - done, MSG_NOSIGNAL);
            if (count <= 0) {
                throw MailError(std::strerror(errno));
            }
            done += static_cast<std::size_t>(count);
        }
    }

    // The last line of the reply: the lines of a multi-line reply have a '-' after the code.
    std::string read_reply() {
        while (true) {
            std::string line = read_line();
            if (line.size() < 4 || line[3] != '-') {
                return line;
            }
        }
    }

    std::string read_line() {
        while (true) {
            if (const auto end = buffer_.find("\r\n"); end != std::string::npos) {
                std::string line = buffer_.substr(0, end);
                buffer_.erase(0, end + 2);
                return line;
            }
            char chunk[512];
            const ssize_t count = ::recv(fd_, chunk, sizeof chunk, 0);
            if (count <= 0) {
                throw MailError(count == 0 ? "the server closed the connection" : std::strerror(errno));
            }
            buffer_.append(chunk, static_cast<std::size_t>(count));
        }
    }

    int fd_ = -1;
    std::string buffer_;
};

// The body as DATA expects it: CRLF line ends, and a leading '.' doubled.
std::string data_lines(std::string_view body) {
    std::string out;
    std::size_t start = 0;
    while (start <= body.size()) {
        const std::size_t end = std::min(body.find('\n', start), body.size());
        const std::string_view line = body.substr(start, end - start);
        if (line.starts_with('.')) {
            out += '.';
        }
        out.append(line);
        out += "\r\n";
        start = end + 1;
    }
    return out;
}

}  // namespace

void Outbox::send(const std::string& to, const std::string& subject, const std::string& body) {
    const std::lock_guard lock(mutex_);
    sent_.push_back({to, subject, body});
}

std::vector<Message> Outbox::sent() const {
    const std::lock_guard lock(mutex_);
    return sent_;
}

SmtpMailer::SmtpMailer(std::string host, std::string sender, int port)
    : host_(std::move(host)), sender_(std::move(sender)), port_(port) {}

void SmtpMailer::send(const std::string& to, const std::string& subject, const std::string& body) {
    try {
        Session smtp(host_, port_);
        smtp.command("", 220);
        smtp.command("HELO shelfwise", 250);
        smtp.command(std::format("MAIL FROM:<{}>", sender_), 250);
        smtp.command(std::format("RCPT TO:<{}>", to), 250);
        smtp.command("DATA", 354);
        smtp.command(std::format("From: {}\r\nTo: {}\r\nSubject: {}\r\n\r\n{}.", sender_, to, subject, data_lines(body)), 250);
        smtp.command("QUIT", 221);
    } catch (const MailError& e) {
        throw MailError(std::format("cannot send to {}: {}", to, e.what()));
    }
}

}  // namespace shelfwise
