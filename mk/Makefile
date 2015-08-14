USE_BRANDING := yes
include $(B_BASE)/common.mk
include $(PROJECT_OUTPUTDIR)/kernel-dom0/kernel.inc

# inputs
YUM_CONF := $(PROJECT_OUTPUTDIR)/chroot-dom0/yum.conf
DRIVER_RPMS_LIST := $(PROJECT_OUTPUTDIR)/driver-disks/packages.installer

# outputs
INSTALL_IMG = $(MY_OUTPUT_DIR)/install.img
MBOOT_IMG = $(MY_OUTPUT_DIR)/mboot.img
BUILD_FI_IMAGE = $(MY_OUTPUT_DIR)/build-fi-image.sh

# intermediate:
PKG_LIST := $(MY_OBJ_DIR)/pkgs.txt
KERNEL_CONFIGURED_STAMP = $(MY_OBJ_DIR)/.kernel-configured.stamp
BASE_IMAGE_STAMP := $(MY_OBJ_DIR)/.base-image.stamp
BASE_IMAGE := $(MY_OBJ_DIR)/base-image.tar.gz
INSTALLER_INSTALLED_STAMP = $(MY_OBJ_DIR)/.installer-installed.stamp
FILES_COLLECTED_STAMP = $(MY_OBJ_DIR)/.files-collected.stamp
INIT_CREATED_STAMP = $(MY_OBJ_DIR)/.init-created.stamp
PROC_ADDED_STAMP = $(MY_OBJ_DIR)/.proc-added.stamp
REPO_STAMP = $(MY_OBJ_DIR)/.repo.stamp

INSTALLER_FILESYSTEM = $(MY_OBJ_DIR)/filesystem

# commands:
INSTALLER_CHROOT = chroot $(INSTALLER_FILESYSTEM)

.PHONY: build
build: $(INSTALL_IMG) $(MBOOTPACK) $(BUILD_FI_IMAGE) $(MY_OUTPUT_DIR)/.dirstamp
	$(MAKE) -C $(call hg_loc,host-installer)/upgrade-plugin $@
	$(call mkdir_clean,$(MY_MAIN_CDFILES))
	cp -l $(INSTALL_IMG) $(MY_MAIN_CDFILES)
	zcat $(PROJECT_OUTPUTDIR)/xen/CD_FILES.main/boot/xen.gz >$(MY_OBJ_DIR)/xen
	zcat $(PROJECT_OUTPUTDIR)/kernel-dom0/CD_FILES.main/boot/vmlinux.gz >$(MY_OBJ_DIR)/vmlinux
	mbootpack -o $(MBOOT_IMG) $(MY_OBJ_DIR)/xen -m $(MY_OBJ_DIR)/vmlinux -m $(INSTALL_IMG)
	rm -f $(MY_OBJ_DIR)/xen $(MY_OBJ_DIR)/vmlinux

$(REPO_STAMP):
	rm -rf $(MY_OBJ_DIR)/repos/xenserver
	mkdir -p $(MY_OBJ_DIR)/repos/xenserver
	set -e; for comp in $(DDEPS); do \
		d="$(PROJECT_OUTPUTDIR)/$$comp/RPMS" ;\
		if [ -d "$$d" ]; then \
			ln -sf $$(find "$$d" -name \*.rpm -type f) $(MY_OBJ_DIR)/repos/xenserver ;\
		fi ;\
	done
	createrepo $(MY_OBJ_DIR)/repos/xenserver
	@touch $@

$(PKG_LIST): pkgs.txt $(DRIVER_RPMS_LIST)
	cat $^ >$@

$(BASE_IMAGE): $(YUM_CONF) $(PKG_LIST) $(REPO_STAMP)
	{ cat $(YUM_CONF) ;\
	echo -e "\n[xenserver]\nname=xenserver\nenabled=1\ngpgcheck=0\nbaseurl=file://$(MY_OBJ_DIR)/repos/xenserver\n" ;\
	} | sed -r '/\[base\]|\[updates\]/a\exclude=kernel-xen* *xen* linux-firmware biosdevname' > $(MY_OBJ_DIR)/yum.conf
	rm -rf $(INSTALLER_FILESYSTEM)
	yum --nogpgcheck --config=$(MY_OBJ_DIR)/yum.conf --installroot=$(INSTALLER_FILESYSTEM) install -v $$(sed -r 's/^ +//; /^#|^$$/d' < $(PKG_LIST))
	tar -C $(INSTALLER_FILESYSTEM) -zcf $@.tmp .
	mv -f $@.tmp $@

