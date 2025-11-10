#include "dependency.h"
#include <errno.h>
#include <malloc.h>
#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#if defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2, 39)
#include <sys/pidfd.h>
#endif
#if __GLIBC_PREREQ(2, 35)
#include <sys/epoll.h>
#endif
#if __GLIBC_PREREQ(2, 28)
#include <threads.h>
#endif
#endif

int dep_run()
{
#if defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2, 39)
    return (pidfd_getpid(0) == pidfd_getpid(0)) ? 0 : 1;
#elif __GLIBC_PREREQ(2, 35)
    return (epoll_pwait2(0, NULL, 0, NULL, NULL) == epoll_pwait2(0, NULL, 0, NULL, NULL)) ? 0 : 1;
#elif __GLIBC_PREREQ(2, 34)
    // pthread_mutexattr_init was moved to libc.so.6 in manylinux_2_34+
    pthread_mutexattr_t attr;
    int sts = pthread_mutexattr_init(&attr);
    if (sts == 0) {
        pthread_mutexattr_destroy(&attr);
    }
    return sts;
#elif __GLIBC_PREREQ(2, 30)
    return gettid() == getpid() ? 0 : 1;
#elif __GLIBC_PREREQ(2, 28)
    return thrd_equal(thrd_current(), thrd_current()) ? 0 : 1;
#elif __GLIBC_PREREQ(2, 24)
    return (int)nextupf(0.0F);
#elif __GLIBC_PREREQ(2, 17)
    return (int)(intptr_t)secure_getenv("NON_EXISTING_ENV_VARIABLE");
#elif __GLIBC_PREREQ(2, 10)
    return malloc_info(0, stdout);
#else
    return 0;
#endif
#else // !defined(__GLIBC_PREREQ)
    return 0;
#endif
}
