USE_BRANDING := yes
include $(B_BASE)/common.mk

# inputs
BASE_INSTALLER_IMAGE = $(PROJECT_OUTPUTDIR)/install-image-base/rootfs.$(DOMAIN0_ARCH_OPTIMIZED).ext2
BUILDROOT_ENVIRONMENT = $(PROJECT_OUTPUTDIR)/install-image-base/buildroot-env.tar.gz

# outputs (install.img used by retail installer & recovery.img used by OEM installer)
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
RECOVERY_IMG = $(MY_OUTPUT_DIR)/recovery.img
SOURCES_MANIFEST = $(MY_SOURCES)/MANIFEST

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

# third party
DMIDECODE_BUILT_STAMP = $(MY_OBJ_DIR)/.dmidecode-built.stamp
DMIDECODE_TARBALL ?= $(MY_DISTFILES)/dmidecode-2.9.tar.gz
DMIDECODE_PKGNAME = $(shell basename $(DMIDECODE_TARBALL) | sed s/.tar.gz//)

# commands:
INSTALLER_CHROOT = chroot $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(RECOVERY_IMG) $(SOURCES_MANIFEST) $(MY_OUTPUT_DIR)/.dirstamp
	$(call mkdir_clean,$(MY_MAIN_CDFILES))
	cp -l $(INSTALL_IMG) $(MY_MAIN_CDFILES)
# Note: recovery.img behaves the same as install.img booted with "oem_edition" on kernel command line
# Todo: ditch recovery.img (requires CD and all PXE configs to put "oem_edition" on kernel command line)
	$(call mkdir_clean,$(MY_RECOVERY_CDFILES))
	cp -l $(RECOVERY_IMG) $(MY_RECOVERY_CDFILES)

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
# build third-party stuff:

# a version of dmidecode built against uClibc
$(DMIDECODE_BUILT_STAMP): $(BUILDROOT_ENV_STAMP) $(BASE_IMAGE_EXTRACTED_STAMP)
	rm -rf $(MY_OBJ_DIR)/$(DMIDECODE_PKGNAME)
	tar -C $(MY_OBJ_DIR) -xzf $(DMIDECODE_TARBALL)
	export PATH=$(BUILDROOT_DIR)/build_$(DOMAIN0_ARCH_OPTIMIZED)/staging_dir/bin:$${PATH} && \
	$(MAKE) -C $(MY_OBJ_DIR)/$(DMIDECODE_PKGNAME) CC=$(DOMAIN0_ARCH_OPTIMIZED)-linux-gcc
	cp $(MY_OBJ_DIR)/$(DMIDECODE_PKGNAME)/dmidecode $(INSTALLER_FILESYSTEM)/sbin/
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
		 $(DMIDECODE_BUILT_STAMP) $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(INSTALL_IMG)
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(INSTALL_IMG)
	chmod 644 $@

# Note: recovery.img behaves the same as install.img booted with "oem_edition" on kernel command line
# Todo: ditch recovery.img (requires CD and all PXE configs to put "oem_edition" on kernel command line)
$(RECOVERY_IMG): RECOVERY_FILESYSTEM=/obj/filesystem.oem
$(RECOVERY_IMG): $(INSTALLER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(ISSUE_CUSTOMISED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) \
		 $(DMIDECODE_BUILT_STAMP) $(MY_OUTPUT_DIR)/.dirstamp
	rm -f $(RECOVERY_IMG)
	cp -a $(INSTALLER_FILESYSTEM) $(RECOVERY_FILESYSTEM)
	touch $(RECOVERY_FILESYSTEM)/.oem_edition
	umask 022 && cd $(RECOVERY_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(RECOVERY_IMG)
	chmod 644 $@

SOURCES_PREFIX := $(COMPONENT) dfsg
$(SOURCES_MANIFEST):
	mkdir -p $(@D)
	( echo "$(SOURCES_PREFIX) file $(DMIDECODE_TARBALL)" ; \
	  ) >$@
