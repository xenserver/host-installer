USE_BRANDING := yes
IMPORT_BRANDING := yes
# makefile for the host installer components in build system
include $(B_BASE)/common.mk
include $(B_BASE)/rpmbuild.mk

# For debugging
.PHONY: %var
%var:
        @echo "$* = $($*)"

REPO_NAME := host-installer
SPEC_FILE := $(REPO_NAME).spec
RPM_BUILD_COOKIE := $(MY_OBJ_DIR)/.rpm_build_cookie
REPO_STAMP := $(call hg_req,$(REPO_NAME))

$(eval $(shell $(call hg_cset_number,$(REPO_NAME)))) # Defines CSET_NUMBER for us
HOST_INSTALLER_VERSION := xs$(PLATFORM_VERSION).$(CSET_NUMBER)
HOST_INSTALLER_RELEASE := 1
HOST_INSTALLER_DIR := /opt/xensource/installer


.PHONY: build
build: $(RPM_BUILD_COOKIE) $(MY_OUTPUT_DIR)/host-installer.inc
	@ :


SOURCES := $(RPM_SOURCESDIR)/host-installer-$(HOST_INSTALLER_VERSION).tar.bz2
SOURCES += $(RPM_SPECSDIR)/$(SPEC_FILE)

HOST_INSTALLER_HG_EXCLUDE := -X mk -X tests -X oem -X upgrade-plugin -X sample-version.py
$(RPM_SOURCESDIR)/host-installer-$(HOST_INSTALLER_VERSION).tar.bz2: $(RPM_SOURCESDIRSTAMP)
	{ set -e; set -o pipefail; \
	hg -R "$(call hg_loc,$(REPO_NAME))" archive $(HOST_INSTALLER_HG_EXCLUDE) \
	-p host-installer-$(HOST_INSTALLER_VERSION) -t tbz2 $@.tmp; \
	mv -f $@.tmp $@; \
	}

$(RPM_SPECSDIR)/$(SPEC_FILE): $(SPEC_FILE).in $(RPM_SPECSDIRSTAMP)
	{ set -e; set -o pipefail; \
	sed -e s/@HOST_INSTALLER_VERSION@/$(HOST_INSTALLER_VERSION)/g \
	    -e s/@HOST_INSTALLER_RELEASE@/$(HOST_INSTALLER_RELEASE)/g \
	    -e s!@HOST_INSTALLER_DIR@!$(HOST_INSTALLER_DIR)!g \
	< $< > $@.tmp; \
	mv -f $@.tmp $@; \
	}

$(RPM_BUILD_COOKIE): $(RPM_DIRECTORIES) $(SOURCES)
	$(RPMBUILD) -ba $(RPM_SPECSDIR)/$(SPEC_FILE)
	touch $@

.PHONY: $(MY_OUTPUT_DIR)/host-installer.inc
$(MY_OUTPUT_DIR)/host-installer.inc: $(MY_OUTPUT_DIRSTAMP)
	{ set -e; set -o pipefail; \
	{ echo HOST_INSTALLER_PKG_NAME := host-installer; \
	  echo HOST_INSTALLER_PKG_VERSION := $(HOST_INSTALLER_VERSION)-$(HOST_INSTALLER_RELEASE); \
	  echo HOST_INSTALLER_PKG_FILE := RPMS/noarch/host-installer-\$$\(HOST_INSTALLER_PKG_VERSION\).noarch.rpm; \
	  echo HOST_INSTALLER_STARTUP_PKG_FILE := RPMS/noarch/host-installer-startup-\$$\(HOST_INSTALLER_PKG_VERSION\).noarch.rpm; \
	} > $@.tmp; \
	mv -f $@.tmp $@; \
	}

.PHONY: clean
clean:
	rm -f $(RPM_BUILD_COOKIE)
	rm -f $(SOURCES)
	rm -f $(SOURCES:%=%.tmp)
	rm -f $(MY_OBJ_DIR)/version.inc $(MY_OUTPUT_DIR)/host-installer.inc
