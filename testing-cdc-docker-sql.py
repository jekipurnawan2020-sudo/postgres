import pyodbc

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"
    "SERVER=10.52.132.138,1433;"
    "DATABASE=MyDatabase;"
    "UID=cdc_user;"
    "PWD=PASSWORD;"
    "Encrypt=no;"
    "TrustServerCertificate=yes;"
)

cursor = conn.cursor()

cursor.execute("SELECT @@VERSION")

print(cursor.fetchone()[0])