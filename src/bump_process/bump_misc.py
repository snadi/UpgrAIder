import os
import csv
import shutil


def main():

   #read csv file for commit id, and number of error files
   #read list of files from folder, if number of error files is less than 5 copy files to specified folder
  
    
    csv_path = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/meta/bump_metadata.csv'
    src_folder = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/benchmark_split/COMPILATION_FAILURE'
    dest_folder = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/experiment1'
    max_errors = 5
    process_csv_and_copy_files(csv_path, src_folder, dest_folder, max_errors)
  

def process_csv_and_copy_files(csv_path, src_folder, dest_folder, max_errors):
    try:
        with open(csv_path, mode='r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                file_name = row['CommitID']
                error_count = int(row['Error_Files'])
                rep=row['Reproduciable']
                if error_count < max_errors and error_count > 0 and 'yes' in rep.lower():
                    src_file_path = os.path.join(src_folder, file_name)
                    dest_file_path = os.path.join(dest_folder, file_name)
                    if not os.path.exists(dest_folder):
                        os.makedirs(dest_folder)
                    if os.path.exists(src_file_path):
                        shutil.copy(src_file_path, dest_file_path)
                        print(f"Copied {file_name} to {dest_folder}")
                    else:
                        print(f"File {file_name} does not exist in {src_folder}")
    except Exception as e:
        print(f"An error occurred: {e}")



if __name__ == "__main__":
    main()