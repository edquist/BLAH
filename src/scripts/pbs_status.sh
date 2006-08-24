#!/bin/bash

#  File:     pbs_status.sh
#
#  Author:   David Rebatto
#  e-mail:   David.Rebatto@mi.infn.it
#
#
#  Revision history:
#    20-Mar-2004: Original release
#    04-Jan-2005: Totally rewritten, qstat command not used anymore
#    03-May-2005: Added support for Blah Log Parser daemon (using the pbs_BLParser flag)
#
#  Description:
#    Return a classad describing the status of a PBS job
#
#
#  Copyright (c) 2004 Istituto Nazionale di Fisica Nucleare (INFN).
#  All rights reserved.
#  See http://grid.infn.it/grid/license.html for license details.
#

[ -f ${GLITE_LOCATION:-/opt/glite}/etc/blah.config ] && . ${GLITE_LOCATION:-/opt/glite}/etc/blah.config

usage_string="Usage: $0 [-w] [-n]"

logpath=${pbs_spoolpath}/server_logs

#get worker node info
getwn=""

#get creamport
getcreamport=""

usedBLParser="no"

srvfound=""

BLClient="${GLITE_LOCATION:-/opt/glite}/bin/BLClient"

###############################################################
# Parse parameters
###############################################################

while getopts "wn" arg 
do
    case "$arg" in
    w) getwn="yes" ;;
    n) getcreamport="yes" ;;
    
    -) break ;;
    ?) echo $usage_string
       exit 1 ;;
    esac
done

shift `expr $OPTIND - 1`

if [ "x$pbs_nologaccess" == "xyes" ]; then

#Try different logparser
 if [ ! -z $pbs_num_BLParser ] ; then
  for i in `seq 1 $pbs_num_BLParser` ; do
   s=`echo pbs_BLPserver${i}`
   p=`echo pbs_BLPport${i}`
   eval tsrv=\$$s
   eval tport=\$$p
   testres=`echo "TEST/"|$BLClient -a $tsrv -p $tport`
   if [ "x$testres" == "xYPBS" ] ; then
    pbs_BLPserver=$tsrv
    pbs_BLPport=$tport
    srvfound=1
    break
   fi
  done
  if [ -z $srvfound ] ; then
   echo "1ERROR: not able to talk with no logparser listed"
   exit 0
  fi
 fi
fi

###################################################################
#get creamport and exit

if [ "x$getcreamport" == "xyes" ] ; then
 result=`echo "CREAMPORT/"|$BLClient -a $pbs_BLPserver -p $pbs_BLPport`
 reqretcode=$?
 if [ "$reqretcode" == "1" ] ; then
  exit 1
 fi
 retcode=0
 echo $pbs_BLPserver:$result
 exit $retcode
fi

pars=$*
proxy_dir=~/.blah_jobproxy_dir

for  reqfull in $pars ; do
	requested=""
	#header elimination
	requested=${reqfull:4}
	reqjob=`echo $requested | sed -e 's/^.*\///'`
	logfile=`echo $requested | sed 's/\/.*//'`
	
     if [ "x$pbs_nologaccess" == "xyes" ]; then

        staterr=/tmp/${reqjob}_staterr
	
