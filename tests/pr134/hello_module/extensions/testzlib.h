#include <iostream>
#include <zlib.h>

#ifndef ZLIB_EXAMPLE // include guard
#define ZLIB_EXAMPLE

std::string compress_string(const std::string& str,
                            int compressionlevel = Z_BEST_COMPRESSION);
std::string decompress_string(const std::string& str);

#endif /* ZLIB_EXAMPLE */
