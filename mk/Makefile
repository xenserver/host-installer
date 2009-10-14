USE_BRANDING := yes
include $(B_BASE)/common.mk

# inputs
BASE_INSTALLER_IMAGE = $(PROJECT_OUTPUTDIR)/install-image-base/rootfs.$(DOMAIN0_ARCH_OPTIMIZED).ext2
BUILDROOT_ENVIRONMENT = $(PROJECT_OUTPUTDIR)/install-image-base/buildroot-env.tar.gz

# outputs (install.img used by retail installer & recovery.img used by OEM installer)
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
RECOVERY_IMG = $(MY_OUTPUT_DIR)/recovery.img
UPDATE_INITRD = $(MY_OUTPUT_DIR)/update-initrd
MBOOTPACK = $(MY_OUTPUT_DIR)/mbootpack
BUILD_FI_IMAGE = $(MY_OUTPUT_DIR)/build-fi-image.sh

# intermediate:
BUILDROOT_ENV_STAMP = $(MY_OBJ_DIR)/.buildroot-env.stamp
KERNEL_CONFIGURED_STAMP = $(MY_OBJ_DIR)/.kernel-configured.stamp
BASE_IMAGE_EXTRACTED_STAMP = $(MY_OBJ_DIR)/.base-image-extracted.stamp
INSTALLER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.installer-installed.stamp
FILES_COLLECTED_STAMP = $(MY_OBJ_DIR)/.files-collected.stamp
ISSUE_CUSTOMISED_STAMP = $(MY_OBJ_DIR)/.issue-customised.stamp
INIT_CREATED_STAMP = $(MY_OBJ_DIR)/.init-created.stamp
PROC_ADDED_STAMP = $(MY_OBJ_DIR)/.proc-added.stamp

BUILDROOT_DIR = $(MY_OBJ_DIR)/repos/dist-buildroot.hg
INSTALLER_FILESYSTEM = $(MY_OBJ_DIR)/filesystem

# commands:
INSTALLER_CHROOT = chroot $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(UPDATE_INITRD) $(MBOOTPACK) $(BUILD_FI_IMAGE) $(MY_OUTPUT_DIR)/.dirstamp
	$(call mkdir_clean,$(MY_MAIN_CDFILES))
	cp -l $(INSTALL_IMG) $(MY_MAIN_CDFILES)

$(BUILDROOT_ENV_STAMP): $(BUILDROOT_ENVIRONMENT)
	@echo "Extracting $(BUILDROOT_ENVIRONMENT)..."
	tar -C $(MY_OBJ_DIR) -xzf $(BUILDROOT_ENVIRONMENT)
	@touch $@

$(BASE_IMAGE_EXTRACTED_STAMP): $(BASE_INSTALLER_IMAGE)
	./extract-fs $(BASE_INSTALLER_IMAGE) $(INSTALLER_FILESYSTEM)
	touch $@

$(ISSUE_CUSTOMISED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	$(call brand,$(CURDIR)/issue.in) > $(INSTALLER_FILESYSTEM)/etc/issue
	touch $@

$(INIT_CREATED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	ln $(INSTALLER_FILESYSTEM)/bin/busybox $(INSTALLER_FILESYSTEM)/init
	touch $@

$(PROC_ADDED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	mkdir $(INSTALLER_FILESYSTEM)/proc
	mkdir -p $(INSTALLER_FILESYSTEM)/lib/firmware
	mkdir -p $(INSTALLER_FILESYSTEM)/{var/lib,var/lock,var/log,var/run}
	mkdir -p $(INSTALLER_FILESYSTEM)/tmp/lvm
	touch $@

###
# build installer stuff:

$(INSTALLER_INSTALLED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP) $(BUILDROOT_ENV_STAMP)
# install scripts:
	$(MAKE) -C $(call hg_loc,host-installer) install DESTDIR=$(INSTALLER_FILESYSTEM)
	$(MAKE) -C $(call hg_loc,host-installer)/p2v install DESTDIR=$(INSTALLER_FILESYSTEM)
	$(MAKE) -C $(call hg_loc,host-installer)/startup install DESTDIR=$(INSTALLER_FILESYSTEM)
# make version.py: (XXX should be a separate target):
	$(call brand-python) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	rm -f $(INSTALLER_FILESYSTEM)/etc/init.d/{discover.init,S10udev,S50sshd,S40network}
	touch $@

$(FILES_COLLECTED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	./collect-files $(INSTALLER_FILESYSTEM) $(PROJECT_OUTPUTDIR) INSTALLER_FILES
	touch $@

$(KERNEL_CONFIGURED_STAMP): $(FILES_COLLECTED_STAMP)
	set -e; for k in `find $(INSTALLER_FILESYSTEM)/lib/modules -type d -name '2.6.*'` ; do \
		$(INSTALLER_CHROOT) depmod `basename $$k` ; \
	done
	touch $@

$(INSTALL_IMG): $(INSTALLER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(ISSUE_CUSTOMISED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) \
		 $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(INSTALL_IMG)
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(INSTALL_IMG)
	chmod 644 $@

# Note: recovery.img behaves the same as install.img booted with "oem_edition" on kernel command line
# Todo: ditch recovery.img (requires CD and all PXE configs to put "oem_edition" on kernel command line)
$(RECOVERY_IMG): RECOVERY_FILESYSTEM=/obj/filesystem.oem
$(RECOVERY_IMG): $(INSTALLER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(ISSUE_CUSTOMISED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) \
		 $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(RECOVERY_IMG)
	cp -a $(INSTALLER_FILESYSTEM) $(RECOVERY_FILESYSTEM)
	touch $(RECOVERY_FILESYSTEM)/.oem_edition
	umask 022 && cd $(RECOVERY_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(RECOVERY_IMG)
	chmod 644 $@

# We copy out the update-initrd script so that it can be placed into the oem filesystem
# where it is also required.
$(UPDATE_INITRD):
	cp ../oem/update-initrd $@

# Dell factory installation
$(MBOOTPACK):
	$(call mkdir_clean,$(MY_OBJ_DIR)/mbootpack)
	( cd $(call hg_loc,host-installer)/mbootpack && find . -type f | cpio -dp $(MY_OBJ_DIR)/mbootpack )
	$(MAKE) -C $(MY_OBJ_DIR)/mbootpack
	cp -fp $(MY_OBJ_DIR)/mbootpack/mbootpack $@

$(BUILD_FI_IMAGE):
	$(MAKE) -C $(call hg_loc,host-installer)/oem install DESTDIR=$(MY_OUTPUT_DIR)
