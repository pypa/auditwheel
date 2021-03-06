#include <Python.h>

static PyObject *
run(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    return PyLong_FromLong(0);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testsimple(void)
{
    static PyMethodDef module_methods[] = {
        {"run", (PyCFunction)run, METH_NOARGS, "run."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "testsimple",
        "testsimple module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
