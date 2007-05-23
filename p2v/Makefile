P2V_DIR ?= $(DESTDIR)/opt/xensource/installer

all:

clean:
	rm -rf *.pyc

install:
	mkdir -p $(P2V_DIR)
	install -m755 findroot.py $(P2V_DIR)
	install -m755 p2v.py $(P2V_DIR)
	install -m755 read_osversion.sh $(P2V_DIR)

	install -m644 p2v_answerfile_ui.py $(P2V_DIR)
	install -m644 httpput.py $(P2V_DIR)
	install -m644 p2v_backend.py $(P2V_DIR)
	install -m644 p2v_constants.py $(P2V_DIR)
	install -m644 p2v_error.py $(P2V_DIR)
	install -m644 p2v_tui.py $(P2V_DIR)
	install -m644 p2v_utils.py $(P2V_DIR)
