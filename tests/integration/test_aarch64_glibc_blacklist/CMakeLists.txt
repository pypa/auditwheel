cmake_minimum_required(VERSION 3.15)
project(test_aarch64_glibc_blacklist VERSION 0.1.0 LANGUAGES C CXX)

set(THREADS_PREFER_PTHREAD_FLAG TRUE)
find_package(Threads REQUIRED)

add_library(test_tls_atexit SHARED tst-tls-atexit-lib.c)

add_executable(test_signaling signaling.cpp)
target_compile_definitions(test_signaling PRIVATE SIGNALING_TYPE=double)
target_link_libraries(test_signaling PRIVATE m)
add_executable(test_signalingf signaling.cpp)
target_compile_definitions(test_signalingf PRIVATE SIGNALING_TYPE=float)
target_link_libraries(test_signalingf PRIVATE m)
add_executable(test_signalingl signaling.cpp)
target_compile_definitions(test_signalingl PRIVATE SIGNALING_TYPE=long\ double)
target_link_libraries(test_signalingl PRIVATE m)

add_executable(test_pthread pthread_default_attr.c)
target_link_libraries(test_pthread PRIVATE Threads::Threads)

install(TARGETS test_tls_atexit)
install(TARGETS test_signaling test_signalingf test_signalingl test_pthread DESTINATION "${SKBUILD_SCRIPTS_DIR}")
