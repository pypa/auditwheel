# compile and run
g++ testzlib.cpp -lz -o testzlib
if [ $? == 0 ]; then
    echo Hello Hello Hello Hello Hello Hello! | ./testzlib | ./testzlib -d
fi
# Deflated data: 37 -> 19 (48.6% saved).
# Inflated data: 19 -> 37 (94.7% increase).
# Hello Hello Hello Hello Hello Hello!
