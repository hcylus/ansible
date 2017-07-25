#!/bin/bash

if [ -d $1 ];then
    rsync -av -e "ssh -p 4399" --exclude "*.md" --exclude ".git" $1 ghoul@$2:~/online/$3/
fi
