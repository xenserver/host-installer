P2V_DIR ?= $(DESTDIR)/opt/xensource/installer

all:

clean:
	rm -rf *.pyc

install:
	mkdir -p $(P2V_DIR)
	install -m755 -t $(P2V_DIR) findroot.py
	install -m755 -t $(P2V_DIR) p2v.py
	install -m755 -t $(P2V_DIR) read_osversion.sh

	install -m644 -t $(P2V_DIR) p2v_answerfile_ui.py
	install -m644 -t $(P2V_DIR) p2v_backend.py
	install -m644 -t $(P2V_DIR) p2v_constants.py
	install -m644 -t $(P2V_DIR) p2v_error.py
	install -m644 -t $(P2V_DIR) p2v_pyanswerfile_ui.py
	install -m644 -t $(P2V_DIR) p2v_tui.py
	install -m644 -t $(P2V_DIR) p2v_uicontroller.py
	install -m644 -t $(P2V_DIR) p2v_utils.py
