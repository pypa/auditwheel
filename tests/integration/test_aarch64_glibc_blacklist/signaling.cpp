#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif

#include <cmath>
#include <limits>

int main() {
  return issignaling(std::numeric_limits<SIGNALING_TYPE>::quiet_NaN());
}
