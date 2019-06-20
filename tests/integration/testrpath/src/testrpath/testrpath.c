#include <Python.h>
#include "a.h"

static PyObject *
func(PyObject *self, PyObject *args)
{
    int res;

    (void)self;
    (void)args;

    res = fa();
    return PyLong_FromLong(res);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testrpath(void)
{
    static PyMethodDef module_methods[] = {
        {"func", (PyCFunction)func, METH_NOARGS, "func."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "testrpath",
        "testrpath module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
