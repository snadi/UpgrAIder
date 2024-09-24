import json
import os
import re
import argparse
from dotenv import load_dotenv
from DockerHandler import DockerHandler
import upgraider
from upgraider import upgraide
from upgraider.upgraide import Upgraider
from apiexploration.Library import CodeSnippet, Library
from upgraider.Model import Model
import logging
import random
from pathlib import Path

## Load environment variables from .env file
load_dotenv()

# Get SSH details from environment variables
hostname = os.getenv('SSH_HOSTNAME')
username = os.getenv('SSH_USERNAME')
ssh_key_path = os.getenv('SSH_KEY_PATH')
ssh_passphrase = os.getenv('SSH_PASSPHRASE')

# Expand the tilde to the full path
ssh_key_path = os.path.expanduser(ssh_key_path)

# Function to parse command-line arguments
def parse_arguments():
    parser = argparse.ArgumentParser(description='Process JSON files to run Docker commands via SSH.')
    parser.add_argument('--json_folder_path', required=True, type=str, help='Folder path containing the JSON files.')
    parser.add_argument('--specific_file', type=str, help='Optional: Specify a single JSON file to process.')
    parser.add_argument('--category', type=str, required=True, help='Failure category to process (e.g., COMPILATION_FAILURE).')
    parser.add_argument('--no_download_files',action='store_true', help='If set do not download files causing issues from the Docker image.')
    parser.add_argument('--output_dir', required=True, type=str, help='Folder path for output folder.')
    parser.add_argument('--limit_files', type=int, help='If set then process specificed number of files, selected randomly.')
    parser.add_argument('--use_references', action='store_true', help='If set use references in the LLM model.')
    parser.add_argument('--threshold', type=float, default=0.5, help='Threshold for LLM model.')
    parser.add_argument('--model', type=str, default="gpt-4o-mini", help='Model to use for LLM.')
    parser.add_argument('--db_source', type=str, default="modelonly", help='Data source for LLM.')
   
    return parser.parse_args()

# Function to load JSON data
def load_json_file(file_path):
    with open(file_path, 'r') as json_file:
        return json.load(json_file)

def select_random_files(directory_path, category, number_of_files=20):
     # Check if the directory exists
    if not os.path.isdir(directory_path):
        raise FileNotFoundError(f"The directory {directory_path} does not exist.")
    
    # List all .json files in the directory
    all_files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f)) and f.endswith('.json')]

    # Filter files by category
    category_files = []
    for file_name in all_files:
        file_path = os.path.join(directory_path, file_name)
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                # Check if the category exists in the JSON data (assuming 'category' is a key)
                if data.get('failureCategory') == category:
                    category_files.append(file_name)
        except (json.JSONDecodeError, KeyError):
            print(f"Error processing file {file_name}, skipping.")

    # If the number of matching files is less than the number requested, return all matching files
    if len(category_files) < number_of_files:
        print(f"Only {len(category_files)} files match the category '{category}', returning all matching files.")
        return category_files

    # Select random files from the category list
    selected_files = random.sample(category_files, number_of_files)
    
    return selected_files

def _setup_logger(logfile_name, output_dir):
   
    """Sets up logging to log messages to a file."""
    logs_output_dir = os.path.join(output_dir, "logs")
    os.makedirs(logs_output_dir, exist_ok=True)
    log_file = os.path.join(logs_output_dir, logfile_name)

    # Create a new logger instance for each log file
    logger = logging.getLogger(logfile_name)  # Use logfile_name to create unique logger
    logger.setLevel(logging.INFO)  # Set the logging level

    # Check if the logger already has handlers (to avoid adding duplicate handlers)
    if not logger.hasHandlers():
        # Create a file handler for logging to a file
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # Create a stream handler for logging to the console
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(logging.INFO)

        # Define the formatter and set it for both handlers
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        # Add both handlers to the logger
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    return logger

# Function to check the output for success or errors
def check_for_errors(output, error):
    
    success_patterns = [
        "BUILD SUCCESS"
    ]
    
    failure_patterns = [
        "BUILD FAILURE",
        "COMPILATION FAILURE"
    ]
    
    for pattern in success_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return True, None
    
    for pattern in failure_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return False, output
    
    return False, "Unknown failure"

#Function to extract the file paths causing issues from the error log
def extract_error_file_paths(error_log):
    """
    Extracts and returns a list of file paths that caused issues in the error log.

    :param error_log: A string containing the error log.
    :return: A list of unique file paths causing issues.
    """
    # Regular expression to extract the file paths
    file_path_pattern = r"\[ERROR\] (/.*\.java):\[\d+,\d+\]"

    # Find all matching file paths
    file_paths = re.findall(file_path_pattern, error_log)

    # Remove duplicates
    file_paths = list(set(file_paths))

    return file_paths
