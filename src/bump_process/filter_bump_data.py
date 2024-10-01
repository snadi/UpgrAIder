import os
import shutil
import argparse
import logging
from utils.DockerHandler import DockerHandler
import json
import re
from dotenv import load_dotenv
from utils import load_json_file, setup_logger,check_for_errors

## Load environment variables from .env file
load_dotenv()

# Get SSH details from environment variables
hostname = os.getenv('SSH_HOSTNAME')
username = os.getenv('SSH_USERNAME')
ssh_key_path = os.getenv('SSH_KEY_PATH')
ssh_passphrase = os.getenv('SSH_PASSPHRASE')

# Expand the tilde to the full path
ssh_key_path = os.path.expanduser(ssh_key_path)

def process_json_file(logger, docker_handler, file_path,timeout=200):
    """Processes a single JSON file and returns True if it's valid."""
    data = load_json_file(file_path)

    pre_command = data.get('preCommitReproductionCommand')
    breaking_command = data.get('breakingUpdateReproductionCommand')

    timeout=1200
    # Run pre-commit Docker command
    try: 
        pre_output, pre_error = docker_handler.run_docker_command_with_timeout(pre_command,timeout)
        pre_success, pre_failure_message = check_for_errors(pre_output, pre_error)

        if not pre_success:
            logger.error(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")
            return False

        logger.info(f"{file_path} - Pre-commit build/test succeeded.")

    except TimeoutError as e:
        logger.error(f"{file_path} - Pre-commit command timed out. Error: {e}")
        return False
    
    # Run breaking update Docker command
    try:
        breaking_output, breaking_error = docker_handler.run_docker_command_with_timeout(breaking_command,timeout)
        breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)

        if breaking_success:
            logger.info(f"{file_path} - Breaking update build/test succeeded.")
            return False

        logger.info(f"{file_path} - Breaking update build/test failed as expected.")
        return True
    
    except TimeoutError as e:
        logger.error(f"{file_path} - Breaking update command timed out. Error: {e}")
        return False
    
def _read_processed_files(output_dir):
    """Get the list of processed files from the output directory."""
    processed_files = set()
    logs_output_dir = os.path.join(output_dir, "logs")

    # Check if the logs directory exists
    if os.path.exists(logs_output_dir):
        for log_file in os.listdir(logs_output_dir):
            if log_file.endswith('.log'):
                processed_files.add(log_file.replace('.log', ''))

    return processed_files

def process_files(json_folder_path, excluded_folder, docker_handler, output_dir, category):
    """Process JSON files in the given folder and move excluded files to another folder."""
    # List of JSON files in the specified directory
    files_list = [f for f in os.listdir(json_folder_path) if os.path.isfile(os.path.join(json_folder_path, f)) and f.endswith('.json')]

    processed_files = _read_processed_files(output_dir)

    # Create the folder for excluded files
    os.makedirs(excluded_folder, exist_ok=True)
    
    timeout=600

    # Process each file
    for filename in files_list:   
        if filename.endswith('.json'):
             # Skip files that have already been processed
            if filename.replace('.json', '') in processed_files:
                print(f"{filename} has already been processed and will be skipped.")
                continue
            json_file_path = os.path.join(json_folder_path, filename)
            data = load_json_file(json_file_path)

            # Check if the file matches the category
            if data.get('failureCategory') == category:
                logger = setup_logger(f"{filename.replace('.json', '')}.log", output_dir)
                docker_handler.set_logger(logger)

                # Process the JSON file
                result = process_json_file(logger, docker_handler, json_file_path,timeout)

                # If pre-commit failed or breaking-commit succeeded, move file to excluded folder
                if not result:
                    logger.info(f"Excluding {filename} due to failure.")
                    shutil.move(json_file_path, os.path.join(excluded_folder, filename))
                else:
                    logger.info(f"Processed {filename} successfully.")
            else:
                print(f"{filename} does not match the failure category '{category}' and will not be processed.")
        print(f"Processed {filename}.")

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Process JSON files in a folder and exclude those that fail certain conditions.")
    
    # Add arguments
    parser.add_argument('--json_folder_path', required=True, type=str, help="The folder containing JSON files to process.")
    parser.add_argument('--excluded_folder', required=True, type=str, help="The folder to move excluded JSON files to.")
    parser.add_argument('--output_dir', type=str, required=True, help="The folder to store logs and processed files.")
    parser.add_argument('--category', type=str, help="The category for filtering JSON files.")

    args = parser.parse_args()
    timeout=1000
    # Create the DockerHandler 
    docker_handler = DockerHandler(hostname, username, ssh_key_path,args.output_dir,ssh_passphrase)

    # Process files in the provided folder
    process_files(args.json_folder_path, args.excluded_folder, docker_handler, args.output_dir, args.category)

    # Close the SSH connection
    docker_handler.close_connection()

if __name__ == '__main__':
    main()




