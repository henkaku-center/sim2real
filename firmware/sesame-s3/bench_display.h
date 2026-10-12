// SPDX-License-Identifier: Apache-2.0
// Paired-channel display adapted from Tim's authorised diagnostic design.
// Provenance: reference/vendor/tim-servo-debug/NOTICE.md and SOURCE.json.
#pragma once
#include <cmath>
#include <cstdio>
#include <cstddef>

namespace sesame {
// Raw physical channels, not an assertion that any joint mapping is verified.
inline int benchChannel(int row, int column) { return row + 4 * column; }
inline void formatBenchCell(char* out, size_t size, int channel, const char* joint,
                            bool active, float commanded) {
  if (std::isfinite(commanded))
    std::snprintf(out, size, "%c%d %-2s:%3d", active ? '*' : ' ', channel, joint,
                  int(std::lround(commanded)));
  else
    std::snprintf(out, size, " %d %-2s:---", channel, joint);
}
}