# Function to extract the Docker image name from the JSON data
def extract_docker_image_name(data, command_key):
    # Extract the Docker run command from the JSON
    docker_command = data.get(command_key)
    
    if docker_command:
        # Use a regular expression to extract the Docker image name
        match = re.search(r'docker run (\S+)', docker_command)
        if match:
            return match.group(1)   
    return None
    
def create_library_from_json(libinfo, libpath):
    """
    Create a Library object from the JSON dictionary.

    :param libinfo: Dictionary containing library information.
    :param libpath: The path to the library (libpath can be passed as a separate argument).
    :return: Library object.
    """
    # Extract necessary information from the JSON data
    library = Library(
        name=libinfo["updatedDependency"]["dependencyGroupID"],
        ghurl=libinfo["url"],
        baseversion=libinfo["updatedDependency"]["previousVersion"],
        currentversion=libinfo["updatedDependency"]["newVersion"],
        path=libpath
    )

    return library

def _delete_temp_folder(output_dir):
    path = Path(os.join(output_dir,"temp"))
    try:
        path.rmdir()
        print("Directory removed successfully")
    except OSError as o:
        print(f"Error, {o.strerror}: {path}")

def fix_files_with_llm(error_files, local_temp_dir,library, model="gpt-4o-mini", db_source="modelonly", use_references=True, threshold=0.5):
    """
    Fixes the code in files causing errors using LLM and saves the updated code in separate files for comparison.
    """
    updated_code_map = {}
    
    # Loop through each file causing the error
    for file_path in error_files:
        try:
            local_file_path = f"{local_temp_dir}/{os.path.basename(file_path)}"
            updated_file_path = f"{local_temp_dir}/updated/{os.path.basename(file_path)}"
            
            with open(local_file_path, 'r') as f:
                    content =f.readlines()
                    remote_file_path = content[0].strip()
                    original_code= ''.join(content[1:])

            upgraider = Upgraider(model=Model(model))

            model_response = upgraider.upgraide(
                code_snippet=CodeSnippet(filename=os.path.basename(remote_file_path),code=original_code),
                use_references=use_references,
                threshold=threshold,
                library = library,
                output_dir=local_temp_dir
            )
        
            # Write the updated code to a separate file (for comparison)
            with open(updated_file_path, 'w') as f:
                # f.write("Prompt: "+model_response.prompt+'\n')
                updated_code = model_response.updated_code.code
                if updated_code.startswith("java"):
                    # Remove the Java string from the start of the updated code
                    updated_code = updated_code[len("java"):]
                f.write(updated_code+'\n')
                updated_code_map[remote_file_path] = updated_code
            print(f"Updated code written to {updated_file_path}")
               
        except Exception as e:
            print(f"Error while processing {file_path}: {e}")
        
    return updated_code_map

# def _read_files_paths_from_folder(local_temp_dir):
#     error_files = []
#     for root, _, files in os.walk(local_temp_dir):
#         for file in files:
#             if(file.startswith('.')):
#                 continue
#             if os.path.isdir(file):
#                 continue
#             error_files.append(os.path.join(root, file))
#     return error_files


