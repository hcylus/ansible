#!/bin/bash

DBuser='dumper'
DBpasswd='cdose5398#@**dos'

#enter backup directory
BACKUPDIR='back'
[ -d $BACKUPDIR ] || mkdir $BACKUPDIR
cd $BACKUPDIR
_logfile="dumpLog_`date +%Y%m`.txt"

#delete old or null files
find $BACKUPDIR -mtime +2 -name "*.gz" -exec rm -f {} \; 2>/dev/null
find $BACKUPDIR -mtime +1 -name "*.sql" -exec rm -f {} \; 2>/dev/null
find $BACKUPDIR -mtime +1 -name "*.txt" -exec rm -f {} \; 2>/dev/null
find $BACKUPDIR -size -1 -name "*`date +%Y%m`*" -exec rm -f {} \; 2>/dev/null

#logic dump mysql data and backup
function backup_mysql_dump(){
  DBhost=10.66.109.241
  _time=`date +%Y%m%d%H%M%z`
  _dblist=$(mysql -h$DBhost -u$DBuser -p$DBpasswd -BNe "select SCHEMA_NAME from information_schema.SCHEMATA where SCHEMA_NAME not in ('information_schema','mysql','performance_schema') and SCHEMA_NAME not like '%test';" 2>>$_logfile)
  [ -z "$_dblist" ] && return 0

  for DBname in `echo $_dblist`
  do
    _time=`date +%Y%m%d%H%M`
    _filename=${DBname}_${_time}.sql

    mysqldump --set-gtid-purged=OFF --opt -R -E --hex-blob --single-transaction --default-character-set=utf8 -h$DBhost -u$DBuser -p$DBpasswd $DBname > $BACKUPDIR/$_filename 2>>$_logfile
    # tar czvf ${_filename}{.tar.gz,} --remove-files 2>&1 >>$_logfile
  done
}

backup_mysql_dump
