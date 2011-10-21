#!/bin/env python
#
#     run_pipeline.py: run pipeline script on file sets
#     Copyright (C) University of Manchester 2011 Peter Briggs
#
########################################################################
#
# run_pipeline.py
#
#########################################################################

"""run_pipeline.py

Implements a program to run a pipeline script or command on the
set of files in a specific directory.

Usage: python run_pipeline.py [OPTIONS] <script> <data_dir> [ <data_dir> ... ]

<script> must accept arguments based on the --input option, but defaults to
         a csfasta/qual file pair.
<data_dir> contains the input data for the script.
"""

#######################################################################
# Import modules that this module depends on
#######################################################################

import sys
import os
import time
import subprocess
import Queue
import logging
import JobRunner

#######################################################################
# Class definitions
#######################################################################

# Job: container for a script run
class Job:
    """Wrapper class for setting up, submitting and monitoring running scripts

    Set up a job by creating a Job instance specifying the name, working directory,
    script file to execute, and arguments to be supplied to the script.

    The job is started by invoking the 'start' method; its status can be checked
    with the 'isRunning' method, and terminated and restarted using the 'terminate'
    and 'restart' methods respectively.

    Information about the job can also be accessed via its properties. The following
    properties record the original parameters supplied on instantiation:

      name
      working_dir
      script
      args

    Additional information is set once the job has started or stopped running:

      job_id      The id number for the running job returned by the JobRunner
      log         The log file for the job (relative to working_dir)
      start_time  The start time (seconds since the epoch)
      end_time    The end time (seconds since the epoch)

    The Job class uses a JobRunner instance (which supplies the necessary methods for
    starting, stopping and monitoring) for low-level job interactions.
    """
    def __init__(self,runner,name,dirn,script,*args):
        """Create an instance of Job.

        Arguments:
          runner: a JobRunner instance supplying job control methods
          name: name to give the running job
          dirn: directory to run the script in
          script: script file to submit, either a full path, relative path to dirn, or
            must be on the user's PATH in the environment where jobs are executed
          args: arbitrary arguments to supply to the script when it is submitted
        """
        self.name = name
        self.working_dir = dirn
        self.script = script
        self.args = args
        self.job_id = None
        self.log = None
        self.submitted = False
        self.failed = False
        self.terminated = False
        self.start_time = None
        self.end_time = None
        self.home_dir = os.getcwd()
        self.__finished = False
        self.__runner = runner

    def start(self):
        """Start the job running

        Returns:
          Id for job
        """
        if not self.submitted and not self.__finished:
            self.job_id = self.__runner.run(self.name,self.working_dir,self.script,*self.args)
            self.submitted = True
            self.start_time = time.time()
            if self.job_id is None:
                # Failed to submit correctly
                logging.warning("Job submission failed")
                self.failed = True
                self.__finished = True
                self.end_time = self.start_time
                return self.job_id
            self.submitted = True
            self.start_time = time.time()
            self.log = self.__runner.logfile(self.job_id)
            # Wait for evidence that the job has started
            logging.debug("Waiting for job to start")
            while not self.__runner.isRunning(self.job_id) and not os.path.exists(self.log):
                time.sleep(5)
        logging.debug("Job %s started (%s)" % (self.job_id,
                                               time.asctime(time.localtime(self.start_time))))
        return self.job_id

    def terminate(self):
        """Terminate a running job
        """
        if self.isRunning():
            self.__runner.terminate(self.job_id)
            self.terminated = True
            self.end_time = time.time()

    def restart(self):
        """Restart the job

        Terminates the job (if still running) and restarts"""
        # Terminate running job
        if self.isRunning():
            self.terminate()
            while self.isRunning():
                time.sleep(5)
        # Reset flags
        self.__finished = False
        self.submitted = False
        self.terminated = False
        self.start_time = None
        self.end_time = None
        # Resubmit
        return self.start()

    def isRunning(self):
        """Check if job is still running
        """
        if not self.submitted:
            return False
        if not self.__finished:
            if not self.__runner.isRunning(self.job_id):
                self.end_time = time.time()
                self.__finished = True
        return not self.__finished

    def errorState(self):
        """Check if the job is in an error state
        """
        return self.__runner.errorState(self.job_id)

    def status(self):
        """Return descriptive string indicating job status
        """
        if self.__finished:
            if self.terminated:
                return "Terminated"
            else:
                return "Finished"
        elif self.submitted:
            if self.terminated:
                return "Running pending termination"
            else:
                return "Running"
        else:
            return "Waiting"

