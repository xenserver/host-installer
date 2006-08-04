INSTALLER_DIR = $(DESTDIR)/opt/xensource/installer

all:

install:
	mkdir -p $(INSTALLER_DIR)
	install -m775 preinit $(INSTALLER_DIR)
	install -m644 inittab $(DESTDIR)/etc

