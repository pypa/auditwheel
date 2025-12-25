cmake_minimum_required(VERSION 3.15.0)
project(test_mvec VERSION 0.1.0 LANGUAGES C)

add_library(test_mvec SHARED main.c)

target_link_libraries(test_mvec PUBLIC mvec m)
target_link_options(test_mvec PRIVATE "SHELL:-Wl,-no-as-needed -lmvec -lm")

install(TARGETS test_mvec)
