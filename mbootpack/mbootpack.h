/*
 *  mbootpack.h
 *
 *  Common definitions for mbootpack
 * 
 *  Copyright (C) 2003-2004  Tim Deegan (tjd21@cl.cam.ac.uk)
 * 
 *  This program is free software; you can redistribute it and/or
 *  modify it under the terms of the GNU General Public License as
 *  published by the Free Software Foundation; either version 2 of the
 *  License, or (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 *  General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA
 *  02111-1307, USA.
 *
 * $Id: mbootpack.h,v 1.5 2008/12/09 12:53:24 tjd Exp $
 *
 */

#ifndef __MBOOTPACK__H__
#define __MBOOTPACK__H__

#ifndef __MB_ASM

#undef NDEBUG
#include <stdio.h>
#include <stdint.h>

/* Flags */
extern int quiet;

/* Types */
typedef uint32_t address_t;

typedef struct section_t {
    char *buffer;
    address_t start;
    int32_t size;
    struct section_t *prev;
    struct section_t *next;
} section_t;

/* buildimage.c */
extern void make_bzImage(section_t *sections, 
                         address_t entry, 
                         address_t mbi, 
                         FILE *fp);

address_t place_mbi(long int size);


/* trampoline.S */
extern unsigned char mb_trampoline[];
extern unsigned char mb_trampoline_end[];
extern volatile address_t mb_mbi_address, mb_entry_address;

/* Macros */
#define MIN(_x,_y) (((_x)<=(_y))?(_x):(_y))
#define MAX(_x,_y) (((_x)<=(_y))?(_y):(_x))
#define ROUNDUP_P2(_x, _a) (((_x)+((_a)-1))&(~((_a)-1)))

#endif

/* x86 memory: such fun */
#define MEM_HOLE_START  0xa0000
#define MEM_HOLE_END    0x100000
#define HIGHMEM_START   MEM_HOLE_END
#define X86_PAGE_SIZE   0x1000

/* How much command line we'll take from the bootloader. */
#define CMD_LINE_SPACE  0x300

/* Number of 512-byte sectors to load in low memory (max 7) */
#define SETUPSECTS	7


/* Who are we? */
#define MBOOTPACK_VERSION_STRING "v0.6 (alpha)"

#endif /* __MBOOTPACK__H__ */

/*
 *  EOF (mbootpack.h)
 */