result=`${pbs_binpath}/qstat -f $reqjob 2>$staterr | awk -v jobId=$reqjob '
BEGIN {
    current_job = ""
    current_wn = ""
    current_js = ""
}

/Job Id:/ {
    current_job = substr($0, index($0, ":") + 2)
    current_job = substr(current_job, 1, index(current_job, ".")-1)
    print "[BatchJobId=\"" current_job "\";"
}
/exec_host =/ {
    current_wn = substr($0, index($0, "=")+2)
    current_wn = substr(current_wn, 1, index(current_wn, "/")-1)
}

/job_state =/ {
    current_js = substr($0, index($0, "=")+1)
}

/exit_status =/ {
    exitcode = substr($0, index($0, "=")+1)
}

END {
        if (current_js ~ "Q")  {jobstatus = 1}
        if (current_js ~ "R")  {jobstatus = 2}
        if (current_js ~ "E")  {jobstatus = 2}
        if (current_js ~ "C")  {jobstatus = 4}
        if (current_js ~ "H")  {jobstatus = 5}
	if (exitcode ~ "271")  {jobstatus = 3}
	
	if (jobstatus == 2 || jobstatus == 4) {
		print "WorkerNode=\"" current_wn "\";"
	}
	print "JobStatus=" jobstatus ";"
	if (jobstatus == 4) {
		print "ExitCode=" exitcode ";"
	}
	print "]"
	if (jobstatus == 3 || jobstatus == 4) {
		system("rm " proxyDir "/" jobId ".proxy 2>/dev/null")
	}

}
'
`
        errout=`cat $staterr`
	rm -f $staterr 2>/dev/null
	
        if [ -z "$errout" ] ; then
                echo "0"$result
                retcode=0
        else
                echo "1ERROR: Job not found"
                retcode=1
        fi

     else
	if [ "x$getwn" == "xyes" ] ; then
		workernode=`${pbs_binpath}/qstat -f $reqjob 2> /dev/null | grep exec_host| sed "s/exec_host = //" | awk -F"/" '{ print $1 }'`
	fi

	cliretcode=0
	retcode=0
	logs=""
	result=""
	logfile=`echo $requested | sed 's/\/.*//'`
	if [ "x$pbs_BLParser" == "xyes" ] ; then
    		usedBLParser="yes"
		result=`echo $requested | $BLClient -a $pbs_BLPserver -p $pbs_BLPport`
		cliretcode=$?
		response=${result:0:1}
		if [ "$response" != "[" -o "$cliretcode" != "0" ] ; then
			cliretcode=1
		else 
			cliretcode=0
		fi
	fi
	if [ "$cliretcode" == "1" -a "x$pbs_fallback" == "xno" ] ; then
	 echo "1ERROR: not able to talk with logparser on ${pbs_BLPserver}:${pbs_BLPport}"
	 exit 0
	fi
	if [ "$cliretcode" == "1" -o "x$pbs_BLParser" != "xyes" ] ; then
		result=""
		usedBLParser="no"
		logs="$logpath/$logfile `find $logpath -type f -newer $logpath/$logfile`"
		result=`awk -v jobId="$reqjob" -v wn="$workernode" -v proxyDir="$proxy_dir" '
BEGIN {
	rex_queued   = jobId ";Job Queued "
	rex_running  = jobId ";Job Run "
	rex_deleted  = jobId ";Job deleted "
	rex_finished = jobId ";Exit_status="
	rex_hold     = jobId ";Holds "

	print "["
	print "BatchjobId = \"" jobId "\";"
}

$0 ~ rex_queued {
	jobstatus = 1
}

$0 ~ rex_running {
	jobstatus = 2
}

$0 ~ rex_deleted {
	jobstatus = 3
	exit
}

$0 ~ rex_finished {
	jobstatus = 4
	s = substr($0, index($0, "Exit_status="))
	s = substr(s, 1, index(s, " ")-1)
	exitcode = substr(s, index(s, "=")+1)
	exit
}

$0 ~ rex_hold {
	jobstatus = 5
}

END {
	if (jobstatus == 0) { exit 1 }
	print "JobStatus = " jobstatus ";"
	if (jobstatus == 2) {
		print "WorkerNode = \"" wn "\";"
	}
	if (jobstatus == 4) {
		print "ExitCode = " exitcode ";"
	}
	print "]"
	if (jobstatus == 3 || jobstatus == 4) {
		system("rm " proxyDir "/" jobId ".proxy 2>/dev/null")
	}
}
' $logs`

  		if [ "$?" == "0" ] ; then
			echo "0"$result
			retcode=0
  		else
			echo "1ERROR: Job not found"
			retcode=1
  		fi
	fi #close if on pbs_BLParser
        if [ "x$usedBLParser" == "xyes" ] ; then
                pr_removal=`echo $result | sed -e 's/^.*\///'`
                result=`echo $result | sed 's/\/.*//'`
                res=`echo $result|awk -F"\; ExitCode=" '{ print $2 }'|awk -F"\;" '{ print $1 }'`;
                if [ "$res" == "271" ] ; then
                        out=`sed -n 's/^=>> PBS: //p' *.e$reqjob 2>/dev/null`
                        if [ ! -z $out ] ; then
                                echo "0"$result "Workernode=\"$workernode\"; ExitReason=\"$out\";]"
                        else
                                echo "0"$result "Workernode=\"$workernode\"; ExitReason=\"Killed by Resource Management System\";]"
                        fi
                else
                        echo "0"$result "Workernode=\"$workernode\";]"
                fi

                if [ "x$pr_removal" == "xYes" ] ; then
                        rm -f ${proxy_dir}/${reqjob}.proxy 2>/dev/null
                fi
                usedBLParser="no"
        fi
     fi #close of if-else on $pbs_nologaccess
done 
exit 0
