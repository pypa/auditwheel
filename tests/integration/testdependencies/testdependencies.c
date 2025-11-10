#ifdef WITH_DEPENDENCY
#include "dependency.h"
#else
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
#if __GLIBC_PREREQ(2, 28)
#include <threads.h>
#endif
#endif
#endif
#include <Python.h>

static __thread int tres = 0;

static PyObject *
run(PyObject *self, PyObject *args)
{
    int res;

    (void)self;
    (void)args;

#ifdef WITH_DEPENDENCY
    res = dep_run();
#elif defined(__GLIBC_PREREQ)
#if __GLIBC_PREREQ(2, 39)
    res = (pidfd_getpid(0) == pidfd_getpid(0)) ? 0 : 1;
#elif __GLIBC_PREREQ(2, 34)
    // pthread_mutexattr_init was moved to libc.so.6 in manylinux_2_34+
    pthread_mutexattr_t attr;
    res = pthread_mutexattr_init(&attr);
    if (res == 0) {
        pthread_mutexattr_destroy(&attr);
    }
#elif __GLIBC_PREREQ(2, 30)
    res = gettid() == getpid() ? 0 : 1;
#elif __GLIBC_PREREQ(2, 28)
    res = thrd_equal(thrd_current(), thrd_current()) ? 0 : 1;
#elif __GLIBC_PREREQ(2, 24)
    res = (int)nextupf(0.0F);
#elif __GLIBC_PREREQ(2, 17)
    res = (int)(intptr_t)secure_getenv("NON_EXISTING_ENV_VARIABLE");
#elif __GLIBC_PREREQ(2, 10)
    res = malloc_info(0, stdout);
#else
    res = 0;
#endif
#else  // !defined(__GLIBC_PREREQ)
    res = 0;
#endif
    return PyLong_FromLong(res + tres);
}

static PyObject *
set_tres(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    tres = 1;
    return PyLong_FromLong(tres);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testdependencies(void)
{
    static PyMethodDef module_methods[] = {
        {"run", (PyCFunction)run, METH_NOARGS, "run."},
        {"set_tres", (PyCFunction)set_tres, METH_NOARGS, "set_tres."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "testdependencies",
        "testdependencies module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
