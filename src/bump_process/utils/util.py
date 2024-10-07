
import os
import re
import json
import random
import shutil
import logging



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

# Function to load JSON data
def load_json_file(file_path):
    with open(file_path, 'r') as json_file:
        return json.load(json_file)

# Function to return a list of random files form dirctory based on failure category  
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

#Function to read log files from directory
def read_log_files_paths_from_folder(dir):
    files_list = [os.path.join(dir, f) for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f)) and f.endswith('.log')]       
            
    return files_list

# Function to setup logging
def setup_logger(logfile_name, output_dir):
   
    """Sets up logging to log messages to a file."""
    logs_output_dir = os.path.join(output_dir, "logs")
    if not os.path.exists(logs_output_dir):
     os.makedirs(logs_output_dir)
    log_file = os.path.join(logs_output_dir, logfile_name)

    # Create a new logger instance for each log file
    logger = logging.getLogger(logfile_name)  # Use logfile_name to create unique logger
    logger.setLevel(logging.INFO)  # Set the logging level

    # Check if the logger already has handlers (to avoid adding duplicate handlers)
    if not logger.hasHandlers():
        # Create a file handler for logging to a file
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)

        # # Create a stream handler for logging to the console
        # stream_handler = logging.StreamHandler()
        # stream_handler.setLevel(logging.INFO)

        # Define the formatter and set it for both handlers
        formatter = logging.Formatter('%(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        # stream_handler.setFormatter(formatter)

        # Add both handlers to the logger
        logger.addHandler(file_handler)
        # logger.addHandler(stream_handler)

    return logger

# Function to check the output for success or errors
def check_for_errors(output, error):
    
    success_patterns = [
        "BUILD SUCCESS"
    ]
    
    failure_patterns = [
        "BUILD FAILURE"
    ]
    
    for pattern in success_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return True, None
    
    for pattern in failure_patterns:
        if re.search(pattern, output, re.IGNORECASE):
            return False, output
    
    return False, "Unknown failure"

#Function to list files in a folder
def read_json_files_paths_from_folder(dir):
    files_list = [os.path.join(dir, f) for f in os.listdir(dir) if os.path.isfile(os.path.join(dir, f)) and f.endswith('.json')]       
            
    return files_list
