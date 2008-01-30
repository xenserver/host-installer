USE_BRANDING := yes
include $(B_BASE)/common.mk

# inputs
BASE_INSTALLER_IMAGE = $(PROJECT_OUTPUTDIR)/install-image-base/rootfs.$(DOMAIN0_ARCH_OPTIMIZED).ext2
BUILDROOT_ENVIRONMENT = $(PROJECT_OUTPUTDIR)/install-image-base/buildroot-env.tar.gz
DEBIAN_DISCOVER_TARBALL ?= discover1_1.7.18.tar.gz
DEBIAN_DISCOVER_DATA_TARBALL ?= discover1-data_1.2006.01.14.tar.gz
DEBIAN_USB_DISCOVER_TARBALL ?= usb-discover_1.05.tar.gz

# outputs
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
SOURCES_MANIFEST = $(MY_SOURCES)/MANIFEST

# intermediate:
BUILDROOT_ENV_STAMP = $(MY_OBJ_DIR)/.buildroot-env.stamp
DISCOVER_BUILT_STAMP = $(MY_OBJ_DIR)/.discover-built.stamp
DISCOVER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.discover-installed.stamp
USB_DISCOVER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.usb-discover-installed.stamp
KERNEL_CONFIGURED_STAMP = $(MY_OBJ_DIR)/.kernel-configured.stamp
BASE_IMAGE_EXTRACTED_STAMP = $(MY_OBJ_DIR)/.base-image-extracted.stamp
INSTALLER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.installer-installed.stamp
FILES_COLLECTED_STAMP = $(MY_OBJ_DIR)/.files-collected.stamp
ISSUE_CUSTOMISED_STAMP = $(MY_OBJ_DIR)/.issue-customised.stamp
INIT_CREATED_STAMP = $(MY_OBJ_DIR)/.init-created.stamp
PROC_ADDED_STAMP = $(MY_OBJ_DIR)/.proc-added.stamp

USB_DISCOVER_DIR = $(MY_OBJ_DIR)/usb-discover
DISCOVER_DATA_DIR ?= $(MY_OBJ_DIR)/discover1-data-1.2006.01.14
BUILDROOT_DIR = $(MY_OBJ_DIR)/repos/dist-buildroot.hg
INSTALLER_FILESYSTEM = $(MY_OBJ_DIR)/filesystem

# commands:
INSTALLER_CHROOT = $(CHROOT) $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(SOURCES_MANIFEST) $(MY_OUTPUT_DIR)/.dirstamp
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
	touch $@

###
# build third-party stuff:

$(DISCOVER_BUILT_STAMP): $(BUILDROOT_ENV_STAMP)
# extract/patch:
	tar -C $(MY_OBJ_DIR) -xzf $(MY_DISTFILES)/$(DEBIAN_DISCOVER_TARBALL)
	patch -p0 -d $(MY_OBJ_DIR)/discover1 <$(CURDIR)/discover-uclibc.patch
# build:
	export PATH=$(BUILDROOT_DIR)/build_$(DOMAIN0_ARCH_OPTIMIZED)/staging_dir/bin:$${PATH} && \
	export CC=$(DOMAIN0_ARCH_OPTIMIZED)-linux-gcc && \
	cd $(MY_OBJ_DIR)/discover1 && \
	./configure --host=$(DOMAIN0_ARCH_OPTIMIZED)-linux-gnu --disable-nls --prefix=/usr \
		--sbindir=/sbin \
                --sysconfdir=/etc \
                --libdir=/lib \
                --mandir=\$${prefix}/share/man \
                --infodir=\$${prefix}/share/info && $(MAKE)
	touch $@

$(INSTALLER_INSTALLED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP) $(BUILDROOT_ENV_STAMP)
# install scripts:
	$(MAKE) -C $(call hg_loc,host-installer) install DESTDIR=$(INSTALLER_FILESYSTEM)
	$(MAKE) -C $(call hg_loc,host-installer)/p2v install DESTDIR=$(INSTALLER_FILESYSTEM)
	$(MAKE) -C $(call hg_loc,host-installer)/startup install DESTDIR=$(INSTALLER_FILESYSTEM)
# make /sbin/dhclient symlink so ifup does the right thing:
	#ln -sf /usr/sbin/dhclient ${INSTALLER_FILESYSTEM}/sbin/dhclient
# make version.py: (XXX should be a separate target):
	$(call brand-python) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	rm -f $(INSTALLER_FILESYSTEM)/etc/init.d/{discover.init,S50sshd,S40network}
	touch $@

$(DISCOVER_INSTALLED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP) $(DISCOVER_BUILT_STAMP)
	$(MAKE) -C $(MY_OBJ_DIR)/discover1 install DESTDIR=$(INSTALLER_FILESYSTEM)
	tar -C $(MY_OBJ_DIR) -xzf $(MY_DISTFILES)/$(DEBIAN_DISCOVER_DATA_TARBALL)
	tar -C $(MY_OBJ_DIR) -xzf $(MY_DISTFILES)/$(DEBIAN_USB_DISCOVER_TARBALL)
	$(MAKE) -C $(DISCOVER_DATA_DIR) install DESTDIR=$(INSTALLER_FILESYSTEM) prefix=/usr/share
	@mkdir -p $(INSTALLER_FILESYSTEM)/usr/lib/usb-discover
	$(MAKE) -C $(USB_DISCOVER_DIR) install DESTDIR=$(INSTALLER_FILESYSTEM)/usr/lib/usb-discover DISCDB=$(INSTALLER_FILESYSTEM)/usr/share/discover/pci.lst
	cp $(USB_DISCOVER_DIR)/usb-discover $(INSTALLER_FILESYSTEM)/usr/sbin/
	touch $@

$(FILES_COLLECTED_STAMP): $(BASE_IMAGE_EXTRACTED_STAMP)
	./collect-files $(INSTALLER_FILESYSTEM) $(PROJECT_OUTPUTDIR) INSTALLER_FILES
	touch $@

$(KERNEL_CONFIGURED_STAMP): $(FILES_COLLECTED_STAMP)
	set -e; for k in `find $(INSTALLER_FILESYSTEM)/lib/modules -type d -name '2.6.*'` ; do \
		$(INSTALLER_CHROOT) depmod `basename $$k` ; \
	done
	touch $@

$(INSTALL_IMG): $(INSTALLER_INSTALLED_STAMP) $(DISCOVER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(ISSUE_CUSTOMISED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP)
	rm -f $(INSTALL_IMG)
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | cpio -o -H newc | gzip -9c >$(INSTALL_IMG)
	chmod 644 $@

SOURCES_PREFIX := install-image dfsg
$(SOURCES_MANIFEST):
	mkdir -p $(@D)
	( echo "$(SOURCES_PREFIX) file $(MY_DISTFILES)/$(DEBIAN_DISCOVER_TARBALL)" ; \
	  echo "$(SOURCES_PREFIX) file $(MY_DISTFILES)/$(DEBIAN_DISCOVER_DATA_TARBALL)" ; \
	  echo "$(SOURCES_PREFIX) file $(MY_DISTFILES)/$(DEBIAN_USB_DISCOVER_TARBALL)" ; \
	  ) >$@
