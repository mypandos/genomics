#!/bin/sh
#
# bowtie_build_indexes.sh
#
function usage() {
    # Print usage information
    cat <<EOF

Build color- and nucleotide-space indexes for BOWTIE.

Usage
   $script_name <genome_fasta_file>

Inputs
   <genome_fasta_file> FASTA file containing the reference genome

Outputs
   In the current directory: creates <genome_name>.*.ebwt (nucleotide-space) and
   and <genome_name>_c.*.ebwt (color-space) files
EOF
}
# Import functions
. `dirname $0`/../share/functions.sh
#
# Initialisations
script_name=`basename $0`
SCRIPT_NAME=$(rootname $script_name)
#
BOWTIE_BUILD=$(find_program bowtie-build)
if [ "$BOWTIE_BUILD" == "" ] ; then
    echo Fatal: bowtie-build program not found
    echo Check that bowtie-build is on your PATH and rerun
    exit 1
fi
#
run_date=`date`
machine=`uname -n`
user=`whoami`
run_dir=`pwd`
#
# Command line arguments
# Input fasta file for reference genome
if [ "$1" == "" ] ; then
    echo Fatal: no input fasta file specified
    usage
    exit 1
fi
FASTA_GENOME=$1
#
# Genome base name
genome=$(baserootname $FASTA_GENOME)
#
# Check input file exists
if [ ! -f "$FASTA_GENOME" ] ; then
    echo Fatal: input fasta file $FASTA_GENOME not found
    usage
    exit 1
fi
#
# Collect program version
BOWTIE_VERSION=$(get_version $BOWTIE_BUILD)
#
echo ===================================================
echo $(to_upper $SCRIPT_NAME): START
echo ===================================================
#
# Print program information, versions etc
cat <<EOF
Run date        : $run_date
Machine         : $machine
User            : $user
Run directory   : $run_dir
Input fasta file: $FASTA_GENOME
bowtie-build exe: $BOWTIE_BUILD
bowtie version  : $BOWTIE_VERSION
Genome name     : $genome
EOF
#
# ebwt outfile base names
nt_ebwt_outfile_base=${genome}
cs_ebwt_outfile_base=${genome}_c
#
# Check for fasta data directory
if [ ! -d $fasta_dir ] ; then
    echo "No fasta file directory for genome $genome"
    exit 1
fi
#
# Run bowtie-build in current directory
#
# Nucleotide space
nt_bowtie_build="$BOWTIE_BUILD -f $FASTA_GENOME $nt_ebwt_outfile_base"
echo $nt_bowtie_build
$nt_bowtie_build
# Colorspace
cs_bowtie_build="$BOWTIE_BUILD -C -f $FASTA_GENOME $cs_ebwt_outfile_base"
echo $cs_bowtie_build
$cs_bowtie_build
echo ===================================================
echo $(to_upper $SCRIPT_NAME): FINISHED
echo ===================================================
exit
