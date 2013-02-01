from __future__ import division

from numpy import histogram, zeros, median, sum
import pysam

from crumbs.statistics import draw_histogram, IntCounter, LABELS

from bam_crumbs.settings import get_setting
from bam_crumbs.utils.flag import SAM_FLAG_BINARIES, SAM_FLAGS

# pylint: disable=C0111


DEFAULT_N_BINS = get_setting('DEFAULT_N_BINS')


def count_reads(ref_name, bams, start=None, end=None):
    'It returns the count of aligned reads in the region'
    count = 0
    for bam in bams:
        count += bam.count(reference=ref_name, start=start, end=end)
    return count


class ArrayWrapper(object):
    'A thin wrapper aroung numpy array to have the same interface as IntCounter'
    def __init__(self, array, bins=DEFAULT_N_BINS, max_in_distrib=None):
        self.array = array
        self.labels = LABELS.copy()
        self._bins = bins
        self._max_in_distrib = max_in_distrib

    @property
    def min(self):
        return self.array.min()

    @property
    def max(self):
        return self.array.max()

    @property
    def average(self):
        return self.array.mean()

    @property
    def median(self):
        return median(self.array)

    @property
    def variance(self):
        return self.array.var()

    @property
    def count(self):
        return len(self.array)

    @property
    def sum(self):
        return sum(self.array)

    def calculate_distribution(self, bins=None, min_=None, max_=None):
        if max_ is None and self._max_in_distrib is not None:
            max_ = self._max_in_distrib
        if min_ is None:
            min_ = self.min
        if max_ is None:
            max_ = self.max

        if bins is None:
            bins = self._bins

        counts, bins = histogram(self.array, bins=bins, range=(min_, max_))
        return {'bin_limits': bins, 'counts': counts}

    def update_labels(self, labels):
        'It prepares the labels for output files'
        self.labels.update(labels)

    def __str__(self):
        'It writes some basic stats of the values'
        if self.count != 0:
            labels = self.labels
            # now we write some basic stats
            format_num = lambda x: '{:,d}'.format(x) if isinstance(x, int) else '%.2f' % x
            text = '{}: {}\n'.format(labels['minimum'], format_num(self.min))
            text += '{}: {}\n'.format(labels['maximum'], format_num(self.max))
            text += '{}: {}\n'.format(labels['average'],
                                      format_num(self.average))

            if labels['variance'] is not None:
                text += '{}: {}\n'.format(labels['variance'],
                                          format_num(self.variance))
            if labels['sum'] is not None:
                text += '{}: {}\n'.format(labels['sum'],
                                          format_num(self.sum))
            if labels['items'] is not None:
                text += '{}: {}\n'.format(labels['items'], self.count)
            text += '\n'
            distrib = self.calculate_distribution(max_=self._max_in_distrib,
                                                  bins=self._bins)
            text += draw_histogram(distrib['bin_limits'], distrib['counts'])
            return text
        return ''


class ReferenceStats(object):
    def __init__(self, bams, max_rpkm=None, bins=DEFAULT_N_BINS):
        self._bams = bams
        self._bins = bins
        self._max_rpkm = max_rpkm
        self._rpkms = None
        self._tot_reads = 0
        self._lengths = None
        self._count_reads()

    def _count_reads(self):
        tot_reads = self._tot_reads
        nreferences = self._bams[0].nreferences
        rpks = zeros(nreferences)
        lengths = IntCounter()
        bams = self._bams
        for bam in bams:
            if bam.nreferences != nreferences:
                msg = 'BAM files should have the same references'
                raise ValueError(msg)
            # For the references we use the first BAM to make sure that the
            # references are the same in all bams
        for index, ref in enumerate(bams[0].header['SQ']):
            length = ref['LN']
            count = count_reads(ref['SN'], bams)
            rpk = count / length
            tot_reads += count
            rpks[index] = rpk
            lengths[length] += 1
        self._lengths = lengths

        # from rpk to rpkms
        million_reads = tot_reads / 1e6
        rpks /= million_reads
        self._rpkms = ArrayWrapper(rpks, max_in_distrib=self._max_rpkm,
                                   bins=self._bins)

    @property
    def lengths(self):
        return self._lengths

    @property
    def rpkms(self):
        return self._rpkms

    def __str__(self):
        result = 'RPKMs\n'
        result += '-----\n'
        result += str(self.rpkms)
        result += '\n'
        result += 'Lengths\n'
        result += '-----\n'
        result += str(self.lengths)
        return result


def _flag_to_binary(flag):
    'It returns the indexes of the bits sets to 1 in the given flag'
    return [index for index, num in enumerate(SAM_FLAG_BINARIES) if num & flag]


class ReadStats(object):
    def __init__(self, bams):
        # TODO flag, read_group
        self._bams = bams
        self._mapqs = IntCounter()
        self._flag_counts = {}
        self._count_mapqs()

    def _count_mapqs(self):
        mapqs = self._mapqs
        flag_counts = [0] * len(SAM_FLAG_BINARIES)
        for bam in self._bams:
            for read in bam.fetch():
                mapqs[read.mapq] += 1
                for flag_index in _flag_to_binary(read.flag):
                    flag_counts[flag_index] += 1

        for count, flag_bin in zip(flag_counts, SAM_FLAG_BINARIES):
            self._flag_counts[SAM_FLAGS[flag_bin]] = count

    @property
    def mapqs(self):
        return self._mapqs

    @property
    def flag_counts(self):
        return self._flag_counts


class CoverageCounter(IntCounter):
    def __init__(self, bams):
        self._bams = bams
        self._count_cov()

    def _count_cov(self):
        for bam in self._bams:
            for column in bam.pileup():
                self[len(column.pileups)] += 1


def get_reference_counts(bam_fpath):
    'using samtools idxstats it returns a dictionary with read counts'
    counts = {}
    for line in pysam.idxstats(bam_fpath):
        ref_name, ref_lenght, mapped_reads, unmapped_reads = line.split()
        if ref_name == '*':
            ref_name = None
        counts[ref_name] = {'length': ref_lenght, 'mapped_reads': mapped_reads,
                            'unmapped_reads': unmapped_reads}
    return counts


