#include "testcrypt.h"
#include <crypt.h>

std::string crypt_something() {
    return std::string(crypt("will error out", NULL));
}
