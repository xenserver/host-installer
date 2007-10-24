include $(B_BASE)/common.mk

# input 
BUILDROOT_ENVIRONMENT = $(PROJECT_OUTPUTDIR)/install-image-base/buildroot-env.tar.gz

# config
KBD_VERSION = 1.12
KBD_DIR = $(MY_OBJ_DIR)/kbd-$(KBD_VERSION)
BUILDROOT_DIR = $(MY_OBJ_DIR)/repos/dist-buildroot.hg

UCLIBC_VARS :=
UCLIBC_VARS += PATH=$(BUILDROOT_DIR)/build_i686/staging_dir/bin:$${PATH}
UCLIBC_VARS += CC=i686-linux-gcc

REMOVE = consolefonts consoletrans man

# intermediate
EXTRACT_COOKIE = $(MY_OBJ_DIR)/.extract.cookie
BUILDROOT_ENV_COOKIE = $(MY_OBJ_DIR)/.buildroot-env.cookie
PATCH_COOKIE = $(MY_OBJ_DIR)/.patch.cookie
BUILD_COOKIE = $(MY_OBJ_DIR)/.build.cookie
INSTALL_COOKIE = $(MY_OBJ_DIR)/.install.cookie

.PHONY: build
build: $(INSTALL_COOKIE)
	@ :

$(EXTRACT_COOKIE): $(MY_DISTFILES)/kbd_$(KBD_VERSION).orig.tar.gz
	tar -C $(MY_OBJ_DIR) -xzf $<
	touch $@

$(BUILDROOT_ENV_COOKIE): $(BUILDROOT_ENVIRONMENT)
	@echo "Extracting $(BUILDROOT_ENVIRONMENT)..."
	tar -C $(MY_OBJ_DIR) -xzf $<
	touch $@

$(PATCH_COOKIE): $(EXTRACT_COOKIE) 01_locale_h.patch
	patch -p1 -d$(KBD_DIR) <01_locale_h.patch

$(BUILD_COOKIE): $(PATCH_COOKIE) $(BUILDROOT_ENV_COOKIE)
	cd $(KBD_DIR) && \
	env $(UCLIBC_VARS) ./configure --disable-nls
	rm -f $(KBD_DIR)/defines.h && touch $(KBD_DIR)/defines.h
	$(MAKE) -C $(KBD_DIR) $(UCLIBC_VARS) all
	touch $@

$(INSTALL_COOKIE): $(BUILD_COOKIE)
	mkdir -p $(MY_INSTALLER_FILES)
	$(MAKE) -C $(KBD_DIR) $(UCLIBC_VARS) DESTDIR=$(MY_INSTALLER_FILES) install
# remove some cruft now
	rm -rf $(addprefix $(MY_INSTALLER_FILES)/usr/share/kbd/,$(REMOVE))
	rm -rf $(MY_INSTALLER_FILES)/usr/share/man
	rm -rf $(MY_INSTALLER_FILES)/usr/bin
	touch $@
