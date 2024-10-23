
import os
import re
import json
import random
import shutil
import logging



#Function to format release notes into a formated string
def format_release_notes(data):
    # Create a dictionary to group details by version
    grouped_versions = {}
    for entry in data:
        version = entry['version']
        details = entry['details']
        if version not in grouped_versions:
            grouped_versions[version] = []
        grouped_versions[version].append(details)

    # Build the desired string output
    result_str = ""
    for version, details_list in grouped_versions.items():
        result_str += f"Version {version}:\n"
        for detail in details_list:
            result_str += f"- {detail}\n"
        result_str += "\n"  # Add a new line between versions for better formatting

    return result_str

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


def extract_errors(error_log):
    # """
    # Extracts and returns a list of dictionaries where the key is the file path
    # and the value is a list of the errors caused in that file.

    # :param error_log: A string containing the error log.
    # :return: A dictionaries {file_path: [error_messages]}.
    # """
    # # Regular expression to extract the file paths and line numbers
    # file_path_pattern = r"\[ERROR\] (/.*\.java):\[\d+,\d+\] (.*)"
    
    
    """
    Extracts and returns a list of dictionaries where the key is the file path
    and the value is a list of the errors caused in that file. Handles multi-line
    errors and errors without a specific 'error:' prefix.

    :param error_log: A string containing the error log.
    :return: A list of dictionaries {file_path: [error_messages]}.
    """
    # Regular expression to match the error message with file paths
    file_path_pattern = r"\[ERROR\] (/.*\.java):\[(\d+),(\d+)\] (.*)"
    
    # Split the error log into lines
    log_lines = error_log.splitlines()
    error_log_lines=get_error_lines(log_lines)


    error_dict = {}
    current_file_path = None
    current_error_message = []
    

    for line in error_log_lines:
        if "-> [Help 1]" in line or "To see the full stack trace of the errors" in line:
            break
        if "Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin" in line:
            #trim line starting from "Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin"
            index = line.find("Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin")
            line = line[:index]
        # Check if the line matches the file path pattern
        match = re.match(file_path_pattern, line)
        
        if match:
            # If we have an ongoing error message, save it before starting a new one
            if current_file_path and current_error_message:
                message = ' '.join(current_error_message)
                #check if error message is already in the list
                if message not in error_dict[current_file_path]:
                    error_dict[current_file_path].append(message.strip())
                current_error_message = []  # Reset for the next error
            
            # Extract file path and error message from the match
            current_file_path, line_number, column_number,initial_error_message = match.groups()
            
            # Ensure the file path is in the dictionary
            if current_file_path not in error_dict:
                error_dict[current_file_path] = []
            
            # Start collecting the error message
            current_error_message.append(f"[{line_number},{column_number}]: {initial_error_message}")
        
        elif line.startswith("[ERROR]") and current_error_message:
                # This is a continuation of the error message
                if line.replace("[ERROR]", "").strip() not in current_error_message:
                    if line.replace("[ERROR]", "").strip() != "":
                        current_error_message.append(line.replace("[ERROR]", "").strip())
        
        else:
            # Non-error lines are part of the error details
            if current_error_message and not line.strip() in current_error_message:
                    current_error_message.append(line.strip())

    # Add the last error message to the dictionary if it exists
    if current_file_path and current_error_message:
                message = ' '.join(current_error_message).strip()
                #check if error message is already in the list
                if message not in error_dict[current_file_path]:
                    error_dict[current_file_path].append(message.strip())

    return error_dict


def get_error_lines(log_lines):
    error_lines = []
    error_start=False
    for line in log_lines:
        if line.startswith("[ERROR]") and not error_start:
            error_start=True
        if error_start:
            if not line.startswith("[INFO]") and not line.startswith("[WARNING]"):
                error_lines.append(line)
    return error_lines

def convert_errors_to_string(error_dict):
    """
    Converts a list of error messages associated with a file path into a single string.

    :param error_dict: A dictionary where the key is the file path and the value is a list of error messages.
    :return: A string combining all the errors in the dictionary.
    """
    error_strings = []
    
    # Iterate through the dictionary
    for file_path, errors in error_dict.items():
        # Join all error messages for the current file path into a single string
        error_string = " ".join(errors)
        error_strings.append(error_string)
    
    # Join all file error strings into a single string with two newlines separating each file's errors
    return "\n\n".join(error_strings)

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
    logger.propagate = False
    logging.getLogger().handlers.clear()

    # # Check if the logger already has handlers (to avoid adding duplicate handlers)
    # if not logger.hasHandlers():
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


