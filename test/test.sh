#!/bin/sh

export PYTHONPATH="$(realpath $(dirname $0))":"$(realpath $(dirname $0)/..)":"$PYTHONPATH"

cd "$(realpath $(dirname $0))"
PYTHON=python2
if  head -1 ../init | grep -q python3; then
	PYTHON=python3
fi
$PYTHON test_errors.py -v
