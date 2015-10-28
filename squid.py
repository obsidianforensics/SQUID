#!/usr/bin/env python

import sqlite3
import os
import sys
import json
import time
import hashlib
import argparse
import textwrap
import xlsxwriter

__author__ = "Ryan Benson"
__version__ = "0.5.0"
__email__ = "ryan@obsidianforensics.com"


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class squid(object):
    def __init__(self, db_name=None, structure={}, path=None, program_family=None, program_name=None, program_version=None, squid_id=None):
        self.db_name = db_name
        self.structure = structure
        self.path = path
        self.program_family = program_family
        self.program_name = program_name
        self.program_version = program_version
        self.squid_id = squid_id

    def build_structure(self):

        self.structure = {}

        # Connect to SQLite db
        try:
            db = sqlite3.connect(self.path)
            cursor = db.cursor()
        except:
            return

        # Find the names of each table in the db
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
        except sqlite3.OperationalError:
            # print("\nSQLite3 error; is the file open?  If so, please close it and try again.")
            return
        except:
            # print "Couldn't open {}".format(self.path)
            return

        # For each table, find all the columns in it
        for table in tables:
            try:
                cursor.execute('PRAGMA table_info({})'.format(str(table[0])))
                columns = cursor.fetchall()
                # print columns

                # Create a dict of lists of the table/column names
                self.structure[str(table[0])] = {}
                for column in columns:
                    self.structure[str(table[0])][str(column[1])] = {}
                    self.structure[str(table[0])][str(column[1])]['type'] = str(column[2])
                    self.structure[str(table[0])][str(column[1])]['not_null'] = column[3]
                    self.structure[str(table[0])][str(column[1])]['default_value'] = column[4]
            except:
                return


def compare_dbs(candidate, known):
    # These values are used to compute how similar two databases are, based on how many tables, columns, and column
    # attributes are shared between them.  These initial values are set to give table name matches the most weight at
    # 12, each column name match half that weight at 6, and all three attributes total a weight of 3 (1 each).  These
    # weights can be modified as you see fit to tweak the comparison equation.
    TABLE_WEIGHT = 12
    COLUMN_WEIGHT = 6
    # SQUID considers three attributes for each column: type, default_value, and not_null.
    ATTRIBUTE_WEIGHT = 1
    attributes = ['type', 'default_value', 'not_null']
    # Initialize both the scores to 0.
    candidate_score = 0
    known_score = 0

    # For every table in the candidate DB
    for candidate_table in candidate.structure.keys():
        # if the candidate table name matches a table name in the known DB
        if candidate_table in known.structure.keys():
            # increase the candidate's score
            candidate_score += TABLE_WEIGHT
            # for each column in the matching table in the candidate DB
            for candidate_column in candidate.structure[candidate_table]:
                # if the candidate column name matches a column in the known table
                if candidate_column in known.structure[candidate_table].keys():
                    # increase the candidate's score
                    candidate_score += COLUMN_WEIGHT
                    # for each attribute SQUID is tracking
                    for attribute in attributes:
                        # if the attribute value for the candidate column matches the known column
                        if candidate.structure[candidate_table][candidate_column][attribute] == \
                                known.structure[candidate_table][candidate_column][attribute]:
                            # increase the candidate score
                            candidate_score += ATTRIBUTE_WEIGHT
                        # increase the known score, regardless
                        known_score += ATTRIBUTE_WEIGHT

                else:
                    # increase the known score instead
                    known_score += COLUMN_WEIGHT

        # if the candidate table name doesn't match any known table name
        else:
            # increase the known score instead
            known_score += TABLE_WEIGHT
            # and also increase the known score for all the columns in that non-matching table
            for candidate_column in candidate.structure[candidate_table]:
                known_score += COLUMN_WEIGHT
                # also do this for attr(*3)?

    # add the points for each table and column in the known DB to the known score
    for known_table in known.structure.keys():
        known_score += TABLE_WEIGHT
        for known_column in known.structure[known_table].keys():
            known_score += COLUMN_WEIGHT

    return candidate_score, known_score, "{:.1f}".format(100 * float(candidate_score) / known_score)