#Main function to process the JSON files
def process_json_file(logger,docker_handler, file_path, no_download_files, output_dir,library,model,db_source,use_references,threshold):
    data = load_json_file(file_path)

    pre_command = data.get('preCommitReproductionCommand')
    breaking_command = data.get('breakingUpdateReproductionCommand')
    
    # Extract Docker image name from the breaking update command
    breaking_image_name = extract_docker_image_name(data, 'breakingUpdateReproductionCommand')

    # Run pre-commit Docker command
    pre_output, pre_error = docker_handler.run_docker_command(pre_command)
    pre_success, pre_failure_message = check_for_errors(pre_output, pre_error)

    # Report results for pre-commit
    if pre_success:
        print(f"{file_path} - Pre-commit build/test succeeded.")
        logger.info(f"{file_path} - Pre-commit build/test succeeded.")
    else:
        print(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")
        logger.error(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")   
        return -1,-1

    # Run breaking update Docker command
    breaking_output, breaking_error = docker_handler.run_docker_command(breaking_command)
    breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)

    # Report results for breaking update
    if breaking_success:
        print(f"{file_path} - Breaking update build/test succeeded.")
        logger.info(f"{file_path} - Breaking update build/test succeeded.") 
        return -1,-1
    else:
        error_files = extract_error_file_paths(breaking_failure_message)
        pre_fix_error_files = len(error_files)
        if error_files:
            print(f"{file_path} - Breaking update build/test failed. Files causing issues:")
            logger.error(f"{file_path} - Breaking update build/test failed. Error: {breaking_failure_message}")
            logger.error("Files causing issues:")
            for error_file in error_files:
                print(f" - {error_file}")
                logger.error(f" - {error_file}")

            # Define local directory for temporary file storage
            local_temp_dir = os.path.join(output_dir, "temp")
            os.makedirs(local_temp_dir,exist_ok=True)
            breaking_data_point = os.path.basename(breaking_image_name).replace("breaking-updates:","")
            local_temp_dir = os.path.join(local_temp_dir, breaking_data_point)
            os.makedirs(local_temp_dir,exist_ok=True)
           

            # Retrieve and print the files from the Docker image via SSH
            if breaking_image_name:
                if not no_download_files:
                    docker_handler.get_files_from_docker_via_ssh(breaking_image_name, error_files, local_temp_dir)
                    print(f"Files causing issues downloaded to {local_temp_dir}.")
                    
                # Fix the files causing errors using LLM
                updated_code_map=fix_files_with_llm(error_files, local_temp_dir,library,model,db_source,use_references,threshold)
                

                # Update the code in the Docker container and rerun the necessary commands check if breaking issue is fixed
                breaking_output, breaking_error=docker_handler.update_docker_code(updated_code_map,breaking_image_name)
                breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)

                # Report results for breaking update
                if breaking_success:
                    print(f"{error_file} - Breaking update build/test succeeded after fixes.")
                    logger.info(f"{error_file} - Breaking update build/test succeeded after fixes.")
                elif breaking_failure_message:
                    error_files = extract_error_file_paths(breaking_failure_message)
                    post_fix_error_files = len(error_files)
                    if error_files:
                        print(f"{file_path} - Breaking update build/test failed after fixes. Files causing issues:")
                        logger.error(f"{file_path} - Breaking update build/test failed after fixes. Files causing issues:") 
                        print(breaking_failure_message)
                        # logger.error(breaking_failure_message)
                        for error_file in error_files:
                            print(f" - {error_file}")
                            logger.error(f" - {error_file}")
                else:
                    print(f"Failed to reprocess {breaking_image_name}.")
                    logger.error(f"Failed to reprocess {breaking_image_name}.")
            else:
                print(f"{error_file} - Breaking update build/test failed. No specific files identified.")
                logger.error(f"Failed to reprocess {breaking_image_name}.")
    return  pre_fix_error_files, post_fix_error_files


# Main function
def main():
    args = parse_arguments()
    with open(os.path.join(args.output_dir, "run_data.txt"), 'w') as f:
        # Process a specific file if provided
        try:      
            if args.specific_file:
                specific_file_path = os.path.join(args.json_folder_path, args.specific_file)
                logger=_setup_logger(f"{args.specific_file.replace(".json","")}.log",args.output_dir)
                docker_handler = DockerHandler(hostname, username, ssh_key_path,args.output_dir,ssh_passphrase,logger)
                if os.path.exists(specific_file_path):
                    library = create_library_from_json(load_json_file(specific_file_path),"")
                    pre_fix_num,post_fix_num=process_json_file(logger,docker_handler, specific_file_path,args.no_download_files,args.output_dir,library,
                                                               args.model,args.db_source,args.use_references,args.threshold)
                    f.write(f"{args.specific_file},{pre_fix_num},{post_fix_num}\n")
                else:
                    print(f"Specified file {args.specific_file} does not exist in {args.json_folder_path}.")
            else:
                if args.limit_files:
                    #change to consider failure type if passed in args
                    files_list=select_random_files(args.json_folder_path,args.category,args.limit_files)
                else:
                    files_list = [f for f in os.listdir(args.json_folder_path) if os.path.isfile(os.path.join(args.json_folder_path, f)) and f.endswith('.json')]       
            
                docker_handler = DockerHandler(hostname, username, ssh_key_path,args.output_dir,ssh_passphrase)
                for filename in files_list:
                    if filename.endswith('.json'):
                        json_file_path = os.path.join(args.json_folder_path, filename)
                        data = load_json_file(json_file_path)
                        if data.get('failureCategory') == args.category:
                            logger=_setup_logger(f"{filename.replace(".json","")}.log",args.output_dir)
                            docker_handler.set_logger(logger)
                            library = create_library_from_json(data,"")
                            pre_fix_num,post_fix_num=process_json_file(logger,docker_handler, json_file_path,args.no_download_files,args.output_dir,library,
                                                                       args.model,args.db_source,args.use_references,args.threshold)
                            f.write(f"{filename},{pre_fix_num},{post_fix_num}\n")
                        else:
                            print(f"{filename} does not match the failure category '{args.category}' and will not be processed.")
                        print(f"Processed {filename}.")    
    
            # Close the SSH connection
            docker_handler.close_connection()
        except Exception as e:
            print(f"An error occurred: {e}")   

if __name__ == "__main__":
    main()