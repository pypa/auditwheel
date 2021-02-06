#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include "extensions/testzlib.h"

// Module method definitions
static PyObject* hello_world(PyObject *self, PyObject *args) {
    printf("Hello, World!");
    Py_RETURN_NONE;
}

// static PyObject* zlib_example(PyObject *self, PyObject *args) {
//     main();
//     Py_RETURN_NONE;
// }

static PyObject* z_compress(PyObject *self, PyObject *args) {
    const char* str_compress;
    if (!PyArg_ParseTuple(args, "s", &str_compress)) {
        return NULL;
    }

    std::string str_compress_s = str_compress;
    std::string compressed = compress_string(str_compress_s);
    // Copy pointer (compressed string may contain 0 byte)
    const char * str_compressed = &*compressed.begin();
    return PyBytes_FromStringAndSize(str_compressed, compressed.length());
}

static PyObject* z_uncompress(PyObject *self, PyObject *args) {
    const char * str_uncompress;
    Py_ssize_t str_uncompress_len;
    // according to https://docs.python.org/3/c-api/arg.html
    if (!PyArg_ParseTuple(args, "y#", &str_uncompress, &str_uncompress_len)) {
        return NULL;
    }

    std::string uncompressed = decompress_string(std::string (str_uncompress, str_uncompress_len));

    return PyUnicode_FromString(uncompressed.c_str());
}

static PyObject* hello(PyObject *self, PyObject *args) {
    const char* name;
    if (!PyArg_ParseTuple(args, "s", &name)) {
        return NULL;
    }

    printf("Hello, %s!\n", name);
    Py_RETURN_NONE;
}

// Method definition object for this extension, these argumens mean:
// ml_name: The name of the method
// ml_meth: Function pointer to the method implementation
// ml_flags: Flags indicating special features of this method, such as
//          accepting arguments, accepting keyword arguments, being a
//          class method, or being a static method of a class.
// ml_doc:  Contents of this method's docstring
static PyMethodDef hello_methods[] = {
    {
        "hello_world", hello_world, METH_NOARGS,
        "Print 'hello world' from a method defined in a C extension."
    },
    {
        "hello", hello, METH_VARARGS,
        "Print 'hello xxx' from a method defined in a C extension."
    },
    {
        "z_compress", z_compress, METH_VARARGS,
        "Compresses a string using C's libz.so"
    },
    {
        "z_uncompress", z_uncompress, METH_VARARGS,
        "Unompresses a string using C's libz.so"
    },
    {NULL, NULL, 0, NULL}
};

// Module definition
// The arguments of this structure tell Python what to call your extension,
// what it's methods are and where to look for it's method definitions
static struct PyModuleDef hello_definition = {
    PyModuleDef_HEAD_INIT,
    "_hello",
    "A Python module that prints 'hello world' from C code.",
    -1,
    hello_methods
};

// Module initialization
// Python calls this function when importing your extension. It is important
// that this function is named PyInit_[[your_module_name]] exactly, and matches
// the name keyword argument in setup.py's setup() call.
PyMODINIT_FUNC PyInit__hello(void) {
    Py_Initialize();
    return PyModule_Create(&hello_definition);
}