def learn_db(db_name, new_database_path, program_family, program_name, program_version):
    new_database = squid(db_name, path=new_database_path, program_family=program_family, program_name=program_name,
                         program_version=program_version)
    new_database.build_structure()
    new_database.db_name = os.path.split(new_database.db_name)[1]

    if new_database.structure != {}:
        # Connect to SQUID db
        database_path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'catalog.sqlite')
        db = sqlite3.connect(database_path)
        with db:
            db.row_factory = dict_factory
            cursor = db.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS known_databases("
                           "program_family TEXT,"
                           "program_name TEXT,"
                           "program_version TEXT,"
                           "db_name TEXT,"
                           "structure TEXT,"
                           "structure_md5 TEXT)")

            m = hashlib.md5()
            m.update(json.dumps(new_database.structure))

            # Check if we already have a database with this structure
            cursor.execute("SELECT * FROM known_databases WHERE structure_md5 = :candidate",
                           {'candidate': str(m.hexdigest())})
            matches = cursor.fetchall()

            # If there is only one match in the catalog, ask if we should add to it, make a new entry, or do nothing.
            if len(matches) == 1:
                existing_versions = json.loads(matches[0]['program_version'])
                existing_versions_friendly = ', '.join(map(str, existing_versions))
                print "\n - A database with this structure is already in the catalog."
                print "      DB Name: {}".format(matches[0]['db_name'])
                print "      Program: {}".format(matches[0]['program_name'])
                print "      Version: {}".format(existing_versions_friendly)
                if program_version not in existing_versions:
                    update = raw_input("   Would you like to add this new version number to this existing entry in "
                                       "the\n   SQUID catalog? \n   (Y)es or (N)o? ")
                    if update[0].lower() == 'y':
                        new_versions = json.loads(matches[0]['program_version'])
                        new_versions.append(program_version)
                        try:
                            new_versions.sort(key=float)
                        except:
                            new_versions.sort()
                        cursor.execute("UPDATE known_databases SET program_version = ? WHERE (structure_md5 = ? "
                                       "AND program_name = ?)", (json.dumps(new_versions), matches[0]['structure_md5'],
                                                                 matches[0]['program_name']))
                    elif update[0].lower() == 'n':
                        add_new = raw_input("   Would you like to add this database as a new entry in the SQUID "
                                       "catalog? \n   (Y)es or (N)o? ")
                        if add_new[0].lower() == 'y':
                            version_list = []
                            version_list.append(new_database.program_version)
                            cursor.execute("INSERT INTO known_databases (program_family, program_name, program_version,"
                                           " db_name, structure, structure_md5) VALUES (?, ?, ?, ?, ?, ?)",
                                           (new_database.program_family, new_database.program_name,
                                           json.dumps(version_list), new_database.db_name,
                                           json.dumps(new_database.structure), m.hexdigest()))
                else:
                    print textwrap.fill("Not adding as version {} is already associated with this catalog entry"
                                  .format(program_version), width=75, initial_indent="   ", subsequent_indent="   ")

            # If there is more than one match in the catalog, ask if we should add to it, make a new entry, or skip.
            elif len(matches) > 1:
                print "\n {} databases with this structure are already in the catalog.\n".format(len(matches))
                for count, match in enumerate(matches):
                    existing_versions = json.loads(matches[count]['program_version'])
                    if isinstance(existing_versions, list):
                        existing_versions = ', '.join(map(str, existing_versions))
                    print "   {}. DB Name: {}".format(count+1, matches[count]['db_name'])
                    print "      Program: {}".format(matches[count]['program_name'])
                    print "      Version: {}".format(existing_versions)

                update = raw_input("   Which entry would you like to add this new version number to? \n [Enter # or "
                                   "(N)one] ")
                try:
                    if 0 < int(update[0]) <= len(matches):
                        new_versions = json.loads(matches[int(update[0])-1]['program_version'])
                        if program_version not in new_versions:
                            new_versions.append(program_version)
                            new_versions.sort()
                        cursor.execute("UPDATE known_databases SET program_version = ? WHERE (structure_md5 = ? "
                                       "AND program_name = ?)",
                                       (json.dumps(new_versions), matches[int(update[0])-1]['structure_md5'],
                                        matches[int(update[0])-1]['program_name']))
                    else:
                        print "   Invalid entry. Skipping this database."
                except:
                    pass

                if program_version not in matches[0]['program_version']:
                    new_versions = json.loads(matches[0]['program_version'])
                    new_versions.append(program_version)
                    new_versions.sort()

            else:
                version_list = []
                version_list.append(new_database.program_version)
                cursor.execute("INSERT INTO known_databases (program_family, program_name, program_version, db_name, "
                               "structure, structure_md5) VALUES (?, ?, ?, ?, ?, ?)",
                               (new_database.program_family, new_database.program_name,
                                json.dumps(version_list), new_database.db_name,
                                json.dumps(new_database.structure), m.hexdigest()))
                print
                print textwrap.fill("- Learned {} from {}\n".format(db_name, new_database_path), width=75,
                                    initial_indent=" ", subsequent_indent="   ", replace_whitespace=False)


