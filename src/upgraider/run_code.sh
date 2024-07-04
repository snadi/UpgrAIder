#!/bin/bash
set -e

filename=$1
libname=$2
libversion=$3
reqfile=$4

echo "SCRATCH_VENV: $SCRATCH_VENV"

cd $SCRATCH_VENV

# create a fresh venv
rm -rf .venv
python -m venv .venv
source .venv/bin/activate

pip install --disable-pip-version-check $libname==$libversion 

if [[ ! -z "$reqfile" ]] ; then
    pip install --disable-pip-version-check -r $reqfile
fi

echo "Running $filename in venv"

python $filename

deactivate