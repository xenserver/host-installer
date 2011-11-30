USE_BRANDING := yes
include $(B_BASE)/common.mk
include $(PROJECT_OUTPUTDIR)/python-libs/python-libs.inc

# inputs
BASE_INSTALLER_IMAGE = $(PROJECT_OUTPUTDIR)/install-image-base/rootfs.$(DOMAIN0_ARCH_OPTIMIZED).ext2
PYTHON_LIBS_RPM := $(PROJECT_OUTPUTDIR)/python-libs/$(PYTHON_LIBS_PKG_FILE)

# outputs
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
INSTALL_IMG_XCP = $(MY_OUTPUT_DIR)/install.xcp.img
MBOOT_IMG = $(MY_OUTPUT_DIR)/mboot.img
BUILD_FI_IMAGE = $(MY_OUTPUT_DIR)/build-fi-image.sh

# intermediate:
KERNEL_CONFIGURED_STAMP = $(MY_OBJ_DIR)/.kernel-configured.stamp
BASE_IMAGE_EXTRACTED_STAMP = $(MY_OBJ_DIR)/.base-image-extracted.stamp
PYTHON_LIBS_INSTALLED_STAMP = $(MY_OBJ_DIR)/.python-libs-installed.stamp
INSTALLER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.installer-installed.stamp
FILES_COLLECTED_STAMP = $(MY_OBJ_DIR)/.files-collected.stamp
INIT_CREATED_STAMP = $(MY_OBJ_DIR)/.init-created.stamp
PROC_ADDED_STAMP = $(MY_OBJ_DIR)/.proc-added.stamp

INSTALLER_FILESYSTEM = $(MY_OBJ_DIR)/filesystem

# commands:
INSTALLER_CHROOT = chroot $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(INSTALL_IMG_XCP) $(MBOOTPACK) $(BUILD_FI_IMAGE) $(MY_OUTPUT_DIR)/.dirstamp
	$(MAKE) -C $(call hg_loc,host-installer)/upgrade-plugin $@
	$(call mkdir_clean,$(MY_MAIN_CDFILES))
	cp -l $(INSTALL_IMG) $(MY_MAIN_CDFILES)
	zcat $(PROJECT_OUTPUTDIR)/xen/CD_FILES.main/boot/xen.gz >$(MY_OBJ_DIR)/xen
	zcat $(PROJECT_OUTPUTDIR)/kernel-dom0/CD_FILES.main/boot/vmlinuz >$(MY_OBJ_DIR)/vmlinux
	mbootpack -o $(MBOOT_IMG) $(MY_OBJ_DIR)/xen -m $(MY_OBJ_DIR)/vmlinux -m $(INSTALL_IMG)
	rm -f $(MY_OBJ_DIR)/xen $(MY_OBJ_DIR)/vmlinux

$(BASE_IMAGE_EXTRACTED_STAMP): $(BASE_INSTALLER_IMAGE)
	./extract-fs $(BASE_INSTALLER_IMAGE) $(INSTALLER_FILESYSTEM)
	touch $@

$(PYTHON_LIBS_INSTALLED_STAMP): $(PYTHON_LIBS_RPM)
	rpm2cpio $^ | ( cd $(INSTALLER_FILESYSTEM) && cpio -idv )
	touch $@

$(INIT_CREATED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	ln -f $(INSTALLER_FILESYSTEM)/bin/busybox $(INSTALLER_FILESYSTEM)/init
	touch $@

$(PROC_ADDED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	mkdir -p $(INSTALLER_FILESYSTEM)/proc
	mkdir -p $(INSTALLER_FILESYSTEM)/lib/firmware
	mkdir -p $(INSTALLER_FILESYSTEM)/{var/lib,var/lock,var/log,var/run}
	mkdir -p $(INSTALLER_FILESYSTEM)/tmp/lvm
	touch $@

###
# build installer stuff:

$(INSTALLER_INSTALLED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
# install scripts:
	$(MAKE) -C $(call hg_loc,host-installer) install DESTDIR=$(INSTALLER_FILESYSTEM)
	$(MAKE) -C $(call hg_loc,host-installer)/startup install DESTDIR=$(INSTALLER_FILESYSTEM)
	rm -f $(INSTALLER_FILESYSTEM)/etc/init.d/{discover.init,S10udev,S50sshd,S40network}
	touch $@

$(FILES_COLLECTED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	./collect-files $(INSTALLER_FILESYSTEM) $(PROJECT_OUTPUTDIR) INSTALLER_FILES
	ln -sf /lib/udev/scsi_id $(INSTALLER_FILESYSTEM)/sbin/scsi_id # symlink needed by multipath-tools
	touch $@

$(KERNEL_CONFIGURED_STAMP): $(FILES_COLLECTED_STAMP)
	set -e; for k in `find $(INSTALLER_FILESYSTEM)/lib/modules -type d -name '2.6.*'` ; do \
		$(INSTALLER_CHROOT) depmod `basename $$k` ; \
	done
	touch $@

$(INSTALL_IMG): $(INSTALLER_INSTALLED_STAMP) $(PYTHON_LIBS_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) \
		 $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(INSTALL_IMG)
	$(call brand-python) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	$(call brand,$(CURDIR)/issue.in) > $(INSTALLER_FILESYSTEM)/etc/issue
	install -m644 /output/eulas/EULA_XENSERVER $(INSTALLER_FILESYSTEM)/opt/xensource/installer/EULA
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(INSTALL_IMG)
	chmod 644 $@

$(INSTALL_IMG_XCP): $(INSTALLER_INSTALLED_STAMP) $(PYTHON_LIBS_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(INIT_CREATED_STAMP) \
	$(PROC_ADDED_STAMP) $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(INSTALL_IMG_XCP)
	$(call brand-python-xcp) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	$(call brand-xcp,$(CURDIR)/issue.in) > $(INSTALLER_FILESYSTEM)/etc/issue
	install -m644 /output/eulas/EULA_XCP $(INSTALLER_FILESYSTEM)/opt/xensource/installer/EULA
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(INSTALL_IMG_XCP)
	chmod 644 $@

# Dell factory installation
$(BUILD_FI_IMAGE):
	$(MAKE) -C $(call hg_loc,host-installer)/oem install DESTDIR=$(MY_OUTPUT_DIR)
