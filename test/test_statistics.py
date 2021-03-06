
import os.path
import unittest
from subprocess import check_output

import pysam

from bam_crumbs.utils.test import TEST_DATA_DIR
from bam_crumbs.utils.bin import BIN_DIR
from bam_crumbs.statistics import (count_reads, ReferenceStats, ReadStats,
                                   CoverageCounter, _flag_to_binary,
                                   get_reference_counts,
                                   get_reference_counts_dict,
                                   get_genome_coverage, get_bam_readgroups,
                                   mapped_count_by_rg, GenomeCoverages)

# pylint: disable=R0201
# pylint: disable=R0904
# pylint: disable=C0111


class StatsTest(unittest.TestCase):
    def test_count(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        bam = pysam.Samfile(bam_fpath)
        assert count_reads('reference1', [bam]) == 9
        assert count_reads('reference2', [bam]) == 9
        assert count_reads('reference1', [bam], start=1, end=10) == 0
        assert count_reads('reference1', [bam], start=0, end=500) == 9

    def test_reference_stats(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        bam = pysam.Samfile(bam_fpath)
        refstats = ReferenceStats([bam], n_most_abundant_refs=1)
        rpkms = refstats.rpkms
        assert rpkms.min - 291715.28 < 0.1
        assert rpkms.max - 600240.1 < 0.1
        assert rpkms.average - 445977.7 < 0.1
        assert rpkms.median - 445977.7 < 0.1
        assert rpkms.variance - 23796889620.7 < 0.1
        assert rpkms.count == 2
        assert rpkms.sum - 891955.38 < 0.1
        assert refstats.most_abundant_refs[0]['reference'] == 'reference1'
        assert list(rpkms.calculate_distribution()['counts'])[0] == 1
        assert 'minimum:' in str(rpkms)
        assert 'Most represented' in str(refstats)

        refstats = ReferenceStats([bam, bam])
        n_max_expressed = len(set([i['reference'] for i in refstats.most_abundant_refs]))
        assert n_max_expressed == 2
        max_rpkm = refstats.most_abundant_refs[0]['rpkm']
        assert max_rpkm - refstats.rpkms.max < 0.1
        assert refstats.rpkms.max - 600240.1 < 0.1

    def test_ref_stats_bin(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')

        bin_ = os.path.join(BIN_DIR, 'calculate_ref_stats')
        # help
        assert 'usage' in check_output([bin_, '-h'])

        assert 'RPKMs' in check_output([bin_, bam_fpath])

    def test_read_stats(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        bam = pysam.Samfile(bam_fpath)
        stats = ReadStats([bam])
        assert stats.mapqs.count == 18
        assert stats.mapqs.min == 28
        assert stats.mapqs.max == 149
        assert stats.flag_counts['is_unmapped'] == 0

    def test_coverage_distrib(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        bam = pysam.Samfile(bam_fpath)
        cov = CoverageCounter([bam])
        assert cov.count == 147
        assert cov.min == 6
        assert cov.max == 9

    def test_genome_coverage_distrib(self):
        bam_fhand = open(os.path.join(TEST_DATA_DIR, 'seqs.bam'))
        cov = GenomeCoverages([bam_fhand])
        assert repr(cov.get_mapq_counter(0)) == 'IntCounter({9: 146, 6: 1})'
        assert repr(cov.get_mapq_counter(20)) == 'IntCounter({9: 146, 6: 1})'
        assert repr(cov.get_mapq_counter(30)) == 'IntCounter({9: 73, 3: 73, 6: 1})'

    def test_flag_to_binary(self):
        assert not _flag_to_binary(0)
        assert _flag_to_binary(1) == [0]
        assert _flag_to_binary(2) == [1]
        assert _flag_to_binary(1 | 2) == [0, 1]

    def test_ref_counts(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        counts = list(get_reference_counts(bam_fpath))
        assert counts[2] == {'unmapped_reads': 0, 'reference': None,
                             'length': None, 'mapped_reads': 0}
        assert counts[1] == {'unmapped_reads': 0, 'reference': 'reference2',
                             'length': 1714, 'mapped_reads': 9}
        counts = get_reference_counts_dict([bam_fpath])
        assert  None in counts.keys()
        assert  'reference2' in counts.keys()
        assert  'reference2' in counts.keys()

    def test_get_readgroup(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        readgroups = get_bam_readgroups(pysam.Samfile(bam_fpath))
        assert readgroups == [{'LB': 'group1', 'ID': 'group1+454',
                               'PL': '454', 'SM': 'group1+454'},
                              {'LB': 'group2', 'ID': 'group2+454',
                               'PL': '454', 'SM': 'group2+454'}]

    def test_mapped_counts(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        map_counts = mapped_count_by_rg([bam_fpath])
        assert map_counts['group1+454']['mapped'] == 9

        bam_fpath = os.path.join(TEST_DATA_DIR, 'sample_no_rg.bam')
        map_counts = mapped_count_by_rg([bam_fpath])
        assert map_counts['sample_no_rg']['mapped'] == 1
        assert 'bigger_mapqx' not in map_counts['sample_no_rg']
        map_counts = mapped_count_by_rg([bam_fpath], mapqx=20)
        assert map_counts['sample_no_rg']['bigger_mapqx'] == 1

        map_counts = mapped_count_by_rg([bam_fpath], mapqx=50)
        assert map_counts['sample_no_rg']['bigger_mapqx'] == 0

    def test_bin_mapped_counts(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')

        bin_ = os.path.join(BIN_DIR, 'count_mapped_by_rg')
        cmd = [bin_, bam_fpath]
        output = check_output(cmd)
        assert "group2+454" in output


class GenomeCoverageTest(unittest.TestCase):

    def test_genome_cover(self):
        bam_fpath = os.path.join(TEST_DATA_DIR, 'seqs.bam')
        scatter_group = get_genome_coverage([open(bam_fpath)])
        assert scatter_group.items() == [(0, 2400), (9, 144), (6, 3)]


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'StatsTest.test_genome_coverage_distrib']
    unittest.main()
