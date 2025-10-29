# -*- coding: utf-8 -*-
"""
utils.py

Collection of utility functions for logging, SQLite, IMAP, etc.
"""
import sys
import logging
import logging.handlers
import itertools

# ------------ Generic Helpers ------------


def get_logger(file_path):
    "return a standard logger for our example scripts"
    rfh = logging.handlers.RotatingFileHandler(filename=file_path, maxBytes=5000000)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s - %(levelname)-8s - %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=[rfh, logging.StreamHandler(sys.stdout)])
    return logging.getLogger()


def chunker(iterable, n):
    "returns chunks of tuples for any iterable"
    source = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(source, n))
        if not chunk:
            return
        yield chunk


#-------------------- Database Helpers  -------------------------------


def create_sqlite_table(sqlite_conn, tbl_name, cols, indices=None):
    "create new SQLite table"
    cursor = sqlite_conn.cursor()
    cursor.execute(f"DROP TABLE IF EXISTS {tbl_name};")
    cursor.execute(make_create_table(tbl_name, cols))

    # index columns for better performance
    indices = indices or {}
    for index, col in indices.items():
        q = f"CREATE INDEX {index} ON {tbl_name}({col} ASC);"
        cursor.execute(q)

    sqlite_conn.commit()


def make_insertp(tbl, columns, ph="?"):
    "make an INSERT SQL command with placeholders"
    cols_str = ", ".join([f"`{col}`" for col in columns])
    vals_str = ", ".join([ph] * len(columns))
    return f"INSERT INTO {tbl} ({cols_str}) VALUES ({vals_str});"


def make_create_table(tbl_name, col_defs):
    "generate a SQLite CREATE TABLE query"
    cols_str = ", ".join([f"`{col_name}` {col_type.upper()}" for col_name, col_type in col_defs])
    return f"CREATE TABLE {tbl_name} ({cols_str});"


def make_update(tbl, data, pks, ph='?'):
    """
    execute a complete UPDATE SQL command
    """
    match_clause = " AND ".join([f"{key} = {ph}" for key in pks])
    set_clause = ",".join([f"{key} = {ph}" for key in data])
    return f"UPDATE {tbl} SET {set_clause} WHERE {match_clause};"


def upsert(cursor, tbl, pks, data, ph="?", ignore_cols=None):
    """
    if record matches data on pks, do an update, otherwise do an insert
    """
    if ignore_cols:
        cols = set(data.keys()) - set(ignore_cols)
    else:
        cols = data.keys()

    match_clause, query_keys = [], []
    for key in cols:
        if data[key] is None:
            match_clause.append(f"{key} IS NULL")
        else:
            match_clause.append(f"{key} = {ph}")
            query_keys.append(key)

    if match_clause:
        match_clause = " AND ".join(match_clause)
    else:
        match_clause = "1"  # this ensure dupes and error raised

    q = f"SELECT COUNT(*) FROM {tbl} WHERE {match_clause};"
    cursor.execute(q, tuple(data[key] for key in query_keys))
    results = cursor.fetchall()[0][0]

    if results > 1:  # we have dupes
        raise ValueError(f'duplicate record: {data}')
    if results == 1:
        return "NO CHANGES"

    # check for partial match on pks
    match_clause = " AND ".join([f"{key} = {ph}" for key in pks])
    q = f"SELECT COUNT(*) FROM {tbl} WHERE {match_clause};"
    cursor.execute(q, tuple(data[key] for key in pks))
    results = cursor.fetchall()[0][0]
    if results > 1:  # our pks do not constitute uniqueness
        raise ValueError(f'primary keys retrieve multiple records--uniqueness violated: {pks}')
    if results == 1:
        q = make_update(tbl, data, pks, ph)
        cursor.execute(q, tuple(list(data.values()) + [data[key] for key in pks]))
        return 'UPDATE'
    # no matches found; so do an insert
    q = make_insertp(tbl, data.keys(), ph)
    cursor.execute(q, tuple(data.values()))
    return 'INSERT'


#-------------------- IMAP Helpers  -------------------------------


def safe_create_folder(imap, folder_name):
    """
    create folder_name if it does not already exist
    """
    all_folders = [x.decode('utf-8').split(' "/" ')[1][1:-1] for x in imap.list()[1]]
    if folder_name not in all_folders:
        imap.create(folder_name)
        return True
    return False
