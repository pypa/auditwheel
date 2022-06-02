#include <Python.h>
#include <random>

static PyObject *
run(PyObject *self, PyObject *args)
{
    (void)self;
    (void)args;
    std::random_device rd;
    return PyLong_FromLong(rd.entropy() >= 0.0 ? 0 : -1);
}

/* Module initialization */
PyMODINIT_FUNC PyInit_testentropy(void)
{
    static PyMethodDef module_methods[] = {
        {"run", (PyCFunction)run, METH_NOARGS, "run."},
        {NULL}  /* Sentinel */
    };
    static struct PyModuleDef moduledef = {
        PyModuleDef_HEAD_INIT,
        "testentropy",
        "testentropy module",
        -1,
        module_methods,
    };
    return PyModule_Create(&moduledef);
}
