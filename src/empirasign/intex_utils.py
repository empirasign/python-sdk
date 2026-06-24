# -*- coding: utf-8 -*-
"""
utils.py

Collection of utility functions for logging, SQLite, IMAP, etc.
"""
import json
import re
import datetime
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

def _comp_px(handle, ticks):
    """
    helper function for _price32_to_dec
    """
    tot_px = 0
    if ticks[-1] == "+":
        tot_px += .5 / 32.0
        ticks = ticks[:-1]
    if len(ticks) == 3:
        tot_px += float(ticks[-1]) / 8.0 / 32.0
        tot_px += float(ticks[:2]) / 32.0
    else:
        tot_px += float(ticks) / 32.0
    tot_px += float(handle)
    return tot_px


def _price32_to_dec(price32):
    """
    convert a well-formed price32 or price with handle suffix to a
    decimal price
    """
    if not price32:
        return None
    if isinstance(price32, (int, float)):
        return float(price32)

    if m := re.search(r"( *\$ *)(.+)", price32):
        price32 = m.group(2)
    try:
        return float(price32)
    except Exception:  # pylint: disable=broad-except
        pass

    if m := re.search(r'^(\d+)-?h$', price32, re.I):
        return int(m.group(1)) + 0.25
    if m := re.search(r'^(\d+)-$', price32, re.I):
        return float(m.group(1))

    # negative price32 - specs
    if m := re.search(r'^\-\d', price32, re.I):
        parts = price32.strip().split("-")[-2:]
        if len(parts) == 2 and "" not in parts:
            try:
                return _comp_px(*parts) * -1
            except ValueError:
                pass
        return None

    price32 = price32.lower().replace("a", "")
    parts = price32.strip().split("-")
    if len(parts) == 2:
        try:
            return _comp_px(*parts)
        except ValueError:
            pass
    return None


def _split_mkt(item):
    """
    split 2 way mkts into bid and offer quotes
    """
    bid_keys = [key for key in item if '_bid' in key]
    offer_keys = [key for key in item if '_offer' in key]
    if bid_keys and offer_keys:
        bid = {x: item[x] for x in item if x not in offer_keys}
        bid['kind'] = 'bid'
        offer = {x: item[x] for x in item if x not in bid_keys}
        offer['kind'] = 'offer'
        return [offer, bid]
    return [item]


def _to_intex_bwic(bwic):
    """
    convert bwic item from /api/bwics/ to format suitable for INTEXcalc .bwic files
    """
    idata = {"Size": 0, "Securities": []}
    for bond in bwic["bonds"]:
        idata["Size"] += round(bond["of"] * 1e6)
        idata["Securities"].append({
            "Orig Face": round(bond["of"] * 1e6),
            "Tranche ID": bond["isin"]
        })
    idata["Notes"] = bwic.get("description") or ""
    if bwic.get("seller"):
        idata["Notes"] += f'Seller: {bwic["seller"]}'
    idata["Settle Date"] = bwic["settle_dt"]
    idata["Date"] = bwic["trade_dt_utc"][:-1] + "-00:00"
    fpath = bwic["trade_dt"][:10].replace("-", "") + "/" + bwic["list_id"] + ".bwic"
    return fpath, idata


