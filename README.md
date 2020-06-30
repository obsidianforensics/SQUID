SQUID (SQLite Unknown Identifier)
=========

"Fuzzy matching" for SQLite databases (presentation from [OSDFCon about SQUID](https://www.osdfcon.org/presentations/2015/Ryan-Benson_OSDF-Squid.pdf))

SQUID (SQLite Unknown Identifier) is a tool that compares unknown SQLite databases to a catalog of 'known' databases to find exact and near matches.  Even if a program updates and its database structure changes, there's a good chance SQUID will be able to identify it as related to that application.

SQUID is made up of a Python script (squid.py) and a SQLite file of known databases (catalog.sqlite).  

#### Examples:

Scan a folder of carved SQLite databases to determine what application they are associated with:
> C:\\squid.py --compare "C:\carving\recovered_SQLite_DBs"

Scan a user's AppData folder to locate interesting databases and name the report:
> C:\\squid.py --compare "C:\Users\Ryan\AppData" --output "Ryan_AppData"

Scan iOS backups and save the report to a different drive:
> C:\\squid.py --compare "C:\Users\Ryan\AppData\Roaming\Apple Computer\MobileSync\Backup" --output "X:\Reports\Ryan_iOS_Backups"

Teach SQUID about a new version of Chrome:
> C:\\squid.py --learn "C:\Users\Ryan\AppData\Local\Google\Chrome\User Data\Default" --program "Google Chrome" --version "47" --family "Web Browser"


#### Command Line Options:

| Option          | Description                                             |
| --------------- | ------------------------------------------------------- |
| -c or --compare | Compare to catalog of known databases. If -c points to a file, just that file will be compared. If -c points to a directory, the contents of that directory and all subdirectories will be scanned and compared. |
| -o or --output  | File name of XLSX report (without extension) with match details.  If -o is not given, the file will be named "SQUID Matches (YYYY-MM-DDTHH-MM-SS)" |
| -l or --learn   | Learn the structure of the indicated database(s) and add to catalog. If -l points to a file, just that single database will be added. If -l points to a directory, the contents of that directory will be scanned and added. Subdirectories will NOT be added. |
| -n or --name    | Name of the database from --learn.  If -n is not given, the name of SQLite file from -l will be entered in the catalog.|
| -f or --family  | Program Family (Web Browser, Chat, etc).  Use with --learn |
| -p or --program | Program the database is associated with.  Use with --learn |
| -v or --version | Version of the program the database is associated with.  Use with --learn |

#### Requirements:

XlsxWriter (pip install xlsxwriter)
