PREFIX ?= /usr/local
DESTDIR ?=
PYTHON ?= python3

.PHONY: install

install:
	$(PYTHON) scripts/install_runtime.py --prefix "$(PREFIX)" --destdir "$(DESTDIR)"
