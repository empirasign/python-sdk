# -*- coding: utf-8 -*-
"""
parser/schemas.py

Return schemas and their sqlite data types for Empirasign Parser API
Refer to /examples/parser for use patterns
"""

# /parse-corp/
CORP_SCHEMA = (
    ('bbg_ticker', 'TEXT'),
    ('cusip', 'TEXT'),
    ('isin', 'TEXT'),
    ('figi', 'TEXT'),
    ('of_bid', 'REAL'),
    ('of_offer', 'REAL'),
    ('price_bid', 'REAL'),
    ('price_offer', 'REAL'),
    ('spread_bid', 'REAL'),
    ('spread_offer', 'REAL'),
    ('curve', 'TEXT'),
    ('asw_bid', 'REAL'),
    ('asw_offer', 'REAL'),
    ('axe_bid', 'INTEGER'),
    ('axe_offer', 'INTEGER'),
    ('yield_bid', 'REAL'),
    ('yield_offer', 'REAL'),
    ('ytc_bid', 'REAL'),
    ('ytc_offer', 'REAL'),
    ('ytm_bid', 'REAL'),
    ('ytm_offer', 'REAL'),
    ('ytw_bid', 'REAL'),
    ('ytw_offer', 'REAL'),
    ('margin', 'REAL'),
    ('notes', 'TEXT'),
    ('dealer', 'TEXT'),
    ('trade_dt', 'TEXT'),
    ('settle_dt', 'TEXT'),
)

# /parse-cds/
CDS_SCHEMA = (
    ('asset_class', 'TEXT'),
    ('bbg_ticker', 'TEXT'),
    ('ticker', 'TEXT'),
    ('parsed_name', 'TEXT'),
    ('term_id', 'TEXT'),
    ('isin', 'TEXT'),
    ('figi', 'TEXT'),
    ('markit_ticker', 'TEXT'),
    ('contract_reference_obligation', 'TEXT'),
    ('eligible_reference_entity', 'TEXT'),
    ('ref_entity_name', 'TEXT'),
    ('sector', 'TEXT'),
    ('red_code', 'TEXT'),
    ('date_included_for_clearing', 'TEXT'),
    ('credit_derivatives_definition', 'TEXT'),
    ('tenor', 'TEXT'),
    ('tier', 'TEXT'),
    ('currency', 'TEXT'),
    ('doc_clause', 'TEXT'),
    ('running_coupon', 'REAL'),
    ('size_bid', 'REAL'),
    ('size_offer', 'REAL'),
    ('spread_bid', 'REAL'),
    ('spread_offer', 'REAL'),
    ('upfront_bid', 'REAL'),
    ('upfront_offer', 'REAL'),
    ('is_axe', 'INTEGER'),
    ('axe_bid', 'INTEGER'),
    ('axe_offer', 'INTEGER'),
    ('level_bid', 'REAL'),
    ('level_offer', 'REAL'),
    ('i_nav', 'TEXT'),
    ('to_maturity', 'TEXT'),
    ('from_maturity', 'TEXT'),
    ('maturity', 'TEXT'),
    ('dealer', 'TEXT'),
    ('firmness', 'TEXT'),
    ('change', 'REAL'),
    ('cod', 'REAL'),
    ('cow', 'REAL'),
)

# /parse-run/
# MyData: excel_results are flattened with wb_name embedded

# Standard API response excel_results:
# {
#     <wb 1>: [<bond 1>, <bond 2>, ...],
#     <wb 2>: [<bond 1>, <bond 2>, ...],
#     ...
# }

# MyData:
# [
#     {'wb_name': <wb 1>, **<bond 1>},
#     {'wb_name': <wb 1>, **<bond 2>},
#     ...
#     {'wb_name': <wb 2>, **<bond 1>},
#     {'wb_name': <wb 2>, **<bond 2>},
#     ...
# ]

RUNS_SCHEMA = (
    ('bbg_ticker', 'TEXT'),
    ('cusip', 'TEXT'),
    ('isin', 'TEXT'),
    ('of_bid', 'REAL'),
    ('of_offer', 'REAL'),
    ('cf_bid', 'REAL'),
    ('cf_offer', 'REAL'),
    ('price_bid', 'REAL'),
    ('price_offer', 'REAL'),
    ('price32_bid', 'TEXT'),
    ('price32_offer', 'TEXT'),
    ('spread_bid', 'REAL'),
    ('spread_offer', 'REAL'),
    ('curve', 'TEXT'),
    ('speed', 'TEXT'),
    ('mtg_wal', 'REAL'),
    ('maxls', 'REAL'),
    ('notes', 'TEXT'),
    ('dealer', 'TEXT'),
    ('trade_dt', 'TEXT'),
    ('settle_dt', 'TEXT'),
    ('wb_name', 'TEXT'),
)

# /parse-bwic/
# MyData: bonds data flattened with auction data embedded and numbered with bwic_id

# Standard API response data:
# [
#     {
#         <bwic 1>
#         'bonds': [<bond 1>, <bond 2>, ...]
#     },
#     {
#         <bwic 2>
#         'bonds': [<bond 1>, <bond 2>, ...]
#     },
#     ...
# ]

# Mydata:
# [
#     <bwic 1> + <bond 1>,
#     <bwic 1> + <bond 2>,
#     ...
#     <bwic 2> + <bond 1>,
#     <bwic 2> + <bond 2>,
#     ...
# ]

BWIC_AUCTION_SCHEMA = (
    ('bid_time', 'TEXT'),
    ('bid_method', 'TEXT'),
    ('trade_dt', 'TEXT'),
    ('settle_dt', 'TEXT'),
    ('settle_desc', 'TEXT'),
    ('bwic_match', 'TEXT'),
    ('curve', 'TEXT'),
    ('header', 'TEXT'),
    ('bwic_id', 'INTEGER'),
)

BWIC_BOND_SCHEMA = (
    ('of', 'REAL'),
    ('bbg_ticker', 'TEXT'),
    ('cusip', 'TEXT'),
    ('isin', 'TEXT'),
    ('settle_dt', 'TEXT'),
    ('pxtalk', 'TEXT'),
    ('price', 'REAL'),
    ('spread_dec', 'REAL'),
    ('curve', 'TEXT'),
    ('line', 'TEXT'),
    ('other', 'TEXT'),
)

# common mydata meta fields across sectors
MYDATA_SCHEMA = (
    ('tx_id', 'TEXT'),
    ('msg_received', 'TEXT'),
    ('path', 'TEXT'),
)
