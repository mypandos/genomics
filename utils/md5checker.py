#!/bin/env python
#
#     md5checker.py: check files and directories using md5 checksums
#     Copyright (C) University of Manchester 2012 Peter Briggs
#
########################################################################
#
# md5checker.py
#
#########################################################################

"""md5checker

Utility for checking files and directories using md5 checksums.
"""

#######################################################################
# Module metadata
#######################################################################

__version__ = "0.1.0"

#######################################################################
# Import modules that this module depends on
#######################################################################

import sys
import os
import optparse
import tempfile
# Put ../share onto Python search path for modules
SHARE_DIR = os.path.abspath(
    os.path.normpath(
        os.path.join(os.path.dirname(sys.argv[0]),'..','share')))
sys.path.append(SHARE_DIR)
import Md5sum

#######################################################################
# Functions
#######################################################################

def compute_md5sums(dirn,output_file=None):
    """Compute and write MD5 sums for all files in a directory

    Walks the directory tree under the specified directory and
    computes the MD5 for each file it finds. The sums are written
    along with the names of the files either to stdout or to the
    specified file name.

    Note that the output format is compatible with the Linux
    'md5sum' program's '-c' option.

    Arguments:
      dirn: directory to run the MD5 sum computation on
      output_file: (optional) name of file to write MD5 sums to

    Returns:
      Zero on success, 1 if errors were encountered
    """
    retval = 0
    if output_file:
        fp = open(output_file,'w')
    else:
        fp = sys.stdout
    for d in os.walk(dirn):
        # Calculate md5sum for each file
        for f in d[2]:
            try:
                filen = os.path.normpath(os.path.join(d[0],f))
                chksum = Md5sum.md5sum(filen)
                fp.write("%s  %s\n" % (chksum,filen))
            except IOError, ex:
                # Error accessing file, report and skip
                sys.stderr.write("%s: error while generating MD5 sum: '%s'\n" % (filen,ex))
                sys.stderr.write("%s: skipped\n" % filen)
                retval = 1
    if output_file:
        fp.close()
    return retval

def verify_md5sums(chksum_file,verbose=False):
    """Check the MD5 sums for all entries specified in a file

    For all entries in the supplied file, check the MD5 sum is
    the same as that calculated by the function, and report
    whether they match or are different.

    The input file can either be output from this program or
    from the Linux 'md5sum' program.

    Arguments:
      chksum_file: name of the file containing the MD5 sums
      verbose: (optional) if True then report status for all
        files checked, plus a summary; otherwise only report
        failures

    Returns:
      Zero on success, 1 if errors were encountered
    """
    retval = 0
    nsuccess = 0
    failures = []
    # Perform the verification
    for line in open(chksum_file,'rU'):
        items = line.strip().split()
        if len(items) != 2:
            sys.stderr.write("Badly formatted MD5 checksum line, skipped\n")
            continue
        chksum = items[0]
        chkfile = items[1]
        try:
            new_chksum = Md5sum.md5sum(chkfile)
            if chksum == new_chksum:
                report("%s: OK" % chkfile,verbose)
                nsuccess += 1
            else:
                sys.stderr.write("%s: FAILED\n" % chkfile)
                failures.append(chkfile)
                retval = 1
        except IOError, ex:
            if not os.path.exists(chkfile):
                sys.stderr.write("%s: FAILED (missing file)\n" % chkfile)
            else:
                sys.stderr.write("%s: FAILED (%s)\n" % (chkfile,ex))
            failures.append(chkfile)
            retval = 1
    # Summarise
    nfailed = len(failures)
    report("Summary: %d files checked, %d okay %d failed" % 
           (nsuccess + nfailed,nsuccess,nfailed),
           verbose)
    return retval

def diff_directories(dirn1,dirn2,verbose=False):
    """Check one directory against another using MD5 sums

    This compares one directory against another by computing the
    MD5 sums for the contents of the first, and then checking these
    against the second.

    (Essentially this is automatically performing the compute/verify
    steps in a single operation.)

    Note that if there are different files in one directory compared
    with the other then this function will give different results
    depending on the order theh directories are specified. However
    for common files the actual MD5 sums will be the same regardless
    of order.

    Arguments:
      dirn1: "source" directory
      dirn2: "target" directory to be compared to dirn1
      verbose: (optional) if True then report status for all
        files checked; otherwise only report summary

    Returns:
      Zero on success, 1 if errors were encountered
    """
    # Move to first dir and generate temporary Md5sum file
    os.chdir(dirn1)
    fp,tmpfile = tempfile.mkstemp()
    os.close(fp)
    retval1 = compute_md5sums('.',output_file=tmpfile)
    # Run this against the second directory
    os.chdir(dirn2)
    retval2 = verify_md5sums(tmpfile,verbose=verbose)
    # Delete temporary file
    os.remove(tmpfile)
    # Return status
    return max(retval1,retval2)

def compute_md5sum_for_file(filen,output_file=None):
    """Compute and write MD5 sum for specifed file

    Computes the MD5 sum for a file, and writes the sum and the file
    name either to stdout or to the specified file name.

    Note that the output format is compatible with the Linux
    'md5sum' program's '-c' option.

    Arguments:
      filen: file to compute the MD5 sum for
      output_file: (optional) name of file to write MD5 sum to

    Returns:
      Zero on success, 1 if errors were encountered
    """
    retval = 1
    if output_file:
        fp = open(output_file,'w')
    else:
        fp = sys.stdout
    try:
        chksum = Md5sum.md5sum(filen)
        fp.write("%s  %s\n" % (chksum,filen))
    except IOError, ex:
        # Error accessing file, report and skip
        sys.stderr.write("%s: error while generating MD5 sum: '%s'\n" % (filen,ex))
        retval = 1
    if output_file:
        fp.close()
    return retval

