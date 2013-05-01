INSTALLER_DIR = $(DESTDIR)/opt/xensource/installer

all:

install:
	mkdir -p $(INSTALLER_DIR)
	install -m775 preinit $(INSTALLER_DIR)
	install -m644 inittab $(DESTDIR)/etc
	install -D -m644 blacklist $(DESTDIR)/etc/modprobe.d/blacklist.conf
	mkdir -p $(DESTDIR)/lib/firmware
	install -D -m755 S01genesis $(DESTDIR)/etc/init.d/S01genesis
	install -m755 S02hardware $(DESTDIR)/etc/init.d
	install -m755 S03auto $(DESTDIR)/etc/init.d
	install -m755 S03unplug-vcpus $(DESTDIR)/etc/init.d
	install -m755 S05ramdisk $(DESTDIR)/etc/init.d
	install -m755 S06mount $(DESTDIR)/etc/init.d
	install -m755 S11network $(DESTDIR)/etc/init.d
	install -m755 S99alt-start $(DESTDIR)/etc/init.d
	install -m755 functions $(DESTDIR)/etc/init.d
	install -D -m644 depmod.conf $(DESTDIR)/etc/depmod.d/depmod.conf
	install -D -m644 modprobe.mlx4 $(DESTDIR)/etc/modprobe.d/mlx4.conf
