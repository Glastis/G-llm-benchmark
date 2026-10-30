// Reminders for members whose loans are late.
#pragma once

#include "mailer.hpp"
#include "repository.hpp"

#include <string>

namespace shelfwise {

inline const std::string SUBJECT = "Your library loan is overdue";

std::string reminder_body(const std::string& name, const std::string& title, Date due);

// Mails every member with an overdue loan and returns how many were mailed. Members without an
// address are skipped.
int send_reminders(const Repository& repo, Mailer& mailer, Date today);

}  // namespace shelfwise
