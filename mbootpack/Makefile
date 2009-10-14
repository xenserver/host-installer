#
#  Makefile for mbootpack
#

#
#  What object files need building for the program
#

PROG	:= mbootpack
OBJS	:= mbootpack.o buildimage.o
DEPS	:= mbootpack.o.d buildimage.o.d

# 
#  Tools etc.
#

RM 	:= rm -f
GDB	:= gdb
INCS	:= -I. -I-
DEFS	:= 
CC	:= gcc
CFLAGS 	:= -Wall -Wpointer-arith -Wcast-qual -Wno-unused -Wno-format
CFLAGS	+= -Wmissing-prototypes
#CFLAGS	+= -pipe -g -O0 -Wcast-align
CFLAGS	+= -pipe -O3 
DEPFLAGS = -Wp,-MD,$(@F).d

#
#  Rules
#

all: $(PROG)

gdb: $(PROG)
	$(GDB) $<

$(PROG): $(OBJS)
	$(CC) -o $@ $(filter-out %.a, $^)

clean: FRC
	$(RM) mbootpack *.o *.d bootsect setup bzimage_header.c

bootsect: bootsect.S
	$(CC) -m32 $(CFLAGS) $(INCS) $(DEFS) -D__MB_ASM -c bootsect.S -o bootsect.o
	$(LD) -m elf_i386 -Ttext 0x0 -s --oformat binary bootsect.o -o $@

setup: setup.S
	$(CC) -m32 $(CFLAGS) $(INCS) $(DEFS) -D__MB_ASM -c setup.S -o setup.o
	$(LD) -m elf_i386 -Ttext 0x0 -s --oformat binary setup.o -o $@

bzimage_header.c: bootsect setup
	sh ./mkhex bzimage_bootsect bootsect > bzimage_header.c
	sh ./mkhex bzimage_setup setup >> bzimage_header.c

buildimage.c buildimage.d: bzimage_header.c

%.o: %.S
	$(CC) $(CFLAGS) $(INCS) $(DEFS) -c $< -o $@

%.o: %.c
	$(CC) $(CFLAGS) $(DEPFLAGS) $(INCS) $(DEFS) -c $< -o $@

FRC: 
.PHONY:: all FRC clean gdb
.PRECIOUS: $(OBJS) $(OBJS:.o=.c) $(DEPS)
.SUFFIXES: 

-include $(DEPS)

#
#  EOF
#
