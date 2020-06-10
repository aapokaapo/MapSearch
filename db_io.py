import sqlite3
from sqlite3 import Error, Connection
from typing import Union


def clear_requirements(conn):
    """
    Completely clears tables requirements and media_files
    :param conn:
    :return:
    """
    select_sql = """ drop table if exists media_files"""
    rows2 = select(conn, select_sql, ())
    select_sql = """create table media_files (file_id integer primary key, path text not null, type text not null, provided integer not null)"""
    rows2 = select(conn, select_sql, ())
    
    select_sql = """ drop table if exists requirements"""
    rows2 = select(conn, select_sql, ())
    select_sql = """create table requirements (req_id integer primary key, map_id integer not null, file_id integer not null, foreign key (map_id) references maps (map_id), foreign key (file_id) references media_files(file_id))"""
    rows2 = select(conn, select_sql, ())


def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        return conn
    except Error as e:
        print(e)

    return conn


def select(conn, select_sql, param):
    """
    Query all rows in the tasks table
    :param conn: the Connection object
    :return:
    """
    try:
        cur = conn.cursor()
        cur.execute(select_sql, param)

        rows = cur.fetchall()

        # for row in rows:
        #     print(row)
        return rows
    except Error as e:
        print(e)
        return
        
        
def find_map_name(keyword: str, conn: Connection) -> Union[bool, str]:
    """
    returns first map with exact match of path or name and keyword
    :param keyword:
    :param conn:
    :return:
    """
    select_sql = """ select map_path from maps where map_path = ? or map_name = ?"""
    rows = select(conn, select_sql, (keyword,)*2)
    if rows:
        rows = [a for b in rows for a in b]
        return True, rows[0]
    else:
        return False, None
