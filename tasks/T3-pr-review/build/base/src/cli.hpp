// Command line used at the desk: `shelfwise [--config FILE] <command> ...`.
#pragma once

#include "config.hpp"

#include <iosfwd>
#include <string>
#include <vector>

namespace shelfwise {

// Returns 0 on success, 1 when the library refuses or something is missing, 2 on a usage error.
int run(const std::vector<std::string>& argv, std::ostream& out, std::ostream& err,
        const Environment& env = process_environment());

}  // namespace shelfwise
