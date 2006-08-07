INSTALLER_DIR ?= $(DESTDIR)/opt/xensource/installer

CC = gcc
CFLAGS =

all: hn

clean:
	-rm -f hn

install:
	mkdir -p $(INSTALLER_DIR)
	install -m755 hn $(INSTALLER_DIR)

hn: hn.c
	$(CC) $(CFLAGS) -o hn hn.c

