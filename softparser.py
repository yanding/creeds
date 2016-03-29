"""This module contains functions for parsing SOFT files.

__authors__ = "Gregory Gundersen, Andrew Rouillard, Axel Feldmann, Kevin Hu"
__credits__ = "Yan Kou, Avi Ma'ayan"
__contact__ = "gregory.gundersen@mssm.edu"
"""


import numpy as np

from files import SOFTFile, ANNOTFile
from log import pprint


def parse(filename, annot_filename, A_cols, B_cols):
	"""Parses SOFT files, discarding bad data, averaging duplicates, and
	converting probe IDs to gene sybmols.
	"""

	## call parse_annot to get PROBE2GENE
	global PROBE2GENE
	if annot_filename.endswith('.annot'):
		PROBE2GENE = parse_annot(annot_filename)
		platform = PROBE2GENE.keys()[0] 
	else:
		from db import PROBE2GENE
		platform = annot_filename	
	pprint('Parsing SOFT file.')
	soft_file = SOFTFile(filename).path()

	# COL_OFFSET changes because GDS files are "curated", meaning that they
	# have their gene symbols included. GSE files do not and are 1 column
	# thinner. That said, we do not trust the DGS mapping and do the probe-to-
	# gene mapping ourselves.
	if 'GDS' in filename:
		A_cols = [x.upper() for x in A_cols]
		B_cols = [x.upper() for x in B_cols]
		BOF = '!dataset_table_begin'
		EOF = '!dataset_table_end'
		COL_OFFSET = 2
	else:
		A_cols = ['"{}"'.format(x.upper()) for x in A_cols]
		B_cols = ['"{}"'.format(x.upper()) for x in B_cols]
		BOF = '!series_matrix_table_begin'
		EOF = '!series_matrix_table_end'
		COL_OFFSET = 1

	# For `dict` fast hashing to track a running mean of duplicate probe IDs.
	A = []
	B = []
	genes = []

	# For statistics about data quality.
	unconverted_probes = []
	probe_count = 0

	try:
		with open(soft_file, 'r') as soft_in:
			# Skip comments.
			discard = next(soft_in)
			while discard.rstrip() != BOF:
				discard = next(soft_in)

			# Read header and set column offset.
			header = next(soft_in).rstrip('\r\n').split('\t')
			header = header[COL_OFFSET:]
			line_length = len(header)

			# Find the columns indices.
			A_incides = [header.index(gsm) for gsm in A_cols]
			B_incides = [header.index(gsm) for gsm in B_cols]

			for line in soft_in:
				split_line = line.rstrip('\r\n').split('\t')
				if split_line[0] == EOF or split_line[1] == '--Control':
					continue

				probe  = split_line[0]
				values = split_line[COL_OFFSET:]
				probe_count = probe_count + 1

				# Perform a conservative cleanup by ignoring any rows that
				# have null values or an atypical number of columns.
				if '' in values:
					continue
				# GG: I have not seen the strings 'null' or 'NULL' in any of
				# the data, but AF or KH put this check in place and it does
				# no harm. 
				if 'null' in values or 'NULL' in values:
					continue		
				if len(values) is not line_length:
					continue
				# Three forward slashes, \\\, denotes multiple genes.
				if '\\\\\\' in probe:
					continue

				# GSD files already contain a column with gene symbols but we
				# do not trust that mapping.
				gene = _probe2gene(platform, probe)
				if gene is None:
					unconverted_probes.append(gene)
					continue

				# Don't do any of these steps until we know the data is
				# worthwhile.
				A_row = [float(values[i]) for i in A_incides]
				B_row = [float(values[i]) for i in B_incides]
				A.append(A_row)
				B.append(B_row)
				genes.append(gene)

		conversion_pct = 100.0 - float(len(unconverted_probes)) / float(probe_count)

	# Is this truly exceptional? If someone uses this API endpoint but does
	# not call the dlgeo endpoint first, this file will simply not exist!
	# Is this an acceptable API?
	except IOError:
		raise IOError('Could not read SOFT file from local server.')

	# Convert to numpy arrays, which are more compact and faster.
	A = np.array(A)
	B = np.array(B)
	genes = np.array(genes)
	return (A, B, genes, conversion_pct)


def parse_annot(filename):
	"""Parse .annot file, return a dict of dict {platform: {probe_id: gene_symbol, ...}}
	"""
	pprint('Parsing ANNOT file.')
	annot_file = ANNOTFile(filename).path()
	platform = filename.replace('.annot', '')

	PROBE2GENE = {platform: {}}
	BOF = '!platform_table_begin'
	EOF = '!platform_table_end'

	with open(annot_file, 'r') as annot_in:
		# Skip comments.
		discard = next(annot_in)
		while discard.rstrip() != BOF:
			discard = next(annot_in)

		# Read header
		header = next(annot_in).rstrip('\r\n').split('\t')

		# Find the columns indices.
		probe_index = header.index('ID')
		gene_index = header.index('Gene symbol')

		for line in annot_in:
			split_line = line.rstrip('\r\n').split('\t')
			if split_line[0] == EOF or split_line[1] == '--Control':
				continue

			probe  = split_line[probe_index]
			probe = probe.replace('"', '').replace('\'', '')
			gene = split_line[gene_index]

			# Skip probes with no corresponding genes
			if gene == '':
				continue
			# Three forward slashes, \\\, denotes multiple genes.
			if '\\\\\\' in probe:
				continue

			PROBE2GENE[platform][probe] = gene
	return PROBE2GENE


def platform_supported(platform):
	if platform not in PROBE2GENE:
		return False
	return True


def _probe2gene(platform, probe):
	"""Converts probe IDs to gene symbols. Does not check if the platform is
	supported.
	"""

	# Strip any potential quotation marks.
	probe = probe.replace('"', '').replace('\'', '')
	try:
		if probe in PROBE2GENE[platform]:
			return PROBE2GENE[platform][probe]
	# This should never occur, given that we check if the platform is in the
	# dictionary. But just in case.
	except AttributeError:
		return None
	return None