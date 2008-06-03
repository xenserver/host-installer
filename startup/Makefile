INSTALLER_DIR = $(DESTDIR)/opt/xensource/installer

all:

install:
	mkdir -p $(INSTALLER_DIR)
	install -m775 preinit $(INSTALLER_DIR)
	install -m644 inittab $(DESTDIR)/etc
	install -D -m644 blacklist $(DESTDIR)/etc/modprobe.d/blacklist
	install -D -m644 60-firmware.rules $(DESTDIR)/etc/udev/rules.d/60-firmware.rules
	install -D -m755 firmware.agent $(DESTDIR)/lib/udev/firmware.agent
	mkdir -p $(DESTDIR)/lib/firmware
	install -D -m755 S01genesis $(DESTDIR)/etc/init.d/S01genesis
	install -m755 S02hardware $(DESTDIR)/etc/init.d
	install -m755 S11network $(DESTDIR)/etc/init.d
