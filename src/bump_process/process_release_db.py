import sqlite3
import os

# Function to create the SQLite database and tables
def create_db(db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Create the 'library' table
    cursor.execute('''
        CREATE TABLE library (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_name TEXT NOT NULL,
            url TEXT NOT NULL
        )
    ''')

    # Create the 'release_notes' table
    cursor.execute('''
        CREATE TABLE release_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            library_id INTEGER,
            version TEXT NOT NULL,
            details TEXT NOT NULL,
            FOREIGN KEY(library_id) REFERENCES library(id)
        )
    ''')

    # Commit and close the connection
    conn.commit()
    conn.close()
    print(f"Database '{db_name}' created successfully with tables 'library' and 'release_notes'.")


# Function to insert data into the 'library' table
def insert_library(library_name, url, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
# Check if the library already exists in the database
    cursor.execute('''
        SELECT id FROM library WHERE library_name = ? AND url = ?
    ''', (library_name, url))
    result = cursor.fetchone()
    if result:
        library_id = result[0]
    else:
        # Insert the library name and URL since it doesn't exist
        cursor.execute('''
            INSERT INTO library (library_name, url)
            VALUES (?, ?)
        ''', (library_name, url))

        # Get the last inserted library ID
        library_id = cursor.lastrowid
        conn.commit()
        print(f"Inserted library '{library_name}' with id {library_id}.")
    conn.close()
    return library_id

# Function to insert release notes into the 'release_notes' table
def insert_release_notes(library_id, version, details, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()

    # Check if the library already exists in the database
    cursor.execute('''
        SELECT id FROM release_notes WHERE library_id = ? AND version = ? AND details = ?
    ''', (library_id, version, details))
    result = cursor.fetchone()

    if not result:
        # Insert the release notes associated with a library
        cursor.execute('''
            INSERT INTO release_notes (library_id, version, details)
            VALUES (?, ?, ?)
        ''', (library_id, version, details))
        conn.commit()
        print(f"Inserted release notes for library id {library_id}, version '{version}'.")
    else:
        print(f"Details {details} found in the db for library id {library_id}, version '{version}'.")    

    conn.close()

def check_db_for_data(library_name, version, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    # Check if the library already exists in the database
    cursor.execute('''
        SELECT id FROM library WHERE library_name = ? 
    ''', (library_name,))

    result = cursor.fetchone()
    if result:
        library_id = result[0]
        # Check if the release notes already exist in the database
        cursor.execute('''
            SELECT * FROM release_notes WHERE library_id = ? AND version = ? 
        ''', (library_id, version))
        result = cursor.fetchone()
        conn.close()
        if result:
            print(f"Details found in the db for library name {library_name}, version '{version}'.")
            return True
        else:
            return False
       
    else:
        return False    
    

def check_db_for_library(library_name, db_name):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    # Check if the library already exists in the database
    cursor.execute('''
        SELECT id FROM library WHERE library_name = ? 
    ''', (library_name,))

    result = cursor.fetchone()
    if result:
        return True
    else:
        return False

def get_library_release_notes(db_name,library_name,currentversion,old_version):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    #get all versions between old and current version
    cursor.execute('''
        SELECT version,details FROM release_notes WHERE library_id = (SELECT id FROM library WHERE library_name = ?) AND version > ? AND version <= ?
    ''', (library_name,old_version,currentversion))
    result = cursor.fetchall()
    
    release_notes = []
    if result:
        for row in result:
            release_note = {
                'version': row[0],  # version
                'details': row[1]   # details
            }
            release_notes.append(release_note)  # Add each release note as a dictionary to the list
            
        conn.close()
        return release_notes 
    conn.close()
    return None    
