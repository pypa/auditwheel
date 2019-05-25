#ifdef WITH_DEPENDENCY
#include "dependency.h"
#else
#include <malloc.h>
#endif
#include <Python.h>

static PyObject *
run(PyObject *self, PyObject *args)
{
    int res;

    (void)self;
    (void)args;

#ifdef WITH_DEPENDENCY
    res = dep_run();
#elif defined(__GLIBC_PREREQ) && __GLIBC_PREREQ(2, 10)
    res = malloc_info(0, stdout);
#else
    res = 0;
#endif
    return PyLong_FromLong(res);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testdependencies(void)
{
    static PyMethodDef module_methods[] = {
        {"run", (PyCFunction)run, METH_NOARGS, "run."},
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