def diff_files(filen1,filen2,verbose=False):
    """Check that the MD5 sums of two files match

    This compares two files by computing the MD5 sums for each.

    Arguments:
      filen1: "source" file
      filen2: "target" file to be compared with filen1
      verbose: (optional) if True then report status for all
        files checked; otherwise only report summary

    Returns:
      Zero on success, 1 if errors were encountered
    """
    # Generate Md5sum for each file
    retval = 1
    try:
        chksum1 = Md5sum.md5sum(filen1)
        chksum2 = Md5sum.md5sum(filen2)
        if chksum1 == chksum2:
            report("OK: MD5 sums match",verbose)
            retval = 0
        else:
            report("FAILED: MD5 sums don't match",verbose)
    except IOError, ex:
        report("FAILED (%s)" % ex,verbose)
    return retval

def report(msg,verbose=False):
    """Write text to stdout

    Convenience function for dealing with verbose/silent modes of
    operation: rhe supplied text in 'msg' is only written if the verbose
    argument is set to True.
    """
    if verbose: print "%s" % (msg)

#######################################################################
# Main program
#######################################################################    

if __name__ == "__main__":
    usage = """
  %prog -d SOURCE_DIR DEST_DIR
  %prog -d FILE1 FILE2
  %prog [ -o CHKSUM_FILE ] DIR
  %prog [ -o CHKSUM_FILE ] FILE
  %prog -c CHKSUM_FILE"""
    p = optparse.OptionParser(usage=usage,
                              version="%prog "+__version__,
                              description=
                              "Compute and verify MD5 checksums for files and directories.")

    # Define options
    p.add_option('-d','--diff',action="store_true",dest="diff",default=False,
                 help="for two directories: check that contents of directory DIR1 are present "
                 "in DIR2 and have the same MD5 sums; for two files: check that FILE1 and FILE2 "
                 "have the same MD5 sums")
    p.add_option('-c','--check',action="store_true",dest="check",default=False,
                 help="read MD5 sums from the specified file and check them")
    p.add_option('-q','--quiet',action="store_false",dest="verbose",default=True,
                 help="suppress output messages and only report failures")

    # Directory differencing
    group = optparse.OptionGroup(p,"Directory comparison (-d, --diff)",
                                 "Check that the contents of SOURCE_DIR are present in "
                                 "TARGET_DIR and have matching MD5 sums. Note that files that "
                                 "are only present in TARGET_DIR are not reported.")
    p.add_option_group(group)

    # File differencing
    group = optparse.OptionGroup(p,"File comparison (-d, --diff)",
                                 "Check that FILE1 and FILE2 have matching MD5 sums.")
    p.add_option_group(group)

    # Checksum generation
    group = optparse.OptionGroup(p,"Checksum generation",
                                 "MD5 checksums are calcuated for all files in the specified "
                                 "directory, or for a single specified file.")
    group.add_option('-o','--output',action="store",dest="chksum_file",default=None,
                     help="optionally write computed MD5 sums to CHKSUM_FILE (otherwise the "
                     "sums are written to stdout). The output format is the same as that used "
                     "by the Linux 'md5sum' tool.")
    p.add_option_group(group)

    # Checksum verification
    group = optparse.OptionGroup(p,"Checksum verification (-c, --check)",
                                 "Check MD5 sums for each of the files listed in the "
                                 "specified CHKSUM_FILE relative to the current directory. "
                                 "This option behaves the same as the Linux 'md5sum' tool.")
    p.add_option_group(group)

    # Process the command line
    options,arguments = p.parse_args()

    # Figure out mode of operation
    if options.check:
        # Running in "check" mode
        if len(arguments) != 1:
            p.error("-c: needs single argument (file containing MD5 sums)")
        chksum_file = arguments[0]
        if not os.path.isfile(chksum_file):
            p.error("Checksum '%s' file not found (or is not a file)" % chksum_file)
        # Do the verification
        status = verify_md5sums(chksum_file,verbose=options.verbose)
    elif options.diff:
        # Running in "diff" mode
        if len(arguments) != 2:
            p.error("-d: needs two arguments (pair of directories or files to compare)")
        # Get directories/files as absolute paths
        source = os.path.abspath(arguments[0])
        target = os.path.abspath(arguments[1])
        if os.path.isdir(source) and os.path.isdir(target):
            # Compare two directories
            report("Recursively checking files in %s against copies in %s" % (source,target),
                   options.verbose)
            status = diff_directories(source,target,verbose=options.verbose)
        elif os.path.isfile(source) and os.path.isfile(target):
            # Compare two files
            report("Checking MD5 sums for %s and %s" % (source,target),options.verbose)
            status = diff_files(source,target,verbose=options.verbose)
        else:
            p.error("Supplied arguments must be a pair of directories or a pair of files")
    else:
        # Running in "compute" mode
        if len(arguments) != 1:
            p.error("Needs a single argument (name of directory to generate MD5 sums for)")
        # Check if output file was specified
        output_file = None
        if options.chksum_file:
            output_file = options.chksum_file
        # Generate the checksums
        if os.path.isdir(arguments[0]):
            status = compute_md5sums(arguments[0],output_file)
        elif os.path.isfile(arguments[0]):
            status = compute_md5sum_for_file(arguments[0],output_file)
        else:
            p.error("Supplied argument must be an existing directory or file")
    # Finish
    sys.exit(status)
