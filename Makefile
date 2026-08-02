PACKAGE_DIR := $(CURDIR)
DIST_DIR := $(PACKAGE_DIR)/dist

.PHONY: all deb clean lint

all: deb

deb:
	./build.sh "$(DIST_DIR)"

lint:
	python3 -m py_compile usr/lib/enigma2/python/Plugins/Extensions/Vidio/plugin.py usr/lib/enigma2/python/Plugins/Extensions/Vidio/__init__.py

clean:
	rm -rf "$(DIST_DIR)" .build
