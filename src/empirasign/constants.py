# -*- coding: utf-8 -*-
"""
constants.py
"""

# figi_securitytype
# subset of https://api.openfigi.com/v3/mapping/values/securityType
SECTYPES = ("MBS 30yr", "Agncy CMO Other", "MBS 15yr", "MBS Other", "MBS ARM", "Prvt CMO Other",
            "Agncy CMO IO", "CF", "CMBS", "MBS 20yr", "ABS Other", "Agncy CMO FLT", "Prvt CMO FLT",
            "Agncy CMO Z", "Agncy CMBS", "ABS Home", "Agncy CMO INV", "Prvt CMO IO",
            "Agncy CMO PO", "MBS 10yr", "ABS Auto", "SBA Pool", "MBS balloon", "Prvt CMO PO",
            "Agncy ABS Other", "ABS Card", "Prvt CMO Z", "SN", "Prvt CMO INV", "HB",
            "Agncy ABS Home", "Canadian", "MV")
# figi_securitytype2
# subset of https://api.openfigi.com/v3/mapping/values/securityType2
SECTYPES2 = ("Pool", "CMO", "Whole Loan", "ABS", "TBA", "CMBS", "LL", "ABS Other", "MML", "CRE",
             "SME", "ABS/MEZZ", "ABS/HG", "TRP", "HY", "CDO2", "RMBS", "IG", "CDS", "TRP/REIT",
             "CDS(CRP)", "MEZZ", "CDS(ABS)", "2ND LIEN", "TRP/BK", "SME/MEZZ")

# Empirasign sectors
RUNS_SECTORS = ("abs", "agarm", "agcmo", "us-clo", "eu-clo", "cmbs", "crt", "eu", "nonag", "spec")

BWIC_MAJOR_SECTORS = ('abs', 'agency', 'all-prime', 'clo', 'cmbs', 'conabs', 'euro', 'naresi',
                      'nonag', 'spec')
# subsectors of major sectors
BWIC_MINOR_SECTORS = ('agarm', 'agcmbs', 'agcmo', 'aj', 'alta-15', 'alta-30', 'alta-a', 'am',
                      'auto', 'card', 'cre-cdo', 'crt', 'equip', 'eu-abs', 'eu-clo', 'eu-cmbs',
                      'eu-resi', 'heloc', 'heq', 'io', 'mezz', 'mh', 'other', 'prime', 'prime-15',
                      'prime-30', 'prime-a', 'snr', 'student', 'subprime', 'unk', 'us-clo', 'utility')
BWIC_SECTORS = BWIC_MAJOR_SECTORS + BWIC_MINOR_SECTORS + ('mtge',) # mtge icludes all sectors
