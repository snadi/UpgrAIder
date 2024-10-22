import os
import csv
import shutil
from utils.github_util import get_url_data,extract_release_notes_from_html
from utils.util import load_json_file,setup_logger,get_processed_files
from dotenv import load_dotenv
from utils.DockerHandler import DockerHandler

# Load environment variables from .env file
load_dotenv()

# GitHub API token for authentication (optional)
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')


def main():
    option="filter_versioning_error"
    
   #read csv file for commit id, and number of error files
   #read list of files from folder, if number of error files is less than 5 copy files to specified folder
    csv_path = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_output/old_prompt/run_release_test_full_release/no_refrence_prompt.txt'
    src_folder = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/experiment_norelease'
    dest_folder = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/java_version_error'

    if option=="split_data":
        max_errors = 5
        process_csv_and_copy_files(csv_path, src_folder, dest_folder, max_errors)
    elif option=="fix_meta_csv_file":
        fix_meta_csv_file(csv_path)   
    elif option=="split_data_with_release":
        split_data_with_release(csv_path, src_folder, dest_folder)
    elif option=="find_no_reference_files":
        get_files_with_no_reference(src_folder, dest_folder,csv_path)
    elif option=="filter_versioning_error":
        filter_versioning_error(src_folder, dest_folder)    
  

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

def split_data_with_release(csv_path, src_folder, dest_folder):
    try:
        with open(csv_path, mode='r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                file_name = row['CommitID']
                release = row['PR_Release']
                rep=row['Reproduciable']
                if 'yes' in rep.lower() and 'yes' in release.lower():
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

def fix_meta_csv_file(csv_path):
    meta_file = csv_path  # Path to the CSV file
    temp_file = '/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/meta/bump_metadata_temp2.csv'  # Temp file to store updates

    with open(meta_file, mode='r') as csvfile, open(temp_file, mode='w', newline='') as tempcsvfile:
        # Read the original CSV file
        reader = csv.DictReader(csvfile)
        fieldnames = reader.fieldnames  # Get the field names from the original CSV

        # Create a writer to write to a temp CSV file
        writer = csv.DictWriter(tempcsvfile, fieldnames=fieldnames)
        writer.writeheader()  # Write the headers to the temp file

        for row in reader:
            file_name = row['CommitID']
            reproduciable=row['Reproduciable']
            if 'yes' in reproduciable.lower():
                dir_path='/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/benchmark_split/COMPILATION_FAILURE'
            elif 'timeout' in reproduciable.lower():
                dir_path='/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/benchmark_split/benchmark_compile_timeout'
            elif 'exclude' in reproduciable.lower():
                dir_path='/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/benchmark_split/benchmark_compilation_exclude'
            file_path=os.path.join(dir_path, file_name)
            if os.path.exists(file_path):
                data = load_json_file(file_path)
                print(f"Processing file: {file_name}")

                # Build file path and fetch PR data
                file_path = os.path.join('/Users/mam10532/Documents/GitHub/UpgrAIder/bump_data/benchmark_split/COMPILATION_FAILURE', file_name)
                pr_data, content_type = get_url_data(data.get('url'), GITHUB_TOKEN)

                if content_type == "html":
                    release_note = extract_release_notes_from_html(pr_data)
                    if release_note:
                        print("Release note found.")
                        row['PR_Release'] = 'yes'  # Update the 'PR_Release' column to 'yes' if release note found
                    else:
                        print("Release note not found.")
                        row['PR_Release'] = 'no'  # Optionally, set to 'no' if no release note found (depends on your logic)
                
                writer.writerow(row)  # Write the updated row to the temp file
                print(f"Processed file: {file_name}")
                print("---------------------------------------------------")
    # Replace the original file with the updated file
   # os.replace(temp_file, meta_file)
    print("CSV file updated successfully.")

def filter_versioning_error(src_folder, dest_folder):
    ## Load environment variables from .env file
    load_dotenv()

    # Get SSH details from environment variables
    hostname = os.getenv('SSH_HOSTNAME')
    username = os.getenv('SSH_USERNAME')
    ssh_key_path = os.getenv('SSH_KEY_PATH')
    ssh_passphrase = os.getenv('SSH_PASSPHRASE')

    # Expand the tilde to the full path
    ssh_key_path = os.path.expanduser(ssh_key_path)

        
    logs_folder = os.path.join(dest_folder, "logs")
    processed_files=get_processed_files(logs_folder)   
    files_list=os.listdir(src_folder)
    for filename in files_list:
        if filename.startswith(".") or  filename.replace('.json', '') in processed_files:
            print(f"Skipping file: {filename}")
            continue
        print("Processing file: ", filename)
        logger=setup_logger(f"{filename.replace(".json","")}.log",dest_folder)         
        docker_handler = DockerHandler(hostname, username, ssh_key_path,dest_folder,ssh_passphrase,logger) 
        json_file_path = os.path.join(src_folder, filename) 
        data = load_json_file(json_file_path)
        breaking_command = data.get('breakingUpdateReproductionCommand') 
        print("Running breaking update...")
        # Run breaking update Docker command
        breaking_success, breaking_failure_message=docker_handler.check_breaking(breaking_command)
        if not breaking_success:
            print(f"Breaking update failed: {breaking_failure_message}")
            if "class file has wrong version" in breaking_failure_message:
                print("Moving file to exclude folder...")
                dest_file_path = os.path.join(dest_folder, filename)
                shutil.move(json_file_path, dest_file_path)
                print(f"File {filename} moved to {dest_folder}")
        else:
            print("Breaking update successful.")


def get_files_with_no_reference(src_folder, dest_folder,file_path):
    with open(file_path, mode='w') as csvfile:
        for dir in os.listdir(src_folder):
            if(dir==".DS_Store"):
                continue
            prompt_dir= os.path.join(src_folder,dir, "prompt")
            for prompt in os.listdir(prompt_dir):
                    prompt_path = os.path.join(prompt_dir, prompt)
                    with open(prompt_path, 'r') as file:
                        data = file.read()
                        reference_start = data.find("Provided reference information")  
                        # Extract the part after the reference information header
                        end_ref_index = data.find("Your Response")
                        after_reference = data[reference_start:end_ref_index].lower()
                        after_reference =after_reference.replace("provided reference information:","")
                        after_reference=after_reference.strip()
                        if "no references provided" in after_reference or  after_reference == "none":
                            csvfile.write(f"{dir}\n")
                            print(f"File {prompt} has no references")
                            if not os.path.exists(dest_folder):
                                os.makedirs(dest_folder)
                            shutil.copy(prompt_path, dest_folder)    
                        else:
                            print(f"File {prompt} has references")                     
                   
if __name__ == "__main__":
    main()