INSTALLER_DIR ?= $(DESTDIR)/opt/xensource/installer
INSTALLER_DATA_DIR ?= $(DESTDIR)/opt/xensource/installer

all:

clean:
	rm -rf *.pyc

install:
	mkdir -p $(INSTALLER_DIR)
	install -m755 -t $(INSTALLER_DIR) clean-installer
	install -m755 -t $(INSTALLER_DIR) init
	install -m755 -t $(INSTALLER_DIR) hwdetect
	install -m755 -t $(INSTALLER_DIR) support.sh

	install -m644 -t $(INSTALLER_DIR) answerfile_ui.py
	install -m644 -t $(INSTALLER_DIR) backend.py
	install -m644 -t $(INSTALLER_DIR) constants.py
	install -m644 -t $(INSTALLER_DIR) diskutil.py
	install -m644 -t $(INSTALLER_DIR) generalui.py
	install -m644 -t $(INSTALLER_DIR) hardware.py
	install -m644 -t $(INSTALLER_DIR) init_simpleui.py
	install -m644 -t $(INSTALLER_DIR) init_tui.py
	install -m644 -t $(INSTALLER_DIR) netutil.py
	install -m644 -t $(INSTALLER_DIR) packaging.py
	install -m644 -t $(INSTALLER_DIR) pyanswerfile_ui.py
	install -m644 -t $(INSTALLER_DIR) tui.py
	install -m644 -t $(INSTALLER_DIR) uicontroller.py
	install -m644 -t $(INSTALLER_DIR) util.py
	install -m644 -t $(INSTALLER_DIR) xelogging.py

	install -m644 -t $(INSTALLER_DATA_DIR) keymaps
	install -m644 -t $(INSTALLER_DATA_DIR) timezones

