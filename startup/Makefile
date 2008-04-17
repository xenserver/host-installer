INSTALLER_DIR = $(DESTDIR)/opt/xensource/installer

all:

install:
	mkdir -p $(INSTALLER_DIR)
	install -m775 preinit $(INSTALLER_DIR)
	install -m644 inittab $(DESTDIR)/etc
	mkdir -p $(DESTDIR)/etc/udev/rules.d
	install -m644 60-firmware.rules $(DESTDIR)/etc/udev/rules.d/
	mkdir -p $(DESTDIR)/lib/udev
	install -m755 firmware.agent $(DESTDIR)/lib/udev/
	mkdir -p $(DESTDIR)/lib/firmware
	install -D -m755 S01genesis $(DESTDIR)/etc/init.d
	install -m755 S11network $(DESTDIR)/etc/init.d
