cmake_minimum_required(VERSION 3.20)
project(shelfwise VERSION 0.5.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(SQLite3 REQUIRED)
find_package(Threads REQUIRED)

add_library(shelfwise_core
    src/cli.cpp
    src/config.cpp
    src/date.cpp
    src/db.cpp
    src/loans.cpp
    src/mailer.cpp
    src/models.cpp
    src/notify.cpp
    src/reports.cpp
    src/repository.cpp
    src/search.cpp
)
target_include_directories(shelfwise_core PUBLIC src)
target_compile_options(shelfwise_core PUBLIC -Wall -Wextra)
target_link_libraries(shelfwise_core PUBLIC SQLite::SQLite3 Threads::Threads)

add_executable(shelfwise src/main.cpp)
target_link_libraries(shelfwise PRIVATE shelfwise_core)

enable_testing()
add_executable(shelfwise_tests
    tests/helpers.cpp
    tests/test_catalogue.cpp
    tests/test_cli.cpp
    tests/test_config.cpp
    tests/test_loans.cpp
    tests/test_main.cpp
    tests/test_notify.cpp
)
target_link_libraries(shelfwise_tests PRIVATE shelfwise_core)
add_test(NAME shelfwise_tests COMMAND shelfwise_tests)