# PipelineRunner: class to set up and run multiple jobs
class PipelineRunner:
    """Class to run and manage multiple concurrent jobs.

    PipelineRunner enables multiple jobs to be queued via the 'queueJob' method. The
    pipeline is then started using the 'run' method - this starts each job up to a
    a specified maximum of concurrent jobs, and then monitors their progress. As jobs
    finish, pending jobs are started until all jobs have completed.

    Example usage:

    >>> p = PipelineRunner()
    >>> p.queueJob('/home/foo','foo.sh','bar.in')
    ... Queue more jobs ...
    >>> p.run()

    By default the pipeline runs in 'blocking' mode, i.e. 'run' doesn't return until all
    jobs have been submitted and have completed; see the 'run' method for details of
    how to operate the pipeline in non-blocking mode.
    """
    def __init__(self,runner,max_concurrent_jobs=4,poll_interval=30):
        """Create new PipelineRunner instance.

        Arguments:
          runner: a JobRunner instance
          max_concurrent_jobs: maximum number of jobs that the script will allow to run
            at one time (default = 4)
          poll_interval: time interval (in seconds) between checks on the queue status
            (only used when pipeline is run in 'blocking' mode)
        """
        # Parameters
        self.__runner = runner
        self.max_concurrent_jobs = max_concurrent_jobs
        self.poll_interval = poll_interval
        # Queue of jobs to run
        self.jobs = Queue.Queue()
        # Subset that are currently running
        self.running = []
        # Subset that have completed
        self.completed = []

    def queueJob(self,working_dir,script,*args):
        """Add a job to the pipeline.

        The job will be queued and executed once the pipeline's 'run' method has been
        executed.

        Arguments:
          working_dir: directory to run the job in
          script: script file to run
          args: arguments to be supplied to the script at run time
        """
        job_name = os.path.splitext(os.path.basename(script))[0]
        self.jobs.put(Job(self.__runner,job_name,working_dir,script,*args))
        logging.debug("Added job: now %d jobs in pipeline" % self.jobs.qsize())

    def nWaiting(self):
        """Return the number of jobs still waiting to be started
        """
        return self.jobs.qsize()

    def nRunning(self):
        """Return the number of jobs currently running
        """
        return len(self.running)

    def nCompleted(self):
        """Return the number of jobs that have completed
        """
        return len(self.completed)

    def isRunning(self):
        """Check whether the pipeline is still running

        Returns True if the pipeline is still running (i.e. has either
        running jobs, waiting jobs or both) and False otherwise.
        """
        # First update the pipeline status
        self.update()
        # Return the status
        return (self.nWaiting() > 0 or self.nRunning() > 0)

    def run(self,blocking=True):
        """Execute the jobs in the pipeline

        Each job previously added to the pipeline by 'queueJob' will be
        started and checked periodically for termination.

        By default 'run' operates in 'blocking' mode, so it doesn't return
        until all jobs have been submitted and have finished executing.

        To run in non-blocking mode, set the 'blocking' argument to False.
        In this mode the pipeline starts and returns immediately; it is
        the responsibility of the calling subprogram to then periodically
        check the status of the pipeline, e.g.

        >>> p = PipelineRunner()
        >>> p.queueJob('/home/foo','foo.sh','bar.in')
        >>> p.run()
        >>> while p.isRunning():
        >>>     time.sleep(30)
        """
        logging.debug("PipelineRunner: started")
        logging.debug("Blocking mode : %s" % blocking)
        # Report set up
        print "Initially %d jobs waiting, %d running, %d finished" % \
            (self.nWaiting(),self.nRunning(),self.nCompleted())
        # Initial update sets the jobs running
        self.update()
        if blocking:
            while self.isRunning():
                # Pipeline is still executing so wait
                time.sleep(self.poll_interval)
            # Pipeline has finished
            print "Pipeline completed"

    def update(self):
        """Update the pipeline

        The 'update' method checks and updates the status of running jobs,
        and submits any waiting jobs if space is available.
        """
        # Flag to report updated status
        updated_status = False
        # Look for running jobs that have completed
        for job in self.running[::-1]:
            if not job.isRunning():
                # Job has completed
                self.running.remove(job)
                self.completed.append(job)
                updated_status = True
                print "Job has completed: %s: %s %s (%s)" % (
                    job.job_id,
                    job.name,
                    os.path.basename(job.working_dir),
                    time.asctime(time.localtime(job.end_time)))
                # Set the permissions on the output log file to rw-rw-r--
                if job.log:
                    if os.path.exists(os.path.join(job.working_dir,job.log)):
                        os.chmod(os.path.join(job.working_dir,job.log),0664)
            else:
                # Job is running, check it's not in an error state
                if job.errorState():
                    # Terminate jobs in error state
                    logging.warning("Terminating job %s in error state" % job.job_id)
                    job.terminate()
        # Submit new jobs to GE queue
        while not self.jobs.empty() and len(self.__runner.list()) < self.max_concurrent_jobs:
            next_job = self.jobs.get()
            next_job.start()
            self.running.append(next_job)
            updated_status = True
            print "Job has started: %s: %s %s (%s)" % (
                next_job.job_id,
                next_job.name,
                os.path.basename(next_job.working_dir),
                time.asctime(time.localtime(next_job.start_time)))
            if self.jobs.empty():
                logging.debug("PipelineRunner: all jobs now submitted")
        # Report
        if updated_status:
            print "Currently %d jobs waiting, %d running, %d finished" % \
                (self.nWaiting(),self.nRunning(),self.nCompleted())

    def report(self):
        """Return a report of the pipeline status
        """
        # Pipeline status
        if self.nRunning() > 0:
            status = "RUNNING"
        elif self.nWaiting() > 0:
            status = "WAITING"
        else:
            status = "COMPLETED"
        report = "Pipeline status at %s: %s\n\n" % (time.asctime(),status)
        # Report directories
        dirs = []
        for job in self.completed:
            if job.working_dir not in dirs:
                dirs.append(job.working_dir)
        for dirn in dirs:
            report += "\t%s\n" % dirn
        # Report jobs waiting
        if self.nWaiting() > 0:
            report += "\n%d jobs waiting to run\n" % self.nWaiting()
        # Report jobs running
        if self.nRunning() > 0:
            report += "\n%d jobs running:\n" % self.nRunning()
            for job in self.running:
                report += "\t%s\t%s\t%s\n" % (job.job_id,job.name,job.working_dir)
        # Report completed jobs
        if self.nCompleted() > 0:
            report += "\n%d jobs completed:\n" % self.nCompleted()
            for job in self.completed:
                report += "\t%s\t%s\t%s\t%.1fs\t[%s]\n" % (job.job_id,
                                                           job.name,
                                                           job.working_dir,
                                                           (job.end_time - job.start_time),
                                                           job.status())
        return report

