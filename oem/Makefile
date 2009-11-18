SCRIPTS = build-fi-image.sh rebuild-initrd.sh

all:

clean:
	rm -f $(patsubst %, $(DESTDIR)/%, $(SCRIPTS))

install:
	for s in $(SCRIPTS); do install -m755 $$s $(DESTDIR); done