def learn_program(program_path, program_family, program_name, program_version):
    listing = os.listdir(program_path)
    for potential_db in listing:
        learn_db(potential_db, os.path.join(program_path, potential_db), program_family, program_name, program_version)


def compare_to_known(candidate_db, squid_reference_database):
    top_three_matches = []
    short_columns = "{:>25}  {:>5}%  {:<25} {:<18}"

    def print_short_comparison(score, known_db, candidate_db_name):
        if len(candidate_db_name) > 25:
            candidate_db_name = candidate_db_name[:23] + ".."
        if len(known_db.db_name) > 25:
            known_db.db_name = known_db.db_name[:23] + ".."
        if len(known_db.program_name) > 22:
            known_db.program_name = known_db.program_name[:20] + ".."
        print(short_columns.format(candidate_db_name, score, known_db.db_name, known_db.program_name))

    def add_rank(rankings, score, known_squid):
        if len(rankings) < 3:
            rankings.append({'score': score, 'squid': known_squid})
            rankings = sorted(rankings, key=lambda k: k['score'], reverse=True)
        else:
            if rankings[2]['score'] < score:
                rankings.pop()
                rankings.append({'score': score, 'squid': known_squid})
                rankings = sorted(rankings, key=lambda k: k['score'], reverse=True)

        return rankings

    # Connect to SQUID db
    squid_db = sqlite3.connect(squid_reference_database)
    with squid_db:
        squid_db.row_factory = dict_factory
        cursor = squid_db.cursor()
        cursor.execute("SELECT db_name, structure, rowid AS squid_id, program_family, program_name, program_version "
                       "FROM known_databases")
        for known_db in cursor:
            # Convert 'structure' from string to JSON
            known_db['structure'] = json.loads(known_db['structure'])
            # Create a squid from the database row
            known_squid = squid(**known_db)
            score = compare_dbs(candidate_db, known_squid)
            top_three_matches = add_rank(top_three_matches, float(score[2]), known_squid)

    # If the match is over 90%, just print
    if top_three_matches[0]['score'] > 90:
        print_short_comparison(top_three_matches[0]['score'], top_three_matches[0]['squid'], candidate_db.db_name)

    return top_three_matches


def compare_each(known_db, dirname, names):
    for file_name in names:
        file_path = os.path.join(dirname, file_name)
        candidate = squid(db_name=file_name, path=file_path)
        candidate.build_structure()
        if candidate.structure != {}:
            top_three = compare_to_known(candidate, known_db)
            results.append({'file_name': file_name, 'file_path': file_path, 'top_three': top_three})


