#!/usr/bin/python

#  File:     slurm_status.py
#
#  Author:   Brian Bockelman (bbockelm@cse.unl.edu)
#            Jaime Frey (jfrey@cs.wisc.edu)
#
# Copyright (c) University of Nebraska-Lincoln.  2012
#               University of Wisconsin-Madison. 2016
# 
# Licensed under the Apache License, Version 2.0 (the "License"); 
# you may not use this file except in compliance with the License. 
# You may obtain a copy of the License at 
# 
#     http://www.apache.org/licenses/LICENSE-2.0 
# 
# Unless required by applicable law or agreed to in writing, software 
# distributed under the License is distributed on an "AS IS" BASIS, 
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. 
# See the License for the specific language governing permissions and 
# limitations under the License.
#

"""
Query SLURM for the status of a given job

Internally, it creates a cache of the SLURM response for all jobs and
will reuse this for subsequent queries.
"""

import os
import re
import pwd
import sys
import time
import errno
import fcntl
import random
import struct
import subprocess
import signal
import tempfile
import pickle
import csv

cache_timeout = 60

launchtime = time.time()

def log(msg):
    """
    A very lightweight log - not meant to be used in production, but helps
    when debugging scale tests
    """
    print >> sys.stderr, time.strftime("%x %X"), os.getpid(), msg

def createCacheDir():
    uid = os.geteuid()
    username = pwd.getpwuid(uid).pw_name
    cache_dir = os.path.join("/var/tmp", "slurm_cache_%s" % username)
    
    try:
        os.mkdir(cache_dir, 0755)
    except OSError, oe:
        if oe.errno != errno.EEXIST:
            raise
        s = os.stat(cache_dir)
        if s.st_uid != uid:
            raise Exception("Unable to check cache because it is owned by UID %d" % s.st_uid)

    return cache_dir

def initLog():
    """
    Determine whether to create a logfile based on the presence of a file
    in the user's slurm cache directory.  If so, make the logfile there.
    """
    cache_dir = createCacheDir()
    if os.path.exists(os.path.join(cache_dir, "slurm_status.debug")):
        filename = os.path.join(cache_dir, "slurm_status.log")
    else:
        filename = "/dev/null"
    fd = open(filename, "a")
    # Do NOT close the file descriptor blahp originally hands us for stderr.
    # This causes blahp to lose all status updates.
    os.dup(2)
    os.dup2(fd.fileno(), 2)

# Something else from a prior life - see gratia-probe-common's GratiaWrapper.py
def ExclusiveLock(fd, timeout=120):
    """
    Grabs an exclusive lock on fd

    If the lock is owned by another process, and that process is older than the
    timeout, then the other process will be signaled.  If the timeout is
    negative, then the other process is never signaled.

    If we are unable to hold the lock, this call will not block on the lock;
    rather, it will throw an exception.

    By default, the timeout is 120 seconds.
    """

    # POSIX file locking is cruelly crude.  There's nothing to do besides
    # try / sleep to grab the lock, no equivalent of polling.
    # Why hello, thundering herd.

    # An alternate would be to block on the lock, and use signals to interupt.
    # This would mess up Gratia's flawed use of signals already, and not be
    # able to report on who has the lock.  I don't like indefinite waits!
    max_time = 30
    starttime = time.time()
    tries = 1
    while time.time() - starttime < max_time:
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except IOError, ie:
            if not ((ie.errno == errno.EACCES) or (ie.errno == errno.EAGAIN)):
                raise
            if check_lock(fd, timeout):
                time.sleep(.2) # Fast case; however, we have *no clue* how
                               # long it takes to clean/release the old lock.
                               # Nor do we know if we'd get it if we did
                               # fcntl.lockf w/ blocking immediately.  Blech.
                # Check again immediately, especially if this was the last
                # iteration in the for loop.
                try:
                    fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except IOError, ie:
                    if not ((ie.errno == errno.EACCES) or (ie.errno == errno.EAGAIN)):
                        raise
        sleeptime = random.random()
        log("Unable to acquire lock, try %i; will sleep for %.2f " \
            "seconds and try for %.2f more seconds." % (tries, sleeptime, max_time - (time.time()-starttime)))
        tries += 1
        time.sleep(sleeptime)

    log("Fatal exception - Unable to acquire lock")
    raise Exception("Unable to acquire lock")