class SolidPipelineRunner(PipelineRunner):
    """Class to run and manage multiple jobs for Solid data pipelines

    Subclass of PipelineRunner specifically for dealing with scripts
    that take Solid data (i.e. csfasta/qual file pairs).

    Defines the addDir method in addition to all methods already defined
    in the base class; use this method one or more times to specify
    directories with data to run the script on. The SOLiD data file pairs
    in each specified directory will be located automatically.

    For example:

    solid_pipeline = SolidPipelineRunner('qc.sh')
    solid_pipeline.addDir('/path/to/datadir')
    solid_pipeline.run()
    """
    def __init__(self,runner,script,max_concurrent_jobs=4,poll_interval=30):
        PipelineRunner.__init__(self,runner)
        self.script = script

    def addDir(self,dirn):
        logging.debug("Add dir: %s" % dirn)
        run_data = GetSolidDataFiles(dirn)
        for data in run_data:
            self.queueJob(dirn,self.script,*data)

#######################################################################
# Module Functions
#######################################################################

# SendEmail: send an email message via mutt
def SendEmail(subject,recipient,message):
    """Send an email message via the 'mutt' client
    """
    p = subprocess.Popen(('mutt','-s',subject,recipient),
                         stdin=subprocess.PIPE)
    p.stdin.write(message)
    p.stdin.close()
    p.wait()
    return

