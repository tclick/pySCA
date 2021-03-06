#!/usr/bin/env python
"""
The scaProcessMSA script conducts the basic steps in multiple sequence alignment (MSA) pre-processing for SCA, and stores the results using the python tool pickle:  

     1)  Trim the alignment, either by truncating to a reference sequence (specified with the -t flag) or by removing
         excessively gapped positions (set to positions with more than 40% gaps)
     2)  Identify/designate a reference sequence in the alignment, and create a mapping of the alignment numberings to position numberings 
         for the reference sequence. The reference sequence can be specified in one of four ways:
              a)  By supplying a PDB file - in this case, the reference sequence is taken from the PDB (see the pdb kwarg)
              b)  By supplying a reference sequence directly (as a fasta file - see the refseq kwarg)
              c)  By supplying the index of the reference sequence in the alignment (see the refseq kwarg)
              d)  If no reference sequence is supplied by the user, one is automatically selected using the scaTools function chooseRef.
         The position numbers (for mapping the alignment) can be specified in one of three ways:
              a) By supplying a PDB file - in this case the alignment positions are mapped to structure positions 
              b) By supplying a list of reference positions (see the refpos kwarg)
              c) If no reference positions are supplied by the user, sequential numbering (starting at 1) is assumed.
     3)  Filter sequences to remove highly gapped sequences, and sequences with an identity below or above some minimum 
         or maximum value to the reference sequence (see the parameters kwarg)
     4)  Filter positions to remove highly gapped positions (default 20% gaps, can also be set using --parameters)
     5)  Calculate sequence weights and write out the final alignment and other variables
              

:Arguments: 
     Input_MSA.fasta (the alignment to be processed, typically the headers contain taxonomic information for the sequences).

:Keyword Arguments:
     --pdb, -s         PDB identifier (ex: 1RX2)  
     --chainID, -c     chain ID in the PDB for the reference sequence
     --species, -f     species of the reference sequence
     --refseq, -r      reference sequence, supplied as a fasta file
     --refpos, -o      reference positions, supplied as a text file with one position specified per line
     --refindex, -i    reference sequence number in the alignment, COUNTING FROM 0
     --parameters, -p  list of parameters for filtering the alignment: 
                       [max_frac_gaps for positions, max_frac_gaps for sequences, min SID to reference seq, max SID to reference seq]
                       default values: [0.2, 0.2, 0.2, 0.8] (see filterPos and filterSeq functions for details)
     --selectSeqs, -n  subsample the alignment to (1.5 * the number of effective sequences) to reduce computational time, default: False
     --truncate, -t    truncate the alignment to the positions in the reference PDB, default: False
     --matlab, -m      write out the results of this script to a matlab workspace for further analysis 
     --output          specify a name for the outputfile 

:Example: 
>>> ./scaProcessMSA.py Inputs/PF00071_full.an -s 5P21 -c A -f 'Homo sapiens' 

:By: Rama Ranganathan
:On: 8.5.2014
Copyright (C) 2015 Olivier Rivoire, Rama Ranganathan, Kimberly Reynolds
This program is free software distributed under the BSD 3-clause
license, please see the file LICENSE for details.
"""
from __future__ import (absolute_import, division, unicode_literals)

import argparse
import copy
import os
import sys
import time

from Bio import SeqIO
from scipy.io import savemat
from six import print_

from six.moves import (cPickle, range)
import numpy as np
import os.path as path
import scaTools as sca
import scipy.cluster.hierarchy as sch