def check_lock(fd, timeout):
    """
    For internal use only.

    Given a fd that is locked, determine which process has the lock.
    Kill said process if it is older than "timeout" seconds.
    This will log the PID of the "other process".
    """

    pid = get_lock_pid(fd)
    if pid == os.getpid():
        return True

    if timeout < 0:
        log("Another process, %d, holds the cache lock." % pid)
        return False

    try:
        age = get_pid_age(pid)
    except:
        log("Another process, %d, holds the cache lock." % pid)
        log("Unable to get the other process's age; will not time it out.")
        return False

    log("Another process, %d (age %d seconds), holds the cache lock." % (pid, age))

    if age > timeout:
        os.kill(pid, signal.SIGKILL)
    else:
        return False

    return True

linux_struct_flock = "hhxxxxqqixxxx"
try:
    os.O_LARGEFILE
except AttributeError:
    start_len = "hhlli"

def get_lock_pid(fd):
    # For reference, here's the definition of struct flock on Linux
    # (/usr/include/bits/fcntl.h).
    #
    # struct flock
    # {
    #   short int l_type;   /* Type of lock: F_RDLCK, F_WRLCK, or F_UNLCK.  */
    #   short int l_whence; /* Where `l_start' is relative to (like `lseek').  */
    #   __off_t l_start;    /* Offset where the lock begins.  */
    #   __off_t l_len;      /* Size of the locked area; zero means until EOF.  */
    #   __pid_t l_pid;      /* Process holding the lock.  */
    # };
    #
    # Note that things are different on Darwin
    # Assuming off_t is unsigned long long, pid_t is int
    try:
        if sys.platform == "darwin":
            arg = struct.pack("QQihh", 0, 0, 0, fcntl.F_WRLCK, 0)
        else:
            arg = struct.pack(linux_struct_flock, fcntl.F_WRLCK, 0, 0, 0, 0)
        result = fcntl.fcntl(fd, fcntl.F_GETLK, arg)
    except IOError, ie:
        if ie.errno != errno.EINVAL:
            raise
        log("Unable to determine which PID has the lock due to a " \
            "python portability failure.  Contact the developers with your" \
            " platform information for support.")
        return False
    if sys.platform == "darwin":
        _, _, pid, _, _ = struct.unpack("QQihh", result)
    else:
        _, _, _, _, pid = struct.unpack(linux_struct_flock, result)
    return pid

def get_pid_age(pid):
    now = time.time()
    st = os.stat("/proc/%d" % pid)
    return now - st.st_ctime

def call_scontrol(jobid=""):
    """
    Call scontrol directly for a jobid.
    If none is specified, query all jobid's.

    Returns a python dictionary with the job info.
    """
    scontrol = get_slurm_location('scontrol')

    starttime = time.time()
    log("Starting scontrol.")
    command = (scontrol, 'show', 'job', jobid)
    scontrol_proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    scontrol_out, _ = scontrol_proc.communicate()

    result = parse_scontrol(scontrol_out)
    log("Finished scontrol (time=%f)." % (time.time()-starttime))

    if scontrol_proc.returncode == 1: # Completed
        result = {jobid: {'BatchJobId': '"%s"' % jobid, "JobStatus": "4", "ExitCode": ' 0'}}
    elif scontrol_proc.returncode == 271: # Removed
        result = {jobid: {'BatchJobId': '"%s"' % jobid, 'JobStatus': '3', 'ExitCode': ' 0'}}
    elif scontrol_proc.returncode != 0:
        raise Exception("scontrol failed with exit code %s" % str(scontrol_proc.returncode))

    # If the job has completed...
    if jobid is not "" and "JobStatus" in result[jobid] and (result[jobid]["JobStatus"] == '4' or result[jobid]["JobStatus"] == '3'):
        # Get the finished job stats and update the result
        finished_job_stats = get_finished_job_stats(jobid)
        result[jobid].update(finished_job_stats)

    return result


def which(program):
    """
    Determine if the program is in the path.
    
    arg program: name of the program to search
    returns: full path to executable, or None if executable is not found
    """
    def is_exe(fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                 return exe_file

    return None

def convert_cpu_to_seconds(cpu_string):
    import re
    h,m,s = re.split(':',cpu_string)
    return int(h) * 3600 + int(m) * 60 + int(s)

def get_finished_job_stats(jobid):
    """
    Get a completed job's statistics such as used RAM and cpu usage.
    """
    
    # First, list the attributes that we want
    return_dict = { "ImageSize": 0, "ExitCode": 0, "RemoteUserCpu": 0 }

    # Next, query the appropriate interfaces for the completed job information
    sacct = get_slurm_location('sacct')
    log("Querying sacct for completed job for jobid: %s" % (str(jobid)))
    child_stdout = os.popen("%s -j %s -l --noconvert -P" % (sacct, str(jobid)))
    sacct_data = child_stdout.readlines()
    ret = child_stdout.close()

    if ret:
        # retry without --noconvert for slurm < 15.8
        child_stdout = os.popen("sacct -j %s -l -P" % (str(jobid)))
        sacct_data = child_stdout.readlines()
        child_stdout.close()

    try:
        reader = csv.DictReader(sacct_data, delimiter="|")
    except Exception, e:
        log("Unable to read in CSV output from sacct: %s" % str(e))
        return return_dict
           
    # Slurm can return more than 1 row, for some odd reason.
    # so sum up relevant values
    for row in reader:
        if row["AveCPU"] is not "":
            return_dict['RemoteUserCpu'] += convert_cpu_to_seconds(row["AveCPU"]) * int(row["AllocCPUS"])
        if row["MaxRSS"] is not "":
            # Remove the trailing 'K'
            return_dict["ImageSize"] += int(row["MaxRSS"].replace('K', ''))
        if row["ExitCode"] is not "":
            return_dict["ExitCode"] = int(row["ExitCode"].split(":")[0])

    return return_dict
    

_slurm_location_cache = None
def get_slurm_location(program):
    """
    Locate the copy of the slurm bin the blahp configuration wants to use.
    """
    global _slurm_location_cache
    if _slurm_location_cache != None:
        return os.path.join(_slurm_location_cache, program)
    load_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blah_load_config.sh')
    if os.path.exists(load_config_path) and os.access(load_config_path, os.R_OK):
        cmd = 'source %s && echo "${slurm_binpath:-/usr/bin}/%s"' % (load_config_path, program)
    else:
        cmd = 'which %s' % program
    child_stdout = os.popen(cmd)
    output = child_stdout.read()
    location = output.split("\n")[0].strip()
    if child_stdout.close():
        raise Exception("Unable to determine scontrol location: %s" % output)
    _slurm_location_cache = os.path.dirname(location)
    return location

job_id_re = re.compile("JobId=([0-9]+) .*")
exec_host_re = re.compile("\s*BatchHost=([\w\-.]+)")
status_re = re.compile("\s*JobState=([\w]+) .*")
exit_status_re = re.compile(".* ExitCode=(-?[0-9]+:[0-9]+)")
status_mapping = {"BOOT_FAIL": 4, "CANCELLED": 3, "COMPLETED": 4, "CONFIGURING": 1, "COMPLETING": 2, "FAILED": 4, "NODE_FAIL": 4, "PENDING": 1, "PREEMPTED": 4, "RUNNING": 2, "SPECIAL_EXIT": 4, "STOPPED": 2, "SUSPENDED": 2}

def parse_scontrol(output):
    """
    Parse the stdout of "scontrol show job" into a python dictionary
    containing the information we need.
    """
    job_info = {}
    cur_job_id = None
    cur_job_info = {}
    for line in output.split('\n'):
        line = line.strip()
        m = job_id_re.match(line)
        if m:
            if cur_job_id:
                job_info[cur_job_id] = cur_job_info
            cur_job_id = m.group(1)
            #print cur_job_id, line
            cur_job_info = {"BatchJobId": '"%s"' % cur_job_id}
            continue
        if cur_job_id == None:
            continue
        m = exec_host_re.match(line)
        if m:
            cur_job_info["WorkerNode"] = '"' + m.group(1) + '"'
            continue
        m = status_re.match(line)
        if m:
            status = status_mapping.get(m.group(1), 0)
            if status != 0:
                cur_job_info["JobStatus"] = str(status)
            continue
        m = exit_status_re.match(line)
        if m:
            cur_job_info["ExitCode"] = ' %s' % m.group(1).split(":")[0]
            continue
    if cur_job_id:
        job_info[cur_job_id] = cur_job_info
    return job_info

def job_dict_to_string(info):
    result = ["%s=%s;" % (i[0], i[1]) for i in info.items()]
    return "[" + " ".join(result) + " ]"

def fill_cache(cache_location):
    log("Starting query to fill cache.")
    results = call_scontrol()
    log("Finished query to fill cache.")
    (fd, filename) = tempfile.mkstemp(dir = "/var/tmp")
    # Open the file with a proper python file object
    f = os.fdopen(fd, "w")
    writer = csv.writer(f, delimiter='\t')
    try:
        try:
            for key, val in results.items():
                key = key.split(".")[0]
                writer.writerow([key, pickle.dumps(val)])
            os.fsync(fd)
        except:
            os.unlink(filename)
            raise
    finally:
        f.close()
    os.rename(filename, cache_location)
    
    global launchtime
    launchtime = time.time()

cache_line_re = re.compile("([0-9]+[\.\w\-]+):\s+(.+)")
def cache_to_status(jobid, fd):
    reader = csv.reader(fd, delimiter='\t')
    for row in reader:
        if row[0] == jobid:
            return pickle.loads(row[1])

def check_cache(jobid, recurse=True):
    uid = os.geteuid()
    username = pwd.getpwuid(uid).pw_name
    cache_dir = os.path.join("/var/tmp", "slurm_cache_%s" % username)
    if recurse:
        try:
            s = os.stat(cache_dir)
        except OSError, oe:
            if oe.errno != 2:
                raise
            os.mkdir(cache_dir, 0755)
            s = os.stat(cache_dir)
        if s.st_uid != uid:
            raise Exception("Unable to check cache because it is owned by UID %d" % s.st_uid)
    cache_location = os.path.join(cache_dir, "blahp_results_cache")
    try:
        fd = open(cache_location, "a+")
    except IOError, ie:
        if ie.errno != 2:
            raise
        # Create an empty file so we can hold the file lock
        fd = open(cache_location, "w+")
        ExclusiveLock(fd)
        # If someone grabbed the lock between when we opened and tried to
        # acquire, they may have filled the cache
        if os.stat(cache_location).st_size == 0:
            fill_cache(cache_location)
        fd.close()
        if recurse:
            return check_cache(jobid, recurse=False)
        else:
            return None
    ExclusiveLock(fd)
    s = os.fstat(fd.fileno())
    if s.st_uid != uid:
        raise Exception("Unable to check cache file because it is owned by UID %d" % s.st_uid)
    if (s.st_size == 0) or (launchtime - s.st_mtime > cache_timeout):
        # If someone filled the cache between when we opened the file and
        # grabbed the lock, we may not need to fill the cache.
        s2 = os.stat(cache_location)
        if (s2.st_size == 0) or (launchtime - s2.st_mtime > cache_timeout):
            fill_cache(cache_location)
        if recurse:
            return check_cache(jobid, recurse=False)
        else:
            return None
    return cache_to_status(jobid, fd)

job_status_re = re.compile(".*JobStatus=(\d+);.*")

def main():
    initLog()

    if len(sys.argv) != 2:
        print "1Usage: slurm_status.py slurm/<date>/<jobid>"
        return 1
    jobid = sys.argv[1].split("/")[-1].split(".")[0]
    log("Checking cache for jobid %s" % jobid)
    cache_contents = None
    try:
        cache_contents = check_cache(jobid)
    except Exception, e:
        msg = "1ERROR: Internal exception, %s" % str(e)
        log(msg)
        #print msg
    if not cache_contents:
        log("Jobid %s not in cache; querying SLURM" % jobid)
        results = call_scontrol(jobid)
        log("Finished querying SLURM for jobid %s" % jobid)
        if not results or jobid not in results:
            log("1ERROR: Unable to find job %s" % jobid)
            print "1ERROR: Unable to find job %s" % jobid
        else:
            log("0%s" % job_dict_to_string(results[jobid]))
            print "0%s" % job_dict_to_string(results[jobid])
    else:
        log("Jobid %s in cache." % jobid)
        log("0%s" % job_dict_to_string(cache_contents))
        
        if cache_contents["JobStatus"] == '4' or cache_contents["JobStatus"] == '3':
            finished_job_stats = get_finished_job_stats(jobid)
            cache_contents.update(finished_job_stats)
            
        print "0%s" % job_dict_to_string(cache_contents)
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception, e:
        print "1ERROR: %s" % str(e).replace("\n", "\\n")
        sys.exit(0)