def _to_intex_mktd(item):
    """
    convert market data item from /api/bonds/ to format suitable for INTEXcalc .mktd files
    """
    required_fields = ["Tranche ID", "As Of", "Color", "Quote", "Quote Type"]
    idata = {"Tranche ID": item["isin"]}
    if item['kind'] == 'nport':  # handle nport data
        idata["As Of"] = item["repPdDate"] + "T08:00:00-05:00"
        idata["Color"] = "N-PORT"
        idata["Provider"] = "EDGAR"
        balance_usd = item['balance'] / item['balanceExchangeRt']
        idata["Size"] = round(balance_usd, 3)
        try:
            idata["Quote"] = round(100 * item['valUSD'] / balance_usd, 3)
        except ZeroDivisionError:
            idata["Quote"] = None
        idata["Quote Type"] = "Price"
        idata["Fund-Name"] = item.get("seriesName")
        idata["Fund-Company"] = item.get("regName")
        return idata

    if item["kind"] in ("bwic", "pxtalk"):
        idata["As Of"] = item["trade_datetime_utc"][:-1] + "-00:00"
    else:
        if isinstance(item["trade_dt"], datetime.date):
            item["trade_dt"] = item["trade_dt"].strftime("%Y-%m-%d")
        idata["As Of"] = item["trade_dt"] + "T08:00:00-05:00"  # assume 8AM EST

    if item["kind"] == "bwic":
        idata["Provider"] = item["list_id"]
    else:
        idata["Provider"] = item.get("dealer", "unk")

    if item["kind"] in ("bwic", "pxtalk"):
        idata["Size"] = round(item["of"] * 1e6)
        if item.get("price") is not None:
            idata["Quote"] = item["price"]
            idata["Quote Type"] = "Price"
        elif item.get("price32") is not None:
            idata["Quote"] = _price32_to_dec(item["price32"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_dec") is not None:
            idata["Quote"] = item["spread_dec"]
            idata["curve"] = item.get("curve")
            idata["Quote Type"] = "Spread"
        elif item.get("spread") is not None:
            idata["Quote"] = item["spread"]
            idata["curve"] = item.get("curve")
            idata["Quote Type"] = "Spread"
        if item["kind"] == "pxtalk":
            idata["Color"] = "PX Talk"
        elif item["kind"] == 'bwic' and item['color']:
            idata["Color"] = item['color']
    elif item["kind"] == "offer":
        idata["Size"] = round(item["of_offer"] * 1e6)
        if item.get("price_offer") is not None:
            idata["Quote"] = item["price_offer"]
            idata["Quote Type"] = "Price"
        elif item.get("price32_offer") is not None:
            idata["Quote"] = _price32_to_dec(item["price32_offer"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_offer") is not None:
            idata["Quote"] = item["spread_offer"]
            idata["Quote Type"] = "Spread"
            idata["curve"] = item.get("curve")
        idata["Color"] = "Offer"
    elif item["kind"] == "bid":
        idata["Size"] = round(item["of_bid"] * 1e6)
        if item.get("price_bid") is not None:
            idata["Quote"] = item["price_bid"]
            idata["Quote Type"] = "Price"
        elif item.get("price32_bid") is not None:
            idata["Quote"] = _price32_to_dec(item["price32_bid"])
            idata["Quote Type"] = "Price"
        elif item.get("spread_bid") is not None:
            idata["Quote"] = item["spread_bid"]
            idata["Quote Type"] = "Spread"
            idata["curve"] = item.get("curve")
        idata["Color"] = "Bid"
    else:
        logger.info(f'empty conversion: {item}')
        return {}

    if all(key in idata for key in required_fields):
        return idata
    logger.info(f'empty conversion: {item}')
    return {}


def write_intex_bwic(bwic_dir, bwic_obj):
    """
    write importable INTEXCalc .bwic files to provided directory location
    """
    fpath, idata = _to_intex_bwic(bwic_obj)
    cur_dir = bwic_dir / fpath.split("/")[0]
    if not cur_dir.is_dir():
        cur_dir.mkdir()
    json_path = bwic_dir / fpath
    with open(json_path, "wb") as fp:
        json_bytes = json.dumps(idata, ensure_ascii=False, indent=2).encode("utf-8")
        fp.write(json_bytes)
    logger.info("saved bwic: %s, bonds: %s, bytes: %s, path: %s",
                bwic_obj["list_id"], len(bwic_obj["bonds"]), len(json_bytes), json_path)

    return json_path,


def _mktd_unique_key(quote):
    """
    get a tuple key used to determine uniqueness of the quote
    """
    flds = ('As Of', 'Color', 'Provider')
    return tuple(quote.get(fld) for fld in flds)


def write_intex_mktd(mktd_dir, rows, update=False):
    """
    write importable INTEXCalc .mktd files to provided directory location
    """
    quotes = defaultdict(list)
    for quote in rows:
        quotes[quote["isin"]].extend(_split_mkt(quote))

    for isin in quotes:
        data_path = mktd_dir / f"{isin}.mktd"

        mktd_quotes = [_to_intex_mktd(quote) for quote in quotes[isin]]
        mktd_quotes = list(filter(None, mktd_quotes))
        if not mktd_quotes:
            continue

        if update and data_path.is_file():
            new_keys = {_mktd_unique_key(quote) for quote in mktd_quotes}
            with open(data_path, "rb") as fp:
                file_quotes = json.load(fp)
                file_quotes = [quote for quote in file_quotes
                               if _mktd_unique_key(quote) not in new_keys]
                mktd_quotes = file_quotes + mktd_quotes

        with open(data_path, "wb") as fp:
            fp.write(json.dumps(mktd_quotes, ensure_ascii=False, indent=2).encode("utf-8"))
        logger.info("saved bond data for: %s, num_quotes: %s path: %s",
                    isin, len(mktd_quotes), data_path)
