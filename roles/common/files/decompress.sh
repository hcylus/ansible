#!/bin/bash

src=$1

for i in `find $src -type f -name '*.tar.gz'`
do
    dest=`echo ${i%/*}`
    echo $dest
    echo $i
    tar xf $i -C $dest
done
find $src -type f -name '*.tar.gz' -exec rm -rf {} \;
