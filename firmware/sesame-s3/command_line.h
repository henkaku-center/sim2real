// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <cerrno>

namespace sesame {
// Reject, rather than execute, truncated commands and trailing tokens.
struct CommandLine {
  char text[160] = {};
  char* words[12] = {};
  int count = 0;
  bool parse(const char* input) {
    count = 0;
    if (strlen(input) >= sizeof(text)) return false;
    strcpy(text, input);
    char* save = nullptr;
    for (char* p = strtok_r(text, " \t\r\n", &save); p; p = strtok_r(nullptr, " \t\r\n", &save)) {
      if (count == 12) return false;
      words[count++] = p;
    }
    return count != 0;
  }
  bool is(const char* name, int size) const { return count == size && !strcmp(words[0], name); }
  bool number(int index, float& value) const {
    if (index >= count) return false;
    char* end; errno = 0;
    value = strtof(words[index], &end);
    return end != words[index] && !*end && !errno && std::isfinite(value);
  }
  bool integer(int index, int& value) const {
    float f;
    if (!number(index, f) || f < -100000000 || f > 100000000 || truncf(f) != f) return false;
    value = int(f); return true;
  }
};
} // namespace sesame
