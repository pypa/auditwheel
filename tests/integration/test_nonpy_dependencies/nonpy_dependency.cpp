#include "nonpy_dependency.h"
#include <algorithm>
#include <string>

std::string make_reversed(std::string s){
    std::string s_copy(s);
    std::reverse(s_copy.begin(), s_copy.end());
    return s_copy;
}