def write_xlsx(output):
    def friendly_version(version_json):
        version_list = json.loads(version_json)
        if isinstance(version_list, list):
            if len(version_list) > 1:
                return str(version_list[0]) + " - " + str(version_list[-1])
            else:
                return version_list[0]
        else:
            return version_list
    workbook = xlsxwriter.Workbook(output + '.xlsx')
    w = workbook.add_worksheet('Matches')

    # Define cell formats
    title_header_format  = workbook.add_format({'font_color': 'white', 'bg_color': 'gray', 'bold': 'true'})
    center_header_format = workbook.add_format({'font_color': 'black', 'align': 'center', 'bg_color': 'gray',
                                                'bold': 'true'})
    header_format        = workbook.add_format({'font_color': 'black', 'bg_color': 'gray', 'bold': 'true'})
    black_percent_format = workbook.add_format({'font_color': 'black', 'num_format': '0.0%', 'left': 1})

    # Title bar
    w.merge_range('A1:B1', "SQUID (v%s)" % __version__, title_header_format)
    w.merge_range('C1:G1', 'Match 1', center_header_format)
    w.merge_range('H1:L1', 'Match 2', center_header_format)
    w.merge_range('M1:Q1', 'Match 3', center_header_format)

    # Write column headers
    w.write(1, 0, "Name", header_format)
    w.write(1, 1, "Path", header_format)
    w.write(1, 2, "Match%", header_format)
    w.write(1, 3, "DB Name", header_format)
    w.write(1, 4, "Program Name", header_format)
    w.write(1, 5, "Version", header_format)
    w.write(1, 6, "Category", header_format)

    w.write(1, 7, "Match%", header_format)
    w.write(1, 8, "DB Name", header_format)
    w.write(1, 9, "Program Name", header_format)
    w.write(1, 10, "Version", header_format)
    w.write(1, 11, "Category", header_format)

    w.write(1, 12, "Match%", header_format)
    w.write(1, 13, "DB Name", header_format)
    w.write(1, 14, "Program Name", header_format)
    w.write(1, 15, "Version", header_format)
    w.write(1, 16, "Category", header_format)

    #Set column widths
    w.set_column('A:A', 25)                         # Name
    w.set_column('B:B', 35)                         # Path

                                                    # Match 1
    w.set_column('C:C', 8, black_percent_format)    # Match %
    w.set_column('D:D', 20)                         # DB Name
    w.set_column('E:E', 16)                         # Program Name
    w.set_column('F:F', 10)                         # Program Version
    w.set_column('G:G', 15)                         # Program Family

                                                    # Match 2
    w.set_column('H:H', 8, black_percent_format)    # Match %
    w.set_column('I:I', 20)                         # DB Name
    w.set_column('J:J', 16)                         # Program Name
    w.set_column('K:K', 10)                         # Program Version
    w.set_column('L:L', 15)                         # Program Family

                                                    # Match 3
    w.set_column('M:M', 8, black_percent_format)    # Match %
    w.set_column('N:N', 20)                         # DB Name
    w.set_column('O:O', 16)                         # Program Name
    w.set_column('P:P', 10)                         # Program Version
    w.set_column('Q:Q', 15)                         # Program Family

    print
    print textwrap.fill("Writing match details to \"{}.xlsx\".".format(output), width=75,
                        initial_indent=" ", subsequent_indent=" ")
    row_number = 2
    for item in results:
        for counter, match in enumerate(item['top_three']):
            if item['top_three'][counter]['score'] == 0.0:
                item['top_three'][counter]['squid'].db_name = '-'
                item['top_three'][counter]['squid'].program_name = '-'
                item['top_three'][counter]['squid'].program_version = "[\"-\"]"
                item['top_three'][counter]['squid'].program_family = '-'
        w.write(row_number, 0, item['file_name'])
        w.write(row_number, 1, item['file_path'])
        w.write(row_number, 2, item['top_three'][0]['score'] / 100)
        w.write(row_number, 3, item['top_three'][0]['squid'].db_name)
        w.write(row_number, 4, item['top_three'][0]['squid'].program_name)
        w.write(row_number, 5, friendly_version(item['top_three'][0]['squid'].program_version))
        w.write(row_number, 6, item['top_three'][0]['squid'].program_family)
        w.write(row_number, 7, item['top_three'][1]['score'] / 100)
        w.write(row_number, 8, item['top_three'][1]['squid'].db_name)
        w.write(row_number, 9, item['top_three'][1]['squid'].program_name)
        w.write(row_number, 10, friendly_version(item['top_three'][1]['squid'].program_version))
        w.write(row_number, 11, item['top_three'][1]['squid'].program_family)
        w.write(row_number, 12, item['top_three'][2]['score'] / 100)
        w.write(row_number, 13, item['top_three'][2]['squid'].db_name)
        w.write(row_number, 14, item['top_three'][2]['squid'].program_name)
        w.write(row_number, 15, friendly_version(item['top_three'][2]['squid'].program_version))
        w.write(row_number, 16, item['top_three'][2]['squid'].program_family)

        row_number += 1

    # Formatting
    w.freeze_panes(2, 0)                # Freeze top row
    w.autofilter(1, 0, row_number, 16)  # Add autofilter

    workbook.close()


