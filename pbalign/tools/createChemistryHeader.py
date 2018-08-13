#!/usr/bin/env python
"""createChemistryHeader.py gets chemistry triple information for movies in
a BLASR-produced SAM file. It writes a new SAM header file that contains the
chemisty information. This header can be used with samtools reheader. Most
of the work is actually done by BasH5Reader.
"""
import argparse
import copy
import logging
import sys

import pysam

from pbcore.io import BasH5IO, FofnIO

log = logging.getLogger('main')

MOVIENAME_TAG = 'PU'

class ChemistryLoadingException(Exception):
    """Exception when chemistry lookup fails."""
    pass

def format_rgds_entries(rgds_entries):
    """Turn the RG DS dictionary into a list of strings that
    can be placed into a header object.
    """

    rgds_strings = {}
    for rg_id in rgds_entries:
        rgds_string = ("BINDINGKIT={b};SEQUENCINGKIT={s};"
                       "SOFTWAREVERSION={v}"
                       .format(b=rgds_entries[rg_id][0],
                               s=rgds_entries[rg_id][1],
                               v=rgds_entries[rg_id][2]))
        rgds_strings[rg_id] = rgds_string
    return rgds_strings

def extend_header(old_header, new_rgds_strings):
    """Create a new SAM/BAM header, adding the RG descriptions to the
    old_header.
    """

    new_header = copy.deepcopy(old_header)

    for rg_entry in new_header['RG']:
        try:
            new_ds_string = new_rgds_strings[rg_entry['ID']]
        except KeyError:
            continue

        if 'DS' in rg_entry:
            rg_entry['DS'] += ';' + new_ds_string
        else:
            rg_entry['DS'] = new_ds_string

    return new_header

def get_chemistry_info(sam_header, input_filenames, fail_on_missing=False):
    """Get chemistry triple information for movies referenced in a SAM
    header.

    Args:
        sam_header: a pysam.Samfile.header, which is a multi-level dictionary.
                    Movie names are read from RG tags in this header.
        input_filenames: a list of bas, bax, or fofn filenames.
        fail_on_missing: if True, raise an exception if the chemistry
                         information for a movie in the header cannot be
                         found. If False, just log a warning.
    Returns:
        a list of strings that can be written as DS tags to RG entries in the
        header of a new SAM or BAM file. For example,
        ['BINDINGKIT:xxxx;SEQUENCINGKIT:yyyy;SOFTWAREVERSION:2.0']

    Raises:
        ChemistryLoadingException if chemistry information cannot be found
        for a movie in the header and fail_on_missing is True.
    """

    # First get the full list of ba[sx] files, reading through any fofn or xml
    # inputs
    bas_filenames = []
    for filename in input_filenames:
        bas_filenames.extend(FofnIO.enumeratePulseFiles(filename))

    # Then get the chemistry triple for each movie in the list of bas files
    triple_dict = {}
    for bas_filename in bas_filenames:
        bas_file = BasH5IO.BasH5Reader(bas_filename)
        movie_name = bas_file.movieName
        chem_triple = bas_file.chemistryBarcodeTriple
        triple_dict[movie_name] = chem_triple

    # Finally, find the movie names that appear in the header and create CO
    # lines with the chemistry triple
    if 'RG' not in sam_header:
        return []
    rgds_entries = {}
    for rg_entry in sam_header['RG']:
        rg_id = rg_entry['ID']
        rg_movie_name = rg_entry[MOVIENAME_TAG]

        try:
            rg_chem_triple = triple_dict[rg_movie_name]
            rgds_entries[rg_id] = rg_chem_triple
        except KeyError:
            err_msg = ("Cannot find chemistry information for movie {m}."
                       .format(m=rg_movie_name))
            if fail_on_missing:
                raise ChemistryLoadingException(err_msg)
            else:
                log.warning(err_msg)

    rgds_strings = format_rgds_entries(rgds_entries)

    return rgds_strings

def get_parser():
    """Return an ArgumentParser for pbcompress options."""

    desc = ("createChemistryHeader creates a SAM header that contains the "
            "chemistry information used by Quiver.")

    parser = argparse.ArgumentParser(
        prog='getChemistryHeader.py', description=desc,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument("--debug", help="Output detailed log information.",
                        action='store_true')

    def sam_or_bam_filename(val):
        """Check that val names a SAM or BAM file."""
        if not (val.endswith(".bam") or val.endswith(".sam")):
            raise argparse.ArgumentTypeError(
                "File must end with .sam or .bam. {f} doesn't "
                "end with either of those."
                .format(f=val))
        return val

    parser.add_argument(
        "input_alignment_file",
        help="A SAM or BAM file produced by BLASR.",
        type=sam_or_bam_filename)

    parser.add_argument(
        "output_header_file",
        help=("Name of the SAM or BAM header file that will be created with "
              "chemistry information loaded."),
        type=sam_or_bam_filename)

    parser.add_argument(
        "--bas_files",
        help=("The bas or bax files containing the reads that were aligned in "
              "the input_alignment_file. Also can be a fofn of bas or bax "
              "files."),
        nargs='+',
        required=True)

    return parser

def setup_log(alog, file_name=None, level=logging.DEBUG, str_formatter=None):
    """Util function for setting up logging."""

    if file_name is None:
        handler = logging.StreamHandler(sys.stderr)
    else:
        handler = logging.FileHandler(file_name)

    if str_formatter is None:
        str_formatter = ('[%(levelname)s] %(asctime)-15s '
                         '[%(name)s %(funcName)s %(lineno)d] %(message)s')

    formatter = logging.Formatter(str_formatter)
    handler.setFormatter(formatter)
    alog.addHandler(handler)
    alog.setLevel(level)

def main():
    """Entry point."""
    parser = get_parser()
    args = parser.parse_args()

    if args.debug:
        setup_log(log, level=logging.DEBUG)
    else:
        setup_log(log, level=logging.INFO)

    input_file = pysam.Samfile(args.input_alignment_file, 'r') # pylint: disable=no-member
    input_header = input_file.header
    log.debug("Read header from {f}.".format(f=input_file.filename))

    chemistry_rgds_strings = get_chemistry_info(
        input_header, args.bas_files)

    new_header = extend_header(input_header, chemistry_rgds_strings)

    if args.output_header_file.endswith('.bam'):
        output_file = pysam.Samfile(args.output_header_file, 'wb', # pylint: disable=no-member
                                    header=new_header)
    elif args.output_header_file.endswith('.sam'):
        output_file = pysam.Samfile(args.output_header_file, 'wh', # pylint: disable=no-member
                                    header=new_header)

    output_file.close()

if __name__ == '__main__':
    main()
