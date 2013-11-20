#!/usr/bin/perl

use strict;

my $verbose = 0;

chdir($ARGV[0]) or die;

# check directory existence
die if ! -d 'lib/modules';
die if ! -d 'lib/firmware';

# collect all file names required by installed modules
my %names = ();

my $got;
open(FW, 'find lib/modules -name \*.ko -type f | xargs modinfo | grep -i ^firmware: |') or die;
while(<FW>) {
	next if !/^firmware:(.*)/s;
	my $fw = $1;
	$fw =~ s/\s+/ /sg;
	while ($fw =~ /(\S+)/g) {
		die if $1 !~ m,^.*?([^/]+)$,;
		my $fn = $1;
		print "$fn\n" if $verbose;
		$names{$fn} = 1;
		++$got;
	}
}
close(FW);
die if $got < 20;

# scan all firmware and delete
my $gain = 0;
open(FW, 'find lib/firmware -type f |') or die;
while(<FW>) {
	chomp;
	my $fullpath = $_;
	die if !m,^.*?([^/]+)$,;
	my $fn = $1;
	# do not check files spot by modinfo
	next if exists($names{$fn});
	# do not delete file which name is in some module
	next if (system(qq{grep -qr $fn lib/modules 2> /dev/null}) == 0);

	# finally, delete firmware file
	print "deleting file $fullpath\n" if $verbose;
	my @st = stat($fullpath);
	# if number of links is 1 we gain some space
	$gain += $st[7] if $st[3] == 1;
	unlink($fullpath);
}
close(FW);

print "Gained $gain bytes\n";
