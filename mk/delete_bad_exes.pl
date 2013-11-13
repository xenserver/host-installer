#!/usr/bin/perl

use strict;
my %exes;

# read required executables
open(IN, '<executable_list.txt') or die;
while(<IN>) {
	chomp;
	next if /^#/;
	$exes{$_} = 1;
}
close(IN);

chdir($ARGV[0]) or die;

open(IN, "find -type f -perm +1 | grep bin | grep -v '\\.py\$\\|\\.so\$\\|\\.so\\.' |") or die;
while(<IN>) {
	chomp;
	next if !-f $_; # only regular files
	my $f = $_;
	my $fn = $f;
	$fn =~ s,.*[\\/],,;
	next if exists($exes{$fn});
	next if $fn =~ /[^-._a-z0-9]/i; #  exclude names with strange characters
	next if $fn =~ /^mkfs\.ext|^fsck\.ext/;
	my $type = `file $f`;
	next if $type !~ /ELF/;
	unlink("../tmpfile");
	rename($f, "../tmpfile");
	if (system(qq{grep -qr $fn . 2> /dev/null}) == 0) {
		# found, move back
		rename("../tmpfile", $f);
	} else {
		unlink("../tmpfile");
		print "file $f deleted\n";
	}
}
close(IN);