$(BASE_IMAGE_STAMP): $(BASE_IMAGE)
	rm -rf $(INSTALLER_FILESYSTEM)
	mkdir $(INSTALLER_FILESYSTEM)
	tar -C $(INSTALLER_FILESYSTEM) -zxf $<
	touch $(INSTALLER_FILESYSTEM)/etc/fstab
# prepare terminals to login
	rm -f $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants/getty@tty1.service'
	ln -s /dev/null $(INSTALLER_FILESYSTEM)'/etc/systemd/system/serial-getty@hvc0.service'
	mkdir -p $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants'
# remove the dom0 configuration which disables the getty on tty2
	rm -f $(INSTALLER_FILESYSTEM)/etc/systemd/system/getty@tty2.service
	cp getty@tty2.service $(INSTALLER_FILESYSTEM)/etc/systemd/system
	ln -s /etc/systemd/system/getty@tty2.service $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants/getty@tty2.service'
# init configuration to start our installer
	cp installer.service $(INSTALLER_FILESYSTEM)/etc/systemd/system
	ln -s /etc/systemd/system/installer.service $(INSTALLER_FILESYSTEM)'/etc/systemd/system/multi-user.target.wants/installer.service'
# Disable some services and udev rules
	rm -f $(INSTALLER_FILESYSTEM)/etc/systemd/system/sockets.target.wants/lvm2-lvmetad.socket
	sed -i 's/use_lvmetad = 1/use_lvmetad = 0/' $(INSTALLER_FILESYSTEM)/etc/lvm/lvm.conf
	ln -sf /dev/null $(INSTALLER_FILESYSTEM)/etc/udev/rules.d/11-dm-mpath.rules
	ln -sf /dev/null $(INSTALLER_FILESYSTEM)/etc/udev/rules.d/62-multipath.rules
	ln -sf /dev/null $(INSTALLER_FILESYSTEM)/etc/udev/rules.d/69-dm-lvm-metad.rules
# Prevent lvm from automatically activating volumes on boot
	ln -s /etc/systemd/system/lvm2-activation.service $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants/lvm2-activation.service'
	ln -s /etc/systemd/system/lvm2-activation-early.service $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants/lvm2-activation-early.service'
	ln -s /etc/systemd/system/lvm2-activation-net.service $(INSTALLER_FILESYSTEM)'/etc/systemd/system/getty.target.wants/lvm2-activation-net.service'
# enable network by default to make nfs start correctly
	echo -e 'NETWORKING=yes\nHOSTNAME=localhost.localdomain' > $(INSTALLER_FILESYSTEM)/etc/sysconfig/network
# TODO remove
# hack to not lock decives
	cp 40-multipath.rules $(INSTALLER_FILESYSTEM)/etc/udev/rules.d/40-multipath.rules
