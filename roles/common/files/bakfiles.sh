#!/bin/bash

src=$1
dest=$2
bakdate=`date +%Y-%m-%d-%H-%M-%S`

[ ! -d $2 ] && mkdir $2

find $2/ -maxdepth 1 -type d -ctime +10 -exec rm -rf {} \; 2>/dev/null

#for dir in `find $1/ -maxdepth 1 -type d|awk -F'/' '{print $NF}'|grep -v '^$'`
#do
rsync -avq --exclude "log" --exclude "logs" --exclude "*_log" --exclude "logger_cache" --exclude "core.*" --exclude "pro_*_pid" online/$1/ $2/"$1"_bak_"$bakdate"
result=$?
if [ $result = 0 ];then
echo bak $1 success
else
echo bak $1 fail
fi
#done
