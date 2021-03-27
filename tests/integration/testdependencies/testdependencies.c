#ifdef WITH_DEPENDENCY
#include "dependency.h"
#else
#include <malloc.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
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
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 24)
    res = (int)nextupf(0.0F);
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 17)
    res = (int)(intptr_t)secure_getenv("NON_EXISTING_ENV_VARIABLE");
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 10)
    res = malloc_info(0, stdout);
#else
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
