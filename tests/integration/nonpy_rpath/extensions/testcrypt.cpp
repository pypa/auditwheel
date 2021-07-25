#include "testcrypt.h"
#include <crypt.h>

std::string crypt_something() {
    char const* result = crypt("will error out", "\0");
    if (result == NULL) {
        return std::string("*");
    }
    return std::string(result);
}
