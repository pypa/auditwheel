#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "extensions/testcrypt.h"

// Module method definitions
static PyObject* crypt_something(PyObject *self, PyObject *args) {
    return PyUnicode_FromString(crypt_something().c_str());
}

/* Module initialization */
PyMODINIT_FUNC PyInit__nonpy_rpath(void)
{
    static PyMethodDef module_methods[] = {
        {"crypt_something", (PyCFunction)crypt_something, METH_NOARGS, "crypt_something."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "_nonpy_rpath",
        "_nonpy_rpath module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