# some cleanup
	$(INSTALLER_CHROOT) rpm -e --nodeps pkgconfig perl perl-Carp perl-Encode perl-Exporter perl-File-Path perl-File-Temp perl-Filter perl-Getopt-Long perl-HTTP-Tiny perl-PathTools perl-Pod-Escapes perl-Pod-Perldoc perl-Pod-Simple perl-Pod-Usage perl-Scalar-List-Utils perl-Socket perl-Storable perl-Text-ParseWords perl-Time-Local perl-constant perl-libs perl-macros perl-parent perl-podlators perl-threads perl-threads-shared xen-hypervisor groff-base iptables
	cd $(INSTALLER_FILESYSTEM) && rm -rf usr/share/doc usr/share/man var/lib/yum usr/share/locale \
		var/cache usr/lib/locale var/lib/rpm var/cache/yum \
		usr/bin/info usr/bin/infokey usr/share/info sbin/install-info \
		usr/share/doc usr/share/groff usr/include/python* usr/local/share/man usr/local/share/info \
		etc/profile.d/less.csh etc/profile.d/less.sh usr/bin/lesspipe.sh \
		usr/share/i18n/locales usr/share/perl5 usr/lib64/perl5 usr/bin/perl* \
		boot/* usr/share/bash-completion usr/lib/modules/3.10.0+0/kernel/fs/{btrfs,cifs,cramfs,exofs,jfs,nfsd,ntfs,ocfs2,reiserfs,xfs} \
		usr/lib/modules/3.10.0+0/kernel/drivers/infiniband usr/share/cracklib \
		usr/sbin/{cache_restore,thin_dump,thin_repair,cache_repair,cache_dump,thin_restore,cache_check,era_dump,era_invalidate,thin_rmap,era_check,thin_check} \
		usr/sbin/{glibc_post_upgrade.x86_64,ldconfig} \
		usr/share/doc usr/sbin/oxenstored opt/xensource/bin/xenstored \
		usr/lib/dracut usr/lib/systemd/system/initrd.target.wants usr/lib/systemd/system/shutdown.target.wants \
		usr/lib/systemd/system/dracut-*.service usr/lib/kernel/install.d/50-dracut.install etc/dracut.conf* \
		usr/bin/{dracut,lsinitrd,mkinitrd} usr/sbin/dracut var/lib/initramfs \
		usr/libexec/fcoe etc/fcoe etc/sysconfig/fcoe
# cleanup all compiled Python to gain some space, python will compile if needed
	find $(INSTALLER_FILESYSTEM) \( -name \*.pyc -o -name \*.pyo \) -type f | while read f; do test -r "$${f%[co]}" && rm -f "$$f"; done
# remove duplicate in zoneinfo
	python remove_dups.py $(INSTALLER_FILESYSTEM)/usr/share/zoneinfo
	perl delete_bad_exes.pl $(INSTALLER_FILESYSTEM)
	@touch $@

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

# Actually collects
# /output/guest-packages-linux-firmware/INSTALLER_FILES (firmware for cards, installed even above ??)
# /output/kernel-dom0/INSTALLER_FILES (modules)
$(FILES_COLLECTED_STAMP): $(BASE_IMAGE_STAMP)
	ln -sf /lib/udev/scsi_id $(INSTALLER_FILESYSTEM)/sbin/scsi_id # symlink needed by multipath-tools
# remove duplicate modules
	python remove_dups.py $(INSTALLER_FILESYSTEM)/lib/firmware
	touch $@

$(KERNEL_CONFIGURED_STAMP): $(FILES_COLLECTED_STAMP)
	$(INSTALLER_CHROOT) depmod $(LINUX_KABI_VERSION)
	touch $@

$(MY_OBJ_DIR)/EULA: $(wildcard $(PROJECT_OUTPUTDIR)/xenserver-docs/RPMS/noarch/xenserver-docs-[0-9]*.rpm)
	( cd $(MY_OBJ_DIR) ; rpm2cpio $^ | cpio -idv )

$(INSTALL_IMG): $(INSTALLER_INSTALLED_STAMP) $(KERNEL_CONFIGURED_STAMP) $(INIT_CREATED_STAMP) $(PROC_ADDED_STAMP) $(MY_OUTPUT_DIR)/.dirstamp \
	$(MY_OBJ_DIR)/EULA
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
# strip all kernel modules
	find $(INSTALLER_FILESYSTEM)/lib/modules -name \*.ko -type f -exec strip --strip-unneeded {} \;
	$(call brand-python) > $(INSTALLER_FILESYSTEM)/opt/xensource/installer/version.py
	$(call brand,$(CURDIR)/issue.in) > $(INSTALLER_FILESYSTEM)/etc/issue
	install -m644 $(MY_OBJ_DIR)/EULA $(INSTALLER_FILESYSTEM)/opt/xensource/installer/EULA
	umask 022 && cd $(INSTALLER_FILESYSTEM) && find . | sort | cpio -o -H newc | bzip2 -9c >$@
	chmod 644 $@

# Dell factory installation
$(BUILD_FI_IMAGE):
	$(MAKE) -C $(call hg_loc,host-installer)/oem install DESTDIR=$(MY_OUTPUT_DIR)