def get_fixed_files(pre_fix_errors_files,post_fix_errors_files):
    fixed_files = []
    for file in pre_fix_errors_files:
        if file not in post_fix_errors_files:
            fixed_files.append(file)
    return fixed_files

def get_unfixed_files(pre_fix_errors_files,post_fix_errors_files):
    unfixed_files = []
    for file in pre_fix_errors_files:
        if file in post_fix_errors_files:
            unfixed_files.append(file)
    return unfixed_files

def get_new_error_files(pre_fix_errors_files,post_fix_errors_files):
    new_errors = []
    for file in post_fix_errors_files:
        if file not in pre_fix_errors_files:
            new_errors.append(file)
    return new_errors

def write_output_to_file(dir_path,dir,filename,data,mode='w'):
    data_output_dir = os.path.join(dir_path, dir)
    if not os.path.exists(data_output_dir):
        os.makedirs(data_output_dir)
    file_path = os.path.join(data_output_dir, f"{filename}_{dir}.txt")
    with open(file_path,mode) as f:
       f.write(data)
       f.write("\n-------------------------\n")
    

def write_errors_to_file(dir_path,dir,filename,message,error_list,mode="w"):
    data_output_dir = os.path.join(dir_path, dir)
    if not os.path.exists(data_output_dir):
        os.makedirs(data_output_dir)
    file_path = os.path.join(data_output_dir, f"{filename}_{dir}.txt")
    with open(file_path,mode) as f:
        f.write(f"{message}\n\n")
        for error in error_list:
            f.write(f"{error}\n\n")
        f.write("\n-------------------------\n")



def get_processed_files(logs_output_dir):
    """Get the list of unprocessed files from the output directory."""
    processed_files = set()
    # Check if the logs directory exists
    if os.path.exists(logs_output_dir):
        for log_file in os.listdir(logs_output_dir):
            if log_file.endswith('.log'):
                processed_files.add(log_file.replace('.log', ''))

    return processed_files


def get_error_count(error_dict):
    """Get the total number of errors from the error dictionary."""
    error_count = 0
    for file_path, errors in error_dict.items():
        error_count += len(errors)
    return error_count


def get_fixed_errors(pre_fix_errors, post_fix_errors):
    """Get the errors that were fixed after running the upgrade process."""
    fixed_errors = []
    for file_path, pre_fix_errors_list in pre_fix_errors.items():
        post_fix_errors_list = post_fix_errors.get(file_path, [])
        for error in pre_fix_errors_list:
            if error not in post_fix_errors_list:
                fixed_errors.append(error)
       # fixed_errors[file_path] = [error for error in pre_fix_errors_list if error not in post_fix_errors_list]
    return fixed_errors

def get_unfixed_errors(pre_fix_errors, post_fix_errors):
    """Get the errors that were not fixed after running the upgrade process."""
    unfixed_errors = []
    for file_path, pre_fix_errors_list in pre_fix_errors.items():
        post_fix_errors_list = post_fix_errors.get(file_path, [])
        for error in pre_fix_errors_list:
            if error in post_fix_errors_list:
                unfixed_errors.append(error)
        #unfixed_errors[file_path] = [error for error in pre_fix_errors_list if error in post_fix_errors_list]
    return unfixed_errors

def get_new_errors(pre_fix_errors, post_fix_errors,pre_fix_files):
    """Get the errors that were newly introduced after running the upgrade process."""
    new_errors = []
    for file_path, post_fix_errors_list in post_fix_errors.items():
        if file_path not in pre_fix_files:
            new_file_errors = post_fix_errors.get(file_path, [])
            for error in new_file_errors:
                new_errors.append(error)
        pre_fix_errors_list = pre_fix_errors.get(file_path, [])
        for error in post_fix_errors_list:
            if error not in pre_fix_errors_list:
                new_errors.append(error)
        #new_errors[file_path] = [error for error in post_fix_errors_list if error not in pre_fix_errors_list]
    return new_errors