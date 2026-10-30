Write a single C++20 source file named sim.cpp, and no other file, of at least 500 lines. Using only the standard library, it must implement:

1. a generic LRU cache;
2. a binary min-heap priority queue;
3. a small matrix class with addition, multiplication and transpose;
4. a tokenizer and an evaluator for arithmetic expressions with `+ - * /` and parentheses;
5. a run-length encoder and decoder.

`main()` must run self-tests for every part with assertions, and print exactly `ALL OK` when they all pass.

Before you stop, check that it builds with `g++ -std=c++20 -Wall -Wextra sim.cpp -o sim` and that `./sim` prints `ALL OK`.
