#!/usr/bin/env python
"""
The scaCore script runs the core calculations for SCA, and stores the output using the python tool pickle. These calculations can be divided into two parts:

     1)  Sequence correlations:
              a) Compute simMat = the global sequence similarity matrix for the alignment
              b) Compute Useq and Uica = the eigenvectors (and independent components) for the following sequence correlation matrices:

                 * unweighted (:math:`U^0`)
                 * sequence weights applied (:math:`U^1`)
                 * both sequence and position weights applied (:math:`U^2`)
                  
     2)  Positional correlations: 
              a) Compute the single-site position weights and positional conservation values (:math:`D_i` and :math:`D_i^a`)
              b) Compute the dimension-reduced SCA correlation matrix :math:`\\tilde{C_{ij}}`, the projected alignment :math:`tX`, 
                 and the projector 
              c) Compute Ntrials of the randomized SCA matrix, and the eigenvectors and eigenvalues associated with each

:Arguments: 
     *.db (the database produced by running scaProcessMSA.py).

:Keyword Arguments:
     -n              norm type for dimension-reducing the sca matrix. Options are: 'spec' (the spectral norm) or 'frob' (frobenius norm). Default: frob
     -l              lambda parameter for pseudo-counting the alignment. Default: 0.03
     --Ntrials, -t   number of randomization trials
     --matlab, -m    write out the results of these calculations to a matlab workspace for further analysis

:Example: 
>>> ./scaCore.py PF00071_full.db 

:By: Rama Ranganathan, Kim Reynolds
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
from scipy.stats import scoreatpercentile
from scipy.stats import t
from six import print_

from six.moves import (cPickle, range)
import matplotlib.pyplot as plt
import numpy as np
import os.path as path
import scaTools as sca
import scipy.cluster.hierarchy as sch


if __name__ == '__main__':

    # parse inputs
    parser = argparse.ArgumentParser()
    parser.add_argument("database", help='database from running scaProcessMSA')
    parser.add_argument("-n", dest="norm", default='frob',
                        help="norm type for dimension-reducing the sca matrix. Options are: 'spec' (the spectral norm) or 'frob' (frobenius norm). Default: frob")
    parser.add_argument("-t", "--Ntrials", dest="Ntrials", default=10, type=int, help="number of randomization trials")
    parser.add_argument("-l", dest="lbda", default=0.03, type=float,
                        help="lambda parameter for pseudo-counting the alignment. Default: 0.03")
    parser.add_argument("-m", "--matlab", dest="matfile",  action="store_true", default=False,
                        help="write out the results of these calculations to a matlab workspace for further analysis")
    options = parser.parse_args()

    if (options.norm != 'frob') & (options.norm != 'spec'):
        sys.exit("The option -n must be set to 'frob' or 'spec' - other keywords are not allowed.")

    # extract the necessary stuff from the database...
    with open(options.database, mode='rt') as db_file:
        db_in = cPickle.load(db_file)
        D_in = db_in['sequence']

    msa_num = D_in['msa_num']
    seqw = D_in['seqw']
    Nseq = D_in['Nseq']
    Npos = D_in['Npos']
    ats = D_in['ats']
    hd = D_in['hd']

    # sequence analysis
    print_("Computing the sequence projections.")
    Useq, Uica = sca.seqProj(msa_num, seqw, kseq=30, kica=15)
    simMat = sca.seqSim(msa_num)

    # SCA calculations
    print_("Computing the SCA conservation and correlation values.")
    Wia, Dia, Di = sca.posWeights(msa_num, seqw, options.lbda)
    Csca, tX, Proj = sca.scaMat(msa_num, seqw, options.norm, options.lbda)

    # Matrix randomizations
    print_("Computing matrix randomizations...")
    start = time.time()
    Vrand, Lrand, Crand = sca.randomize(msa_num, options.Ntrials, seqw, options.lbda)
    end = time.time()
    print_("Randomizations complete, {:d} trials, time: {:.1f} minutes".format(options.Ntrials, (end - start) / 60))

    # saving...
    path_list = options.database.split(os.sep)
    fn = path_list[-1]
    fn_noext = fn.split(".")[0]

    D = {}
    D['Useq'] = Useq
    D['Uica'] = Uica
    D['simMat'] = simMat
    D['lbda'] = options.lbda
    D['Dia'] = Dia
    D['Di'] = Di
    D['Csca'] = Csca
    D['tX'] = tX
    D['Proj'] = Proj
    D['Ntrials'] = options.Ntrials
    D['Vrand'] = Vrand
    D['Lrand'] = Lrand
    D['Crand'] = Crand

    db = {}
    db['sequence'] = D_in
    db['sca'] = D

    print_(" ".join(("Calculations complete, writing to database file", path.join("Outputs", fn_noext))))
    if options.matfile:
        matfile = path.join("Outputs", fn_noext)
        savemat(matfile, sca.convert_keys_to_string(sca.convert_values_to_string(db)), oned_as='column')

    with open(".".join((path.join("Outputs", fn_noext), "db")), mode='wb') as db_out:
        cPickle.dump(db, db_out, protocol=cPickle.HIGHEST_PROTOCOL)
