#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "nonpy_dependency.h"
#include <string>

PyObject* reverse_string(PyObject *self, PyObject *args) {
    const char* str_to_reverse;
    if (!PyArg_ParseTuple(args, "s", &str_to_reverse)) {
        return NULL;
    }

    std::string str_to_reverse_s(str_to_reverse);
    std::string reversed = make_reversed(str_to_reverse_s);
    const char * str_reversed = &*reversed.begin();
    return PyUnicode_FromStringAndSize(str_reversed, reversed.length());
}
