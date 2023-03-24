# destinations
DESTDIR =
INSTALLER_DIR = /opt/xensource/installer
EFI_DIR = /EFI/xenserver
SERVICE_DIR = usr/lib/systemd/system

# root of a tree with sm.rpm unpacked
SM_ROOTDIR =

INSTALL = install

install:
	$(INSTALL) -d $(DESTDIR)/usr/bin
	$(INSTALL) -m755 support.sh $(DESTDIR)/usr/bin
	$(INSTALL) -d $(DESTDIR)$(INSTALLER_DIR)/tui/installer/
	$(INSTALL) -m755 init $(DESTDIR)$(INSTALLER_DIR)/
	$(INSTALL) -m644 \
	        keymaps \
	        timezones \
	        answerfile.py \
	        backend.py \
	        common_criteria_firewall_rules \
	        constants.py \
	        disktools.py \
	        diskutil.py \
	        driver.py \
	        fcoeutil.py \
	        generalui.py \
	        hardware.py \
	        init_constants.py \
	        install.py \
	        netinterface.py \
	        netutil.py \
	        product.py \
	        report.py \
	        repository.py \
	        restore.py \
	        scripts.py \
	        snackutil.py \
	        uicontroller.py \
	        upgrade.py \
	        util.py \
	        xelogging.py \
	    $(DESTDIR)$(INSTALLER_DIR)/
	$(INSTALL) -m644 \
	        tui/__init__.py \
	        tui/init.py \
	        tui/fcoe.py \
	        tui/network.py \
	        tui/progress.py \
	        tui/repo.py \
	    $(DESTDIR)$(INSTALLER_DIR)/tui/
	$(INSTALL) -m644 \
	        tui/installer/__init__.py \
	        tui/installer/screens.py \
	    $(DESTDIR)$(INSTALLER_DIR)/tui/installer/

 # Startup files
	$(INSTALL) -d \
	    $(DESTDIR)/$(SERVICE_DIR) \
	    $(DESTDIR)/etc/modprobe.d \
	    $(DESTDIR)/etc/modules-load.d \
	    $(DESTDIR)/etc/dracut.conf.d \
	    $(DESTDIR)/etc/systemd/system/sshd.service.d \
	    $(DESTDIR)/etc/systemd/system/systemd-udevd.d

	$(INSTALL) -m755 startup/interface-rename-sideway $(DESTDIR)/$(INSTALLER_DIR)
	$(INSTALL) -m644 startup/functions $(DESTDIR)/$(INSTALLER_DIR)
	$(INSTALL) -m644 startup/bnx2x.conf $(DESTDIR)/etc/modprobe.d/
	$(INSTALL) -m644 startup/blacklist $(DESTDIR)/etc/modprobe.d/installer-blacklist.conf
	$(INSTALL) -m644 startup/modprobe.mlx4 $(DESTDIR)/etc/modprobe.d/mlx4.conf
	$(INSTALL) -m644 startup/iscsi-modules $(DESTDIR)/etc/modules-load.d/iscsi.conf
	$(INSTALL) -m755 startup/preinit startup/S05ramdisk $(DESTDIR)/$(INSTALLER_DIR)/
	$(INSTALL) -m644 startup/systemd-udevd_depmod.conf $(DESTDIR)/etc/systemd/system/systemd-udevd.d/installer.conf
	$(INSTALL) -m644 startup/interface-rename-sideway.service $(DESTDIR)/$(SERVICE_DIR)
	$(INSTALL) -m644 startup/sshd_installer.conf $(DESTDIR)/etc/systemd/system/sshd.service.d/

 # Generate a multipath configuration from sm's copy, removing
 # the blacklist and blacklist_exception sections.
	sed 's/\(^[[:space:]]*find_multipaths[[:space:]]*\)yes/\1no/' \
	    < $(SM_ROOTDIR)/etc/multipath.xenserver/multipath.conf \
	    > $(DESTDIR)/etc/multipath.conf.disabled

 # bootloader files
	$(INSTALL) -D -m644 bootloader/grub.cfg $(DESTDIR)$(EFI_DIR)/grub.cfg
	$(INSTALL) -D -m644 bootloader/grub.cfg $(DESTDIR)$(EFI_DIR)/grub-usb.cfg

	patch < bootloader/grub-usb.patch $(DESTDIR)$(EFI_DIR)/grub-usb.cfg

	printf "echo Skipping initrd creation in the installer\nexit 0\n" \
	    > $(DESTDIR)/etc/dracut.conf.d/installer.conf
