#include "check.hpp"

#include <exception>
#include <iostream>

int main() {
    std::size_t failed = 0;
    for (const check::Test& test : check::registry()) {
        try {
            test.body();
        } catch (const std::exception& e) {
            ++failed;
            std::cerr << "FAIL " << test.name << ": " << e.what() << '\n';
        }
    }
    std::cout << check::registry().size() - failed << '/' << check::registry().size() << " tests passed\n";
    return failed == 0 ? 0 : 1;
}
