#include "dependency.h"
#include <malloc.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>

int dep_run()
{
#if defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 24)
    return (int)nextupf(0.0F);
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 17)
    return (int)(intptr_t)secure_getenv("NON_EXISTING_ENV_VARIABLE");
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 10)
    return malloc_info(0, stdout);
#else
    return 0;
#endif
}
