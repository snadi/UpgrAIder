#script to categorize BUMP dataset, for each datapoint, check if it is reprodiciable, which api and previous and new version, where pr url has release notes, 
#and number of original files causing error in breaking commit 
import argparse
import os
import json
from utils.DockerHandler import DockerHandler
import re
from dotenv import load_dotenv
from utils.util import load_json_file,extract_error_file_paths,check_for_errors
from utils.github_util import get_url_data,extract_release_notes_from_html

## Load environment variables from .env file
load_dotenv()

# Get SSH details from environment variables
hostname = os.getenv('SSH_HOSTNAME')
username = os.getenv('SSH_USERNAME')
ssh_key_path = os.getenv('SSH_KEY_PATH')
ssh_passphrase = os.getenv('SSH_PASSPHRASE')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

# Expand the tilde to the full path
ssh_key_path = os.path.expanduser(ssh_key_path)

def list_files_in_folder(folder_path):
    """Returns a list of JSON files in the given folder."""
    return [os.path.join(folder_path, f) for f in os.listdir(folder_path) if os.path.isfile(os.path.join(folder_path, f)) and f.endswith('.json')]


def process_meta(files,docker_handler,metadata_file,reproduce_message):
    for file_path in files:
        try:
            print(f"Processing file: {file_path}")
            data = load_json_file(file_path)
            metadata_file.write(os.path.basename(file_path)+","+data.get('url')+","+reproduce_message+","+data['updatedDependency']['dependencyGroupID']+","+data['updatedDependency']['previousVersion']+","+data['updatedDependency']['newVersion']+",")
            #TODO Fix issue not reteriveing any release notes
            pr_data, content_type = get_url_data(data.get('url'),GITHUB_TOKEN)
            if content_type == "html":
                release_note=extract_release_notes_from_html(pr_data)
            if release_note:
                metadata_file.write("yes-release"+",")
            else:
                metadata_file.write("no-release"+",")
            timeout=1200    
            error_files=get_error_files(data,docker_handler,file_path,timeout)
            if error_files:
                metadata_file.write(str(len(error_files)) + "\n")
            else:    
                metadata_file.write("0"+"\n")
            print(f"Processed file: {file_path}")
            print("---------------------------------------------------")
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")

def process_files(json_folder_path,exclude_dir,timeout_dir,docker_handler,metadata_file):
    """Function to process JSON files."""
     #TODO change the three folders to one, have a function that check if code reproducible or not
    rep_files=list_files_in_folder(json_folder_path)
    exclude_file=list_files_in_folder(exclude_dir)
    timeout_files=list_files_in_folder(timeout_dir)
    process_meta(rep_files,docker_handler,metadata_file,"yes-reproduce")
    process_meta(exclude_file,docker_handler,metadata_file,"no-exclude")
    process_meta(timeout_files,docker_handler,metadata_file,"no-timeout")
    

def get_error_files(data,docker_handler, file_path,timeout=200):
    breaking_command = data.get('breakingUpdateReproductionCommand')

    timeout=1200
    
    # Run breaking update Docker command
    try:
        breaking_output, breaking_error = docker_handler.run_docker_command_with_timeout(breaking_command,timeout)
        breaking_success, breaking_failure_message = check_for_errors(breaking_output)

        if breaking_success:
            return None
        else:
            return extract_error_file_paths(breaking_failure_message)
    
    except TimeoutError as e:
        print(f"{file_path} - Breaking update command timed out. Error: {e}")
        return None


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Process JSON files in a folder and exclude those that fail certain conditions.")
    
    # Add arguments
    parser.add_argument('--json_folder_path', required=True, type=str, help="The folder containing JSON files to process.")
    parser.add_argument('--exclude_dir', type=str, required=True, help="The folder containg JSON files for excluded data points")
    parser.add_argument('--timeout_dir', type=str, required=True, help="The folder containg JSON files for data points that timeout")
    parser.add_argument('--output_dir', type=str, required=True, help="Output folder")

    args = parser.parse_args()
    docker_handler = DockerHandler(hostname, username, ssh_key_path,args.output_dir,ssh_passphrase)
    # Create a file to store metadata for each file in different folders
    metadata_file_path = os.path.join(args.output_dir, 'bump_metadata.csv')
    with open(metadata_file_path, 'w') as metadata_file:
        process_files(args.json_folder_path,args.exclude_dir, args.timeout_dir, docker_handler, metadata_file)

    # Close the SSH connection
    docker_handler.close_connection()

if __name__ == '__main__':
    main()