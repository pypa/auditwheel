#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <pthread.h>

int main() {
  pthread_attr_t attr;
  pthread_getattr_default_np(&attr);
  return pthread_setattr_default_np(&attr);
}
