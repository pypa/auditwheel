all: lib-src/b/libb.so lib-src/a/liba.so


lib-src/b/libb.so: lib-src/b/b.c
	gcc -fPIC -shared -o lib-src/b/libb.so lib-src/b/b.c


lib-src/a/liba.so: lib-src/b/libb.so lib-src/a/a.c
	gcc -fPIC -shared -o lib-src/a/liba.so -Ilib-src/b -Llib-src/b -lb lib-src/a/a.c