if __name__ == '__main__':
    # parse inputs
    parser = argparse.ArgumentParser()
    parser.add_argument("alignment", help='Input Sequence Alignment')
    parser.add_argument("-s", "--pdb", dest="pdbid", help="PDB identifier (ex: 1RX2)")
    parser.add_argument("-c", "--chainID", dest="chainID", default='A',
                        help="chain ID in the PDB for the reference sequence")
    parser.add_argument("-f", "--species", dest="species", help="species of the reference sequence")
    parser.add_argument("-r", "--refseq", dest="refseq", help="reference sequence, supplied as a fasta file")
    parser.add_argument("-o", "--refpos", dest="refpos",
                        help="reference positions, supplied as a text file with one position specified per line")
    parser.add_argument("-i", "--refindex", dest="i_ref", type=int,
                        help="reference sequence number in the alignment, COUNTING FROM 0")
    parser.add_argument("-p", "--parameters", dest="parameters", default=[0.2, 0.2, 0.2, 0.8], type=float, nargs=4,
                        help="list of parameters for filtering the alignment: [max_frac_gaps for positions, max_frac_gaps for sequences, min SID to reference seq, max SID to reference seq] default values: [0.2, 0.2, 0.2, 0.8] (see filterPos and filterSeq functions for details)")
    parser.add_argument("-n", "--selectSeqs", action="store_true", dest="Nselect", default=False,
                        help="subsample the alignment to (1.5 * the number of effective sequences) to reduce computational time, default: False")
    parser.add_argument("-t", "--truncate", action="store_true", dest="truncate", default=False,
                        help="truncate the alignment to the positions in the reference PDB, default: False")
    parser.add_argument("-m", "--matlab", action="store_true", dest="matfile", default=False,
                        help="write out the results of this script to a matlab workspace for further analysis")
    parser.add_argument("--output", dest="outputfile", default=None, help="specify an outputfile name")
    options = parser.parse_args()

    # A little bit of error checking/feedback for the user.
    if options.i_ref is None:
        if options.species != None and options.pdbid == None:
            print_("No PDBid, ignoring species...")
            options.species = None
        if options.refseq is not None and options.refpos is None:
            print_("Using reference sequence but no position list provided! Just numbering positions 1 to length(sequence)")
            if options.pdbid is not None:
                print_("And...ignoring the PDB file...")
                options.pdbid = None
            options.refpos = range(len(options.refseq)) + 1
        if options.refseq is not None and options.refpos is not None:
            print_("Using the reference sequence and position list...")
            if options.pdbid is not None:
                print_("And...ignoring the PDB file...")
                options.pdbid = None
    else:
        i_ref = options.i_ref

    # Read in initial alignment
    headers_full, sequences_full = sca.readAlg(options.alignment)
    print_('Loaded alignment of {:d} sequences, {:d} positions.'.format(len(headers_full), len(sequences_full[0])))

    # Check the alignment and remove sequences containing non-standard amino acids
    print_("Checking alignment for non-standard amino acids")
    alg_out = list()
    hd_out = list()
    for i, k in enumerate(sequences_full):
        flag = 0
        for aa in k:
            if aa not in 'ACDEFGHIKLMNPQRSTVWY-':
                flag = 1
        if (flag == 0):
            alg_out.append(k)
            hd_out.append(headers_full[i])
    headers_full = hd_out
    sequences_full = alg_out
    print_("Aligment size after removing sequences with non-standard amino acids: {:d}".format(len(sequences_full)))

    # Do an initial trimming to remove excessively gapped positions - this is
    # critical for building a correct ATS
    print_("Trimming alignment for highly gapped positions (80% or more).")
    alg_out, poskeep = sca.filterPos(sequences_full, [1], 0.8)
    sequences_ori = sequences_full
    sequences_full = alg_out
    print_("Alignment size post-trimming: {:d} positions".format(len(sequences_full[0])))

    # If i_ref is directly provided, we use it, ignoring all else.  Otherwise,
    # we explore the other ways of specifying a reference sequences: (1)
    # providing a PDBid (chainID defaults to 'A'), (2) providing the protein
    # sequence with position numbers (defaults to just sequence numbering).
    # If none of these is provided, we just make an alignment based numbering
    # for ats.  If a PDBid is provided, there is an option to also provide
    # species information to permit identifying the reference sequence in the
    # MSA without use of external packages for fast pairwise alignments.

    if options.i_ref is None:
        if options.pdbid is not None:
            try:
                seq_pdb, ats_pdb, dist_pdb = sca.pdbSeq(options.pdbid, options.chainID)
                if options.species is not None:
                    try:
                        print_("Finding reference sequence using species-based best match..")
                        i_ref = sca.MSAsearch(
                            headers_full, sequences_full, seq_pdb, options.species)
                        Options_ref = i_ref
                        print_("reference sequence index is: {:d}".format(i_ref))
                        print_(headers_full[i_ref])
                        print_(sequences_full[i_ref])
                    except:
                        print_("Cant find the reference sequence using species-based best_match! Using global MSAsearch...")
                        try:
                            i_ref = sca.MSAsearch(headers_full, sequences_full, seq_pdb)
                            options.i_ref = i_ref
                            print_("reference sequence index is: {:d}".format(i_ref))
                            print_(headers_full[i_ref])
                            print_(sequences_full[i_ref])
                        except:
                            sys.exit("Error!!  Can't find reference sequence...")
                else:
                    try:
                        print_("Finding reference sequence using global MSAsearch...")
                        i_ref = sca.MSAsearch(headers_full, sequences_full, seq_pdb)
                        options.i_ref = i_ref
                        print_("reference sequence index is: {:d}".format(i_ref))
                        print_(headers_full[i_ref])
                        print_(sequences_full[i_ref])
                    except:
                        sys.exit("Error!!  Can't find reference sequence...")
                sequences, ats = sca.makeATS(sequences_full, ats_pdb, seq_pdb, i_ref, options.truncate)
                dist_new = np.zeros((len(ats), len(ats)))
                for (j, pos1) in enumerate(ats):
                    for (k, pos2) in enumerate(ats):
                        if k != j:
                            if (pos1 == '-') or (pos2 == '-'):
                                dist_new[j, k] == 1000
                            else:
                                ix_j = ats_pdb.index(pos1)
                                ix_k = ats_pdb.index(pos2)
                                dist_new[j, k] = dist_pdb[ix_j, ix_k]
                dist_pdb = dist_new
            except:
                sys.exit("Error!!! Something wrong with PDBid or path...")
        elif options.refseq is not None:
            print_("Finding reference sequence using provided sequence file...")
            try:
                h_tmp, s_tmp = sca.readAlg(options.refseq)
                i_ref = sca.MSAsearch(headers_full, sequences_full, s_tmp[0])
                options.i_ref = i_ref
                print_("reference sequence index is: {:d}".format(i_ref))
                print_(headers_full[i_ref])
                if options.refpos is not None:
                    try:
                        f = open(options.refpos, 'r')
                        ats_tmp = [line.rstrip('\n') for line in f]
                        f.close()
                    except:
                        print_("Error reading reference position file! Using default numbering 1 to number of positions")
                        ats_tmp = range(len(sequences[0]))
                else:
                    print_("No reference position list provided.  Using default numbering 1 to number of positions")
                    ats_tmp = range(len(sequences[0]))
                sequences, ats = sca.makeATS(
                    sequences_full, ats_tmp, s_tmp[0], i_ref, options.truncate)
            except:
                sys.exit("Error!!  Can't find reference sequence...")
        else:
            msa_num = sca.lett2num(sequences_full)
            i_ref = sca.chooseRefSeq(sequences_full)
            print_("No reference sequence given, chose as default ({:d}): {}".format(i_ref, headers_full[i_ref]))
            sequences = sequences_full
            ats = range(len(sequences[0]))
    else:
        print_("using provided reference index {:d}".format(i_ref))
        print_(headers_full[i_ref])
        s_tmp = sequences_ori[i_ref]
        try:
            if options.refpos is not None:
                f = open(options.refpos, 'r')
                ats_tmp = [line.rstrip('\n') for line in f]
                # print ats_tmp
                f.close()
            else:
                ats_tmp = range(len(sequences_full[0]))
            sequences, ats = sca.makeATS(sequences_full, ats_tmp, s_tmp, i_ref, options.truncate)
        except:
            sys.exit("Error!!  Can't find reference sequence...")

    # filtering sequences and positions, calculations of effective number of seqs
    print_("Conducting sequence and position filtering: alignment size is {:d} seqs, {:d} pos".format(len(sequences),
                                                                                                      len(sequences[0])))
    if options.pdbid is not None:
        print_("ATS and distmat size - ATS: {:d}, distmat: {:d} x {:d}".format(len(ats), len(dist_pdb), len(dist_pdb[0])))
    else:
        print_("ATS should also have {:d} positions - ATS: {:d}".format(len(sequences[0]), len(ats)))

    if i_ref is not None:
        alg0, seqw0, seqkeep = sca.filterSeq(sequences, i_ref, max_fracgaps=options.parameters[1],
                                             min_seqid=options.parameters[2], max_seqid=options.parameters[3])
    else:
        alg0, seqw0, seqkeep = sca.filterSeq(sequences, max_fracgaps=options.parameters[1], min_seqid=options.parameters[2],
                                             max_seqid=options.parameters[3])

    headers = [headers_full[s] for s in seqkeep]
    alg1, iposkeep = sca.filterPos(alg0, seqw0, options.parameters[0])
    ats = [ats[i] for i in iposkeep]
    if options.pdbid is not None:
        distmat = dist_pdb[np.ix_(iposkeep, iposkeep)]
    effseqsprelimit = int(seqw0.sum())
    Nseqprelimit = len(alg1)
    print_("After filtering: alignment size is {:d} seqs, {:d} effective seqs, {:d} pos".format(len(alg1), effseqsprelimit,
                                                                                                len(alg1[0])))

    # Limitation of total sequences to [1.5 * # ofeffective sequences] if Nselect is set to True
    if (options.Nselect):
        seqsel = sca.randSel(seqw0, int(1.5 * effseqsprelimit), [seqkeep.index(i_ref)])
        alg = [alg1[s] for s in seqsel]
        hd = [headers[s] for s in seqsel]
    else:
        alg = alg1
        hd = headers

    # calculation of final MSA, sequence weights
    seqw = sca.seqWeights(alg)
    effseqs = seqw.sum()
    msa_num = sca.lett2num(alg)
    Nseq, Npos = msa_num.shape
    print_("Final alignment parameters:")
    print_("Number of sequences: M = {:d}".format(Nseq))
    print_("Number of effective sequences: M' = {:.0f}".format(np.round(effseqs)))
    print_("Number of alignment positions: L = {:d}".format(Npos))

    if options.pdbid is not None:
        print_("Number of positions in the ats: {:d}".format(len(ats)))
        structPos = [i for (i, k) in enumerate(ats) if k != '-']
        print_("Number of structure positions mapped: {:d}".format(len(structPos)))
        print_("Size of the distance matrix: {:d} x {:d}".format(len(distmat), len(distmat[0])))

    # saving the important stuff. Everything is stored in a file called
    # [MSAname]_sequence.db.  But we will also write out the final processed
    # alignment to a fasta file.

    path_list = options.alignment.split(os.sep)
    fn = path_list[-1]
    fn_noext = fn.split(".")[0]
    with open(".".join((path.join("Outputs", fn_noext + "processed"), "fasta")), "w") as f:
        for i in range(len(alg)):
            #f.write(">" + hd[i] + "\n")
            print_(">{}".format(hd[i]), file=f)
            print_(alg[i], file=f)

    D = {}
    D['alg'] = alg
    D['hd'] = hd
    D['msa_num'] = msa_num
    D['seqw'] = seqw
    D['Nseq'] = Nseq
    D['Npos'] = Npos
    D['ats'] = ats
    D['effseqs'] = effseqs
    D['limitseqs'] = options.Nselect
    D['NseqPrelimit'] = Nseqprelimit
    D['effseqsPrelimit'] = effseqsprelimit
    if options.pdbid is not None:
        D['pdbid'] = options.pdbid
        D['pdb_chainID'] = options.chainID
        D['distmat'] = distmat
    if options.refseq is not None:
        D['refseq'] = options.refseq
    if options.refpos is not None:
        D['refpos'] = options.refpos
    D['i_ref'] = i_ref
    D['trim_parameters'] = options.parameters
    D['truncate_flag'] = options.truncate

    if (options.outputfile is not None):
        fn_noext = options.outputfile
    print_(" ".join(("Opening database file", path.join("Outputs", fn_noext))))
    db = {}
    db['sequence'] = D

    if options.matfile:
        matfile = path.join("Outputs", fn_noext)
        savemat(matfile, sca.convert_keys_to_string(sca.convert_values_to_string(db)), oned_as='column')

    with open(".".join((path.join("Outputs", fn_noext), "db")), mode='wb') as db_out:
        cPickle.dump(db, db_out, protocol=cPickle.HIGHEST_PROTOCOL)