def GetSolidDataFiles(dirn):
    """Return list of csfasta/qual file pairs in target directory

    Note that files with names ending in '_T_F3' will be rejected
    as these are assumed to come from the preprocess filtering stage.
    """
    # Check directory exists
    if not os.path.isdir(dirn):
        logging.error("'%s' not a directory: unable to collect SOLiD files" % dirn)
        return []
    # Gather data files
    logging.debug("Collecting csfasta/qual file pairs in %s" % dirn)
    data_files = []
    all_files = os.listdir(dirn)
    all_files.sort()

    # Look for csfasta and matching qual files
    for filen in all_files:
        logging.debug("Examining file %s" % filen)
        root = os.path.splitext(filen)[0]
        ext = os.path.splitext(filen)[1]
        if ext == ".qual":
            qual = filen
            # Reject names ending with "_T_F3"
            try:
                i = root.rindex('_T_F3')
                logging.debug("Rejecting %s" % qual)
                continue
            except ValueError:
                # Name is okay, ignore
                pass
            # Match csfasta names which don't have "_QV" in them
            try:
                i = root.rindex('_QV')
                csfasta = root[:i]+root[i+3:]+".csfasta"
            except ValueError:
                # QV not in name, try to match whole name
                csfasta = root+".csfasta"
            if os.path.exists(os.path.join(dirn,csfasta)):
                data_files.append((csfasta,qual))
            else:
                logging.critical("Unable to get csfasta for %s" % filen)
    # Done - return file pairs
    return data_files

def GetFastqFiles(dirn):
    """Return list of fastq files in target directory
    """
    # Check directory exists
    if not os.path.isdir(dirn):
        logging.error("'%s' not a directory: unable to collect fastq files" % dirn)
        return []
    # Gather data files
    logging.debug("Collecting fastq files in %s" % dirn)
    data_files = []
    all_files = os.listdir(dirn)
    all_files.sort()

    # Look for csfasta and matching qual files
    for filen in all_files:
        logging.debug("Examining file %s" % filen)
        root = os.path.splitext(filen)[0]
        ext = os.path.splitext(filen)[1]
        if ext == ".fastq": data_files.append((filen,))
    # Done - return file list
    return data_files

#######################################################################
# Main program
#######################################################################

if __name__ == "__main__":
    # Initialise
    max_concurrent_jobs = 4
    poll_interval = 30
    max_total_jobs = 0
    logging_level = logging.INFO
    script = None
    data_dirs = []
    input_type = "solid"
    email_addr = None
    ge_queue = None
    use_simple_runner = False

    # Deal with command line
    if len(sys.argv) < 3:
        print "Usage: %s [OPTIONS] <script> <dir> [<dir> ...]" % \
            os.path.basename(sys.argv[0])
        print ""
        print "<script> : pipeline script file to execute"
        print "<dir>    : one or more directories holding SOLiD data"
        print "           By default, <script> will be executed for each"
        print "           csfasta/qual file pair in dir, using:"
        print "             <script> <csfasta> <qual>"
        print "           Use --input option to run e.g."
        print "             <script> <fastq> etc"
        print ""
        print "Basic Options:"
        print "  --limit=<n>: queue no more than <n> jobs at one time"
        print "               (default %s)" % max_concurrent_jobs
        print "  --queue=<name>: explicitly specify GE queue to use"
        print "  --input=<type> : specify type of input for script"
        print "               Can be one of:"
        print "               solid = csfasta/qual file pair (default)"
        print "               fastq = fastq file"
        print "  --email=<address>: send an email to <address> when the"
        print "               pipeline has completed."
        print
        print "Advanced Options:"
        print "  --test=<n> : submit no more than <n> jobs in total"
        print "  --runner=<runner>: specify how jobs are executed"
        print "               Can be one of:"
        print "               ge = use Grid Engine (default)"
        print "               simple = use local system"
        print "  --debug    : print debugging output while running"
        print
        sys.exit()

    # Collect command line options
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            # Set maximum number of jobs to queue at one time
            max_concurrent_jobs = int(arg.split('=')[1])
        elif arg.startswith("--queue="):
            # Name of GE queue to use
            ge_queue = arg.split('=')[1]
        elif arg.startswith("--debug"):
            # Set logging level to output debugging info
            logging_level = logging.DEBUG
        elif arg.startswith("--test="):
            # Run in test mode: limit the number of jobs
            # submitted
            max_total_jobs = int(arg.split('=')[1])
        elif arg.startswith("--input="):
            # Specify input type
            input_type = arg.split('=')[1]
        elif arg.startswith("--email="):
            email_addr = arg.split('=')[1]
        elif arg.startswith("--runner="):
            use_simple_runner = (arg.split('=')[1] == 'simple')
        elif arg.startswith("--") and len(data_dirs) > 0:
            # Some option appeared after we started collecting directories
            logging.error("Unexpected argument encountered: %s" % arg)
            sys.exit(1)
        else:
            if script is None:
                # Script name
                print "Script: %s" % arg
                if os.path.isabs(arg):
                    # Absolute path
                    if os.path.isfile(arg):
                        script = arg
                    else:
                        script = None
                else:
                    # Try relative to pwd
                    script = os.path.normpath(os.path.join(os.getcwd(),arg))
                    if not os.path.isfile(script):
                        # Try relative to directory for script
                        script = os.path.abspath(os.path.normpath(
                                os.path.join(os.path.dirname(sys.argv[0]),arg)))
                        if not os.path.isfile(script):
                            script = None
                if script is None:
                    logging.error("Script file not found: %s" % script)
                    sys.exit(1)
                print "Full path for script: %s" % script
            else:
                # Data directory
                print "Directory: %s" % arg
                dirn = os.path.abspath(arg)
                if not os.path.isdir(dirn):
                    logging.error("Not a directory: %s" % dirn)
                    sys.exit(1)
                # Check for duplicates
                if dirn not in data_dirs:
                    data_dirs.append(dirn)
                else:
                    logging.warning("Directory '%s' already specified" % dirn)

    # Set logging format and level
    logging.basicConfig(format='%(levelname)8s %(message)s')
    logging.getLogger().setLevel(logging_level)

    # Set up job runner
    if use_simple_runner:
        runner = JobRunner.SimpleJobRunner()
    else:
        runner = JobRunner.GEJobRunner(queue=ge_queue)

    # Set up and run pipeline
    pipeline = PipelineRunner(runner,max_concurrent_jobs=max_concurrent_jobs)
    for data_dir in data_dirs:
        # Get for this directory
        print "Collecting data from %s" % data_dir
        if input_type == "solid":
            run_data = GetSolidDataFiles(data_dir)
        elif input_type == "fastq":
            run_data = GetFastqFiles(data_dir)
        # Add jobs to pipeline runner (up to limit of max_total_jobs)
        for data in run_data:
            pipeline.queueJob(data_dir,script,*data)
            if max_total_jobs > 0 and pipeline.nWaiting() == max_total_jobs:
                print "Maximum number of jobs queued (%d)" % max_total_jobs
                break
    # Run the pipeline
    pipeline.run()

    # Finished
    if email_addr is not None:
        print "Sending email notification to %s" % email_addr
        subject = "QC pipeline completed"
        SendEmail(subject,email_addr,pipeline.report())
    print "Finished"
