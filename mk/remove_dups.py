import sys
import os
import hashlib

def chunkReader(fobj, chunk_size=1024*64):
	"""Generator that reads a file in chunks of bytes"""
	while True:
		chunk = fobj.read(chunk_size)
		if not chunk:
			return
		yield chunk

def getFileId(filename, hash=hashlib.sha1):
	hashobj = hash()
	for chunk in chunkReader(open(filename, 'rb')):
		hashobj.update(chunk)
	return (hashobj.digest(), os.path.getsize(filename))
	

def fileDuplicates(paths, hash=hashlib.sha1):
	hashes = {}
	sizes = {}
	for path in paths:
		for dirpath, dirnames, filenames in os.walk(path):
			for filename in filenames:
				full_path = os.path.join(dirpath, filename)
				if os.path.islink(full_path):
					continue
				size = os.path.getsize(full_path)
				sameSize = sizes.get(size, None)
				if not sameSize:
					sizes[size] = { 'fn': full_path, 'hashed' : False }
					continue
				# got at least one file with same size
				if not sameSize['hashed']:
					file_id = getFileId(sameSize['fn'], hash)
					hashes[file_id] = sameSize['fn']
					sameSize['hashed'] = True
				file_id = getFileId(full_path, hash)
				duplicate = hashes.get(file_id, None)
				if duplicate:
					yield (full_path, duplicate)
				else:
					hashes[file_id] = full_path

if sys.argv[1:]:
	gain = 0
	for fn1, fn2 in fileDuplicates(sys.argv[1:]):
#		print fn1, fn2
		gain += os.path.getsize(fn1)
		os.unlink(fn2)
		os.link(fn1, fn2)
	print "Gain %d bytes removing duplicate files" % gain
else:
	print >> sys.stderr, "Please pass the paths to check as parameters to the script"
	sys.exit(1)
