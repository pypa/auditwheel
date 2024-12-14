#include "dependency.h"
#include <malloc.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <pthread.h>
#if defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 28)
#include <threads.h>
#endif

int dep_run()
{
#if defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 34)
    // pthread_mutexattr_init was moved to libc.so.6 in manylinux_2_34+
    pthread_mutexattr_t attr;
    int sts = pthread_mutexattr_init(&attr);
    if (sts == 0) {
        pthread_mutexattr_destroy(&attr);
    }
    return sts;
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 28)
    return thrd_equal(thrd_current(), thrd_current()) ? 0 : 1;
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 24)
    return (int)nextupf(0.0F);
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 17)
    return (int)(intptr_t)secure_getenv("NON_EXISTING_ENV_VARIABLE");
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 10)
    return malloc_info(0, stdout);
#else
    return 0;
#endif
}
