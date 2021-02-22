#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "dependency.h"
#include <string>

/* Module initialization */
PyMODINIT_FUNC PyInit_test_nonpy_dependencies(void)
{
    static PyMethodDef module_methods[] = {
        {"reverse_string", (PyCFunction)reverse_string, METH_VARARGS, "Reverse a string."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        .m_name = "test_nonpy_dependencies",
        .m_doc = "test_nonpy_dependencies module",
        .m_size = -1,
        .m_methods = module_methods,
    };
    return PyModule_Create(&moduledef);
}
