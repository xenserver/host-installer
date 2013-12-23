USE_BRANDING := yes
include $(B_BASE)/common.mk
include $(PROJECT_OUTPUTDIR)/python-libs/python-libs.inc
include $(PROJECT_OUTPUTDIR)/host-installer/host-installer.inc

# inputs
YUM_CONF := $(PROJECT_OUTPUTDIR)/chroot-dom0/yum.conf
PKG_LIST := pkgs.txt
PYTHON_LIBS_RPM := $(PROJECT_OUTPUTDIR)/python-libs/$(PYTHON_LIBS_PKG_FILE)
HOST_INSTALLER_RPMS := $(PROJECT_OUTPUTDIR)/host-installer/$(HOST_INSTALLER_PKG_FILE)
HOST_INSTALLER_RPMS += $(PROJECT_OUTPUTDIR)/host-installer/$(HOST_INSTALLER_STARTUP_PKG_FILE)
FIRMWARE_RPMS_LIST := $(PROJECT_OUTPUTDIR)/guest-packages-dom0/guest-packages-dom0-firmware-rpms.inc
BIOSDEVNAME_RPM := $(shell find $(PROJECT_OUTPUTDIR)/guest-packages-biosdevname/RPMS -name biosdevname-[0-9]\* -type f | sort | tail -1)
GDISK_RPM := $(shell find $(PROJECT_OUTPUTDIR)/gdisk/RPMS -name gdisk-[0-9]\* -type f | sort | tail -1)

# outputs
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
MBOOT_IMG = $(MY_OUTPUT_DIR)/mboot.img
BUILD_FI_IMAGE = $(MY_OUTPUT_DIR)/build-fi-image.sh

# intermediate:
KERNEL_CONFIGURED_STAMP = $(MY_OBJ_DIR)/.kernel-configured.stamp
FIRMWARE_INSTALLED_STAMP = $(MY_OBJ_DIR)/.firmware-installed.stamp
BASE_IMAGE_STAMP := $(MY_OBJ_DIR)/.base-image.stamp
BASE_IMAGE := $(MY_OBJ_DIR)/base-image.tar.gz
INSTALLER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.installer-installed.stamp
FILES_COLLECTED_STAMP = $(MY_OBJ_DIR)/.files-collected.stamp
INIT_CREATED_STAMP = $(MY_OBJ_DIR)/.init-created.stamp
PROC_ADDED_STAMP = $(MY_OBJ_DIR)/.proc-added.stamp

INSTALLER_FILESYSTEM = $(MY_OBJ_DIR)/filesystem

# commands:
INSTALLER_CHROOT = chroot $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(MBOOTPACK) $(BUILD_FI_IMAGE) $(MY_OUTPUT_DIR)/.dirstamp
	$(MAKE) -C $(call hg_loc,host-installer)/upgrade-plugin $@
	$(call mkdir_clean,$(MY_MAIN_CDFILES))
	cp -l $(INSTALL_IMG) $(MY_MAIN_CDFILES)
	zcat $(PROJECT_OUTPUTDIR)/xen/CD_FILES.main/boot/xen.gz >$(MY_OBJ_DIR)/xen
	if [ -e $(PROJECT_OUTPUTDIR)/kernel-dom0/CD_FILES.main/boot/vmlinux.gz ]; then \
		zcat $(PROJECT_OUTPUTDIR)/kernel-dom0/CD_FILES.main/boot/vmlinux.gz >$(MY_OBJ_DIR)/vmlinux; \
	else \
		zcat $(PROJECT_OUTPUTDIR)/kernel-dom0/CD_FILES.main/boot/vmlinuz >$(MY_OBJ_DIR)/vmlinux; \
	fi
	mbootpack -o $(MBOOT_IMG) $(MY_OBJ_DIR)/xen -m $(MY_OBJ_DIR)/vmlinux -m $(INSTALL_IMG)
	rm -f $(MY_OBJ_DIR)/xen $(MY_OBJ_DIR)/vmlinux

$(BASE_IMAGE): $(YUM_CONF) $(PKG_LIST)
	rm -rf $(INSTALLER_FILESYSTEM)
	yum --nogpgcheck --config=$(YUM_CONF) --installroot=$(INSTALLER_FILESYSTEM) install -v $$(sed -r 's/^ +//; /^#|^$$/d' < $(PKG_LIST))
	tar -C $(INSTALLER_FILESYSTEM) -zcf $@.tmp .
	mv -f $@.tmp $@

$(BASE_IMAGE_STAMP): $(BASE_IMAGE)
	rm -rf $(INSTALLER_FILESYSTEM)
	mkdir $(INSTALLER_FILESYSTEM)
	tar -C $(INSTALLER_FILESYSTEM) -zxf $<
# install $(PYTHON_LIBS_RPM) and $(HOST_INSTALLER_RPMS)
	set -e; all= ;\
	for f in $(PYTHON_LIBS_RPM) $(HOST_INSTALLER_RPMS) $(BIOSDEVNAME_RPM) $(GDISK_RPM); do \
		cp $$f $(INSTALLER_FILESYSTEM)/tmp ;\
		all="$$all /tmp/$$(basename $$f)" ;\
	done ;\
	$(INSTALLER_CHROOT) rpm -Uvh $$all ;\
	$(INSTALLER_CHROOT) rm -f $$all
	touch $(INSTALLER_FILESYSTEM)/etc/fstab
# prepare terminals to login
	sed -i -re 's!^ACTIVE_CONSOLES=.*!ACTIVE_CONSOLES=/dev/tty2!' $(INSTALLER_FILESYSTEM)/etc/sysconfig/init
	sed -i -re 's,^exec /sbin/mingetty .*,exec /sbin/agetty -n -l /bin/sh 38400 $$TTY,' $(INSTALLER_FILESYSTEM)/etc/init/tty.conf
	rm -f $(INSTALLER_FILESYSTEM)/etc/init/serial.conf
