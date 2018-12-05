#!/usr/bin/env python
"""Takes in a rgn.fofn and corresponding cmp.h5. Uses the
alignments from the cmp.h5 to mask corresponding regions of
the rgn.h5s. Writes output to a new rgn.fofn."""

import os
import sys
import logging
import argparse
import re

from pbcore.io import CmpH5Reader, EmptyCmpH5Error
import traceback
from pbalign.utils.RgnH5IO import RgnH5Reader, RgnH5Writer

__VERSION__ = "0.3.2"


class AlignedReadsMasker(object):
    """Mask aligned reads in a region table.
    Input: inCmpFile - a cmp.h5 file with alignments.
           inRgnFofn - a input fofn of region table files.
    Output: outRgnFofn - a output fofn of region table files.
    Generate new rgn.h5 files, which mask aligned reads in `inRgnFofn`
    by overwritting their corresponding HQ regions to (0, 0). The
    generated new rgn.h5 files have to be stored in the same directory
    as `outRgnFofn`.
    """
    def __init__(self, inCmpFile, inRgnFofn, outRgnFofn):
        self.inCmpFile = inCmpFile
        self.inRgnFofn = inRgnFofn
        self.outRgnFofn = outRgnFofn

    def maskAlignedReads(self):
        """Mask aligned zmws in region tables."""
        logging.info("Log level set to INFO")
        logging.debug("Log Level set to DEBUG")

        alignedReads = self._extractAlignedReads()
        nreads = sum([len(v) for v in alignedReads.values()])
        logging.info("Extracted {r} reads ({m} movies) from {f}".format(
            r=nreads, m=len(alignedReads), f=self.inCmpFile))

        outDir = os.path.splitext(self.outRgnFofn)[0]

        if not os.path.exists(outDir):
            os.mkdir(outDir)

        outRgnFofn = open(self.outRgnFofn, 'w')

        # Check for new format generated from bax files.
        # m130226_022844_...131362_s1_p0.3.rgn.h5
        rx = re.compile(r'\.[0-9].rgn\.h5')

        for rgnH5FN in [line.strip() for line in open(self.inRgnFofn, 'r')]:
            if not rgnH5FN.endswith("rgn.h5"):
                logging.error("Region table file " +
                              "{0} should be a rgn.h5 file.".format(rgnH5FN))
                return 1
            rgnReader = RgnH5Reader(rgnH5FN)

            basename = os.path.basename(rgnH5FN)
            # Default movie name
            movieName = rgnReader.movieName

            # 'movieId' is used to write the file compatible with bax style.
            # m130226_022844_ethan_c100471672550000001823071906131362_s1_p0.3
            if rx.search(basename):
                movieId = re.split(r'.rgn\.h5', basename)[0]
            else:
                # old format
                # m130226_022844_....131362_s1_p0.rgn.h5
                movieId = movieName

            outH5FN = os.path.abspath(os.path.join(outDir,
                                      movieId + ".rgn.h5"))
            outRgnFofn.write("{o}\n".format(o=outH5FN))
            rgnWriter = RgnH5Writer(outH5FN)
            rgnWriter.writeScanDataGroup(rgnReader.scanDataGroup)

            logging.info("Processing {f}...".format(f=rgnH5FN))
            for rt in rgnReader:
                if movieName in alignedReads and \
                   rt.holeNumber in alignedReads[movieName]:
                    rt.setHQRegion(0, 0)
                rgnWriter.addRegionTable(rt)

            rgnReader.close()
            rgnWriter.close()

        outRgnFofn.close()
        return 0

    def _extractAlignedReads(self):
        """Grab a mapping of all movie names of aligned reads to hole numbers.
           and return { Movie: [HoleNumbers ...] }.
        """
        alignedReads = {}

        try:
            reader = CmpH5Reader(self.inCmpFile)

            for movie in reader.movieInfoTable.Name:
                alignedReads.setdefault(movie, set())

            for i in reader:
                alignedReads[i.movieInfo.Name].add(i.HoleNumber)
            reader.close()
        except (IndexError, EmptyCmpH5Error):
            msg = "No aligned reads found in {x}".format(x=self.inCmpFile)
            sys.stderr.write(msg + "\n")
            logging.warn(msg)

        return alignedReads


def getParser():
    """Add arguments to an argument parser and return it.
       usage = "%prog [--help] [options] cmp.h5 rgn.fofn rgn_out.fofn"
    """

    desc = "Use in.cmp.h5 to mask corresponing regions of files in " + \
           "in.rgn.h5, write output to a new rgn.fofn."
    parser = argparse.ArgumentParser(
        description=desc,
        version=__VERSION__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument(
        "-l", "--logFile", default=None,
        help="Specify a file to log to. Defaults to stderr.")
    parser.add_argument(
        "-d", "--debug", default=False, action="store_true",
        help="Increases verbosity of logging")
    parser.add_argument(
        "-i", "--info", default=False, action="store_true",
        help="Display informative log entries")
    parser.add_argument(
        "inCmpFile", type=str,
        help="An input cmp.h5 file.")
    parser.add_argument(
        "inRgnFofn", type=str,
        help="A fofn of input region table files.")
    parser.add_argument(
        "outRgnFofn", type=str,
        help="A fofn of output region table files.")
    return parser


def configLog(isInfo, isDebug, logFile):
    """Sets up logging based on command line arguments.
       Allows for three levels of logging:
        logging.error( ): always emitted
        logging.info( ): emitted with --info or --debug
        logging.debug( ): only with --debug
    """
    logLevel = logging.DEBUG if isDebug else \
        logging.INFO if isInfo else logging.ERROR
    logFormat = "%(asctime)s [%(levelname)s] %(message)s"

    if logFile is not None:
        logging.basicConfig(filename=logFile, level=logLevel,
                            format=logFormat)
    else:
        logging.basicConfig(stream=sys.stderr, level=logLevel,
                            format=logFormat)


def run(inCmpFile, inRgnFofn, outRgnFofn):
    """Main function to run mask aligned reads()."""

    masker = AlignedReadsMasker(inCmpFile, inRgnFofn, outRgnFofn)
    try:
        masker.maskAlignedReads()
    except Exception as e:
        logging.error(e, exc_info=True)
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


def main():
    """Main function."""
    parser = getParser()
    args = parser.parse_args()
    configLog(args.debug, args.info, args.logFile)

    rcode = run(args.inCmpFile, args.inRgnFofn, args.outRgnFofn)
    logging.info("Exiting {f} {v} with rturn code {r}.".format(
                 r=rcode, f="mask_aligned_reads.py", v=__VERSION__))
    return rcode

if __name__ == "__main__":
    sys.exit(main())
