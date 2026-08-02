PACKAGE_DIR := $(CURDIR)
DIST_DIR := $(PACKAGE_DIR)/dist

.PHONY: all packages deb ipk clean lint

all: packages

packages: deb ipk

deb:
	./build.sh "$(DIST_DIR)"

ipk:
	./build-ipk.sh "$(DIST_DIR)"

lint:
	PYTHONPYCACHEPREFIX="$(CURDIR)/.build/pycache" python3 -m py_compile usr/lib/enigma2/python/Plugins/Extensions/Vidio/plugin.py usr/lib/enigma2/python/Plugins/Extensions/Vidio/core.py usr/lib/enigma2/python/Plugins/Extensions/Vidio/__init__.py
	python3 -m unittest discover -s tests -v

clean:
	rm -rf "$(DIST_DIR)" .build .build-ipk