def parse_args():
    description = textwrap.fill("SQUID (SQLite Unknown Identifier) is a tool that compares unknown SQLite databases "
                                "to a catalog of 'known' databases to find exact and near matches.  Even if a "
                                "program updates and changes its database structure, there's a good chance SQUID will "
                                "be able to identify it.", width=75, initial_indent=" ", subsequent_indent="  ")
    usage1 = textwrap.fill("squid.py --compare c:\carved_databases", width=75, initial_indent="   ")
    usage2 = textwrap.fill("squid.py --learn \"C:\\Users\\Ryan\\AppData\\Local\\Google\\Chrome\\User Data\\Default\" "
                           "--program \"Chrome\" --version \"47\" --family \"Web Browser\"", width=75,
                           initial_indent="   ", subsequent_indent="     ", replace_whitespace=True)
    pre = description + "\n\n Example Usage:\n" + usage1 + "\n" + usage2

    class MyParser(argparse.ArgumentParser):
        def error(self, message):
            sys.stderr.write('error: %s\n' % message)
            self.print_help()
            sys.exit(2)

    parser = MyParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=pre)

    main_group = parser.add_mutually_exclusive_group(required=True)

    main_group.add_argument('-c', '--compare',
                            help='Compare to catalog of known databases. If -c points to a file, just that file will '
                                 'be compared. If -c points to a directory, the contents of that directory and all '
                                 'subdirectories will be scanned and compared.')

    main_group.add_argument('-l', '--learn',
                            help='Learn the structure of the indicated database(s) and add to catalog. If -l points to '
                                 'a file, just that single database will be added. If -l points to a directory, the '
                                 'contents of that directory will be scanned and added. Subdirectories will NOT '
                                 'be added.')
    parser.add_argument('-n', '--name',
                        help='Name of the database from --learn.  If -n is not given, the name of SQLite '
                             'file from -l will be entered in the catalog.')
    parser.add_argument('-f', '--family',
                        help='Program Family (Web Browser, Chat, etc).  Use with --learn')
    parser.add_argument('-p', '--program',
                        help='Program the database is associated with.  Use with --learn')
    parser.add_argument('-v', '--version',
                        help='Version of the program the database is associated with.  Use with --learn')
    parser.add_argument('-o', '--output',
                        help='File name of XLSX report (without extension) with match details.  If -o is not given, '
                             'the file will be named "SQUID Matches (YYYY-MM-DDTHH-MM-SS)".')

    args = vars(parser.parse_args())
    if not args['name']:
        args['name'] = args['learn']
    if not args['name'] and not args['learn']:
        args['name'] = args['compare']
    if not args['output']:
        args['output'] = "SQUID Matches ({})".format(time.strftime('%Y-%m-%dT%H-%M-%S'))
    return args


def main():
    args = parse_args()

    print
    print '-' * 78
    print " SQUID v{} - SQLite Unknown Identifier".format(__version__)
    print '-' * 78 + '\n'

    if args['compare']:
        global results
        results = []
        short_columns = "{:>25}  {:>5}%  {:<25} {:<18}"

        if os.path.isdir(str(args['compare']).rstrip(os.sep)):
            print textwrap.fill("Scanning {} and any subdirectories for SQLite DBs.\n".format(args['compare']),
                                width=75, initial_indent=" ", subsequent_indent=" ")
            print "\n"
            print textwrap.fill("Below are any high-confidence (90+%) matches; a complete list of the top three matches"
                                " for each SQLite DB is in \"{}.xlsx\".".format(args['output']), width=75,
                                initial_indent=" ", subsequent_indent=" ")
            print "\n"
            print '-' * 78
            print(short_columns.format('Candidate SQLite DB', 'Match', 'Known DB Name', 'Known Program'))
            print '-' * 78
            os.path.walk(args['compare'], compare_each, 'catalog.sqlite')
            print '-' * 78
            write_xlsx(args['output'])
        else:
            print "Comparing {} to known SQLite DBs.\n".format(args['compare'])
            print '-' * 78
            print(short_columns.format('Candidate SQLite DB', 'Match', 'DB Name', 'Program'))
            print '-' * 78
            candidate_db = squid(args['name'], path=args['compare'])
            candidate_db.build_structure()
            catalog_path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), 'catalog.sqlite')
            compare_to_known(candidate_db, catalog_path)
            print '-' * 78 + '\n'

    elif args['learn']:
        if os.path.isdir(str(args['learn']).rstrip(os.sep)):
            print textwrap.fill("Scanning {} for SQLite DBs.\n".format(args['learn']),
                                width=75, initial_indent=" ", subsequent_indent=" ")
            print
            learn_program(args['learn'], args['family'], args['program'], args['version'])
        else:
            print textwrap.fill("Learning structure of {}.\n".format(args['learn']),
                                width=75, initial_indent=" ", subsequent_indent=" ")
            print
            learn_db(args['name'], args['learn'], args['family'], args['program'], args['version'])


if __name__ == "__main__":
    main()