# init configuration to start our installer
	cp installer.conf log_tty.conf $(INSTALLER_FILESYSTEM)/etc/init/
# remove some not used script
	for f in lvm2-lvmetad lvm2-monitor netfs; do rm $(INSTALLER_FILESYSTEM)/etc/init.d/$$f; done
# enable network by default to make nfs start correctly
	echo -e 'NETWORKING=yes\nHOSTNAME=localhost.localdomain' > $(INSTALLER_FILESYSTEM)/etc/sysconfig/network
# TODO remove
# hack to not lock decives
	cp 40-multipath.rules $(INSTALLER_FILESYSTEM)/etc/udev/rules.d/40-multipath.rules
# some cleanup
	$(INSTALLER_CHROOT) rpm -e --nodeps groff
	cd $(INSTALLER_FILESYSTEM) && rm -rf usr/share/doc usr/share/man var/lib/yum usr/share/locale \
		var/cache usr/lib/locale var/lib/rpm var/cache/yum \
		usr/bin/info usr/bin/infokey usr/share/info sbin/install-info \
		usr/share/doc usr/share/groff usr/include/python* usr/local/share/man usr/local/share/info \
		etc/profile.d/less.csh etc/profile.d/less.sh usr/bin/lesspipe.sh
# cleanup all compiled Python to gain some space, python will compile if needed
	find $(INSTALLER_FILESYSTEM) \( -name \*.pyc -o -name \*.pyo \) -type f | while read f; do test -r "$${f%[co]}" && rm -f "$$f"; done
# remove duplicate in zoneinfo
	python remove_dups.py $(INSTALLER_FILESYSTEM)/usr/share/zoneinfo
	perl delete_bad_exes.pl $(INSTALLER_FILESYSTEM)
	@touch $@

$(FIRMWARE_INSTALLED_STAMP): $(FIRMWARE_RPMS_LIST)
	cat $(FIRMWARE_RPMS_LIST) | while read rpm; \
		do rpm2cpio $(PROJECT_OUTPUTDIR)/guest-packages-dom0/RPMS/noarch/$$rpm | \
		(cd $(INSTALLER_FILESYSTEM) && cpio -iudv ); done
	touch $@

$(INIT_CREATED_STAMP): $(BASE_IMAGE_STAMP)
	ln -f $(INSTALLER_FILESYSTEM)/sbin/init $(INSTALLER_FILESYSTEM)/init
	touch $@

$(PROC_ADDED_STAMP): $(BASE_IMAGE_STAMP)
	mkdir -p $(INSTALLER_FILESYSTEM)/proc
	mkdir -p $(INSTALLER_FILESYSTEM)/lib/firmware
	mkdir -p $(INSTALLER_FILESYSTEM)/{var/lib,var/lock,var/log,var/run}
	mkdir -p $(INSTALLER_FILESYSTEM)/tmp/lvm
	touch $@

###
# build installer stuff:

$(INSTALLER_INSTALLED_STAMP): $(BASE_IMAGE_STAMP)
# install scripts:
	rm -f $(INSTALLER_FILESYSTEM)/etc/init.d/{discover.init,S10udev,S50sshd,S40network}
	touch $@

# TODO still useful ??
# Actually collects
# /output/xen/INSTALLER_FILES (some strange python libraries)
# /output/guest-packages-linux-firmware/INSTALLER_FILES (firmware for cards, installed even above ??)
# /output/kernel-dom0/INSTALLER_FILES (modules)
# /output/uclibc-xen/INSTALLER_FILES (xeninfo utility)
$(FILES_COLLECTED_STAMP): $(BASE_IMAGE_STAMP)
	./collect-files $(INSTALLER_FILESYSTEM) $(PROJECT_OUTPUTDIR) INSTALLER_FILES
	ln -sf /lib/udev/scsi_id $(INSTALLER_FILESYSTEM)/sbin/scsi_id # symlink needed by multipath-tools
# remove duplicate modules
	python remove_dups.py $(INSTALLER_FILESYSTEM)/lib/firmware
	touch $@

$(KERNEL_CONFIGURED_STAMP): $(FILES_COLLECTED_STAMP)
	set -e; for k in `find $(INSTALLER_FILESYSTEM)/lib/modules -type d -name '*xs*'` ; do \
		$(INSTALLER_CHROOT) depmod `basename $$k` ; \
	done
	touch $@

$(INSTALL_IMG): $(INSTALLER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) $(FIRMWARE_INSTALLED_STAMP) \
		$(MY_OUTPUT_DIR)/.dirstamp
	rm -f $@
# Remove wifi and other firmware
	set -e; for d in $(INSTALLER_FILESYSTEM)/lib/modules/*; do \
		if [ -d "$$d" ]; then \
			cd "$$d" ;\
			rm -f iwlwifi* *.sbcf v4l* ;\
			rm -rf rtlwifi carl9170fw ti-connectivity ueagle-atm libertas ath6k brcm mrvl ;\
		fi ;\
	done
	perl clean_fw.pl $(INSTALLER_FILESYSTEM)
	$(call brand-python) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	$(call brand,$(CURDIR)/issue.in) > $(INSTALLER_FILESYSTEM)/etc/issue
	install -m644 /output/eulas/EULA_XENSERVER $(INSTALLER_FILESYSTEM)/opt/xensource/installer/EULA
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | sort | cpio -o -H newc | bzip2 -9c >$@
	chmod 644 $@

# Dell factory installation
$(BUILD_FI_IMAGE):
	$(MAKE) -C $(call hg_loc,host-installer)/oem install DESTDIR=$(MY_OUTPUT_DIR)
