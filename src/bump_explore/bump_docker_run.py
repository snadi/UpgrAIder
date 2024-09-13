import paramiko
import json
import os
import re
import argparse
from dotenv import load_dotenv
import docker
import upgraider
from upgraider import upgraide
from upgraider.upgraide import Upgraider
from apiexploration.Library import CodeSnippet, Library
from upgraider.Model import Model


# Load environment variables from .env file
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
    parser.add_argument('--download_files',action='store_true', help='If set download files causing issues from the Docker image.')
    parser.add_argument('--temp_dir', required=True, type=str, help='Folder path for temp folder.')
    return parser.parse_args()

# Function to load JSON data
def load_json_file(file_path):
    with open(file_path, 'r') as json_file:
        return json.load(json_file)

# Function to run a command on the remote server via SSH
def run_docker_command(ssh, command):
    stdin, stdout, stderr = ssh.exec_command(command)
    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')
    return output, error

# Function to check the output for success or errors
def check_for_errors(output, error):
    if error:
        return False, error
    
    success_patterns = [
        "BUILD SUCCESS", 
        "TESTS PASSED", 
        "SUCCESS", 
        "FINISHED SUCCESSFULLY"
    ]
    
    failure_patterns = [
        "BUILD FAILURE",
        "ERROR",
        "FAILED",
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

# Function to retrieve files from a Docker image on a remote server via SSH
def get_files_from_docker_via_ssh(ssh, image_name, file_paths, local_temp_dir):
    """
    Extract and store the contents of the specified files from a Docker image on a remote server via SSH.

    :param ssh: An active paramiko SSH connection.
    :param image_name: The name or ID of the Docker image.
    :param file_paths: A list of file paths to retrieve from the Docker image.
    :param local_temp_dir: The local directory to store the files.
    """
    try:
        # Create a temporary container from the image and keep it running
        stdin, stdout, stderr = ssh.exec_command(f"docker create -it {image_name} /bin/sh")
        container_id = stdout.read().decode('utf-8').strip()

        if not container_id:
            print("Failed to create a Docker container.")
            return

        ssh.exec_command(f"docker start {container_id}")

        sftp = ssh.open_sftp()

        for file_path in file_paths:
            try:
                # Copy the file from the container to a temporary location on the remote server
                remote_temp_path = f"/tmp/{os.path.basename(file_path)}.tar"
                ssh.exec_command(f"docker cp {container_id}:{file_path} {remote_temp_path}")

                # Define the local path where the file will be stored
                local_file_path = os.path.join(local_temp_dir, os.path.basename(file_path))

                # Download the file from the remote server to the local machine
                sftp.get(remote_temp_path, local_file_path)

                # Extract the file content on the local machine
                os.system(f"tar -xf {local_file_path} -C {local_temp_dir}")

                # Print the file content
                with open(local_file_path.replace('.tar', ''), 'r') as file:
                    print(f"{file_path} Downloaded.\n")
                    # print(file.read())
                    # print("\n" + "="*80 + "\n")

                # Clean up the temporary files
                ssh.exec_command(f"rm -f {remote_temp_path}")
                

            except Exception as e:
                print(f"Failed to retrieve {file_path} from the Docker image: {e}")

        # Stop and remove the container
        ssh.exec_command(f"docker rm -f {container_id}")
        sftp.close()

    except Exception as e:
        print(f"An error occurred: {e}")

def fix_files_with_llm(error_files, local_temp_dir,library, model="gpt-4o-mini", db_source="modelonly", use_references=True, threshold=0.5):
    """
    Fixes the code in files causing errors using LLM and saves the updated code in separate files for comparison.
    
    :param ssh: An active paramiko SSH connection.
    :param error_files: List of file paths causing errors.
    :param local_temp_dir: Directory where the files will be temporarily stored.
    :param model: The model to be used for LLM code fixing.
    :param db_source: The database source for the model.
    """
    updated_code_map = {}
    
    # Loop through each file causing the error
    for file_path in error_files:
        try:
            local_file_path = f"{local_temp_dir}/{os.path.basename(file_path)}"
            updated_file_path = f"{local_temp_dir}/updated/{os.path.basename(file_path)}"
            
            # Read the original code from the file
            with open(local_file_path, 'r') as f:
                original_code = f.read()

            upgraider = Upgraider(model=Model(model))

            model_response = upgraider.upgraide(
                code_snippet=CodeSnippet(filename=os.path.basename(local_file_path),code=original_code),
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
                updated_code_map[file_path] = updated_code
            print(f"Updated code written to {updated_file_path}")
               
        except Exception as e:
            print(f"Error while processing {file_path}: {e}")
        
    return updated_code_map

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
        path="/libraries/jakarta.mvc"
    )

    return library

def read_updated_code_from_local_files(local_temp_dir):
    """
    Reads updated code from local files in the specified directory.

    Args:
        local_temp_dir (str): The directory where the updated files are stored.

    Returns:
        dict: A dictionary where the keys are file paths and the values are the updated code.
    """
    updated_code_map = {}
    for root, _, files in os.walk(local_temp_dir):
        for file in files:
            if(file.startswith('.')):
                continue
            file_path = os.path.join(root, file)
            with open(file_path, 'r') as f:
                updated_code_map[file] = f.read()
    return updated_code_map

def update_docker_code(updated_code_map, ssh, image_id):
    """
    Update code inside a Docker container (created from an image) and rerun the necessary commands.

    :param updated_code_map: Dictionary mapping file paths to updated code content.
    :param ssh: Paramiko SSH connection object to access the host machine.
    :param image_id: ID of the Docker image to start the container from.
    """
    try:
        # Step 1: Start a new container from the image ID
        start_container_cmd = f'docker run -d {image_id} /bin/sh -c "while true; do sleep 1000; done"'
        stdin, stdout, stderr = ssh.exec_command(start_container_cmd)
        container_id = stdout.read().decode().strip()
        error = stderr.read().decode()
        if error:
            print(f"Error starting container from image {image_id}: {error}")
            return
        
        print(f"Container started with ID: {container_id}")

        # Step 2: Iterate through the files in updated_code_map and update them in the Docker container
        for file_name, updated_code in updated_code_map.items():
            # Create a temporary file with the updated content
            temp_file = '/tmp/'+file_name
            
            # Write the updated code to the temp file on the remote host
            with ssh.open_sftp() as sftp:
                with sftp.file(temp_file, 'w') as temp_file_handle:
                    temp_file_handle.write(updated_code)

            # Copy the temp file into the Docker container
            #TODO FIX LATER
            if(file_name =="MvcEventListener.java"):
                dir="jakartaee-mvc-sample/src/main/java/com/example/"
            elif(file_name =="PostNotFoundExceptionMapper.java"):
                dir="jakartaee-mvc-sample/src/main/java/com/example/config/"
            else:
                dir="jakartaee-mvc-sample/src/main/java/com/example/web/"
            file_path=dir+file_name
            copy_cmd = f"docker cp {temp_file} {container_id}:{file_path}"
            stdin, stdout, stderr = ssh.exec_command(copy_cmd)
            error = stderr.read().decode()
            if error:
                print(f"Error copying file {file_path} to container: {error}")
            else:
                print(f"File {file_path} copied to container successfully.")
            # Remove the temp file after copying it into the container
            ssh.exec_command(f'rm {temp_file}')

        # 2. Once files are updated, restart the container or rerun the command to fix issues
        # For example, rerun the command that was failing or restart the service inside the container.
        # You can modify this to match your specific command, e.g., restarting a service
        # restart_cmd = f'docker exec {breaking_container} /path/to/your/command.sh'
        # Run breaking update Docker command
        # breaking_command = f"docker exec -ti {container_id} /bin/sh -c 'cd jakartaee-mvc-sample/ && mvn clean test'"
        breaking_command = f"docker exec {container_id} /bin/sh -c 'mvn clean test'"
       
        breaking_output, breaking_error = run_docker_command(ssh, breaking_command)
        breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)

        # Report results for breaking update
        if breaking_success:
            print(f"{file_path} - Breaking update build/test succeeded.")
        else:
            error_files = extract_error_file_paths(breaking_failure_message)
            if error_files:
                print(f"{file_path} - Breaking update build/test failed. Files causing issues:")
                print(breaking_failure_message)
                for error_file in error_files:
                    print(f" - {error_file}")
    # # Stop and remove the container
    #     ssh.exec_command(f"docker rm -f {container_id}")
    #     sftp.close()
    except Exception as e:
        print(f"An error occurred while updating the Docker container: {e}")


# Main processing function
def process_json_file(ssh, file_path, download_files, temp_dir,library):
    data = load_json_file(file_path)

    pre_command = data.get('preCommitReproductionCommand')
    breaking_command = data.get('breakingUpdateReproductionCommand')
    failure_category = data.get('failureCategory')

    # Extract Docker image name from the breaking update command
    breaking_image_name = extract_docker_image_name(data, 'breakingUpdateReproductionCommand')

    # Run pre-commit Docker command
    pre_output, pre_error = run_docker_command(ssh, pre_command)
    pre_success, pre_failure_message = check_for_errors(pre_output, pre_error)

    # Report results for pre-commit
    if pre_success:
        print(f"{file_path} - Pre-commit build/test succeeded.")
    else:
        print(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")

    # Run breaking update Docker command
    breaking_output, breaking_error = run_docker_command(ssh, breaking_command)
    breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)

    # Report results for breaking update
    if breaking_success:
        print(f"{file_path} - Breaking update build/test succeeded.")
    else:
        error_files = extract_error_file_paths(breaking_failure_message)
        if error_files:
            print(f"{file_path} - Breaking update build/test failed. Files causing issues:")
            for error_file in error_files:
                print(f" - {error_file}")

            # Define local directory for temporary file storage
            local_temp_dir = temp_dir+ "/temp"

            # Ensure the local directory exists
            os.makedirs(local_temp_dir, exist_ok=True)

            # Retrieve and print the files from the Docker image via SSH
            if breaking_image_name:
                if download_files:
                    get_files_from_docker_via_ssh(ssh, breaking_image_name, error_files, local_temp_dir)
                  # Fix the files causing errors using LLM
                #updated_code_map=fix_files_with_llm(error_files, local_temp_dir,library,db_source="doc",use_references=True, threshold=0.0)
                updated_code_map=read_updated_code_from_local_files(local_temp_dir+"/updated")
                update_docker_code(updated_code_map,ssh,breaking_image_name)
            else:
                print("Docker image for breaking update not found in the JSON file.")
        else:
            print(f"{file_path} - Breaking update build/test failed. No specific files identified.")


# Main function
def main():
    args = parse_arguments()

    # Load the private key using the passphrase
    private_key = paramiko.RSAKey.from_private_key_file(ssh_key_path, password=ssh_passphrase)

    # Establish SSH connection using the private key
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname, username=username, pkey=private_key)

    # Process a specific file if provided
    if args.specific_file:
        specific_file_path = os.path.join(args.json_folder_path, args.specific_file)
        if os.path.exists(specific_file_path):
            library = create_library_from_json(load_json_file(specific_file_path),"")
            process_json_file(ssh, specific_file_path,args.download_files,args.temp_dir,library)
        else:
            print(f"Specified file {args.specific_file} does not exist in {args.json_folder_path}.")
    else:
        # Otherwise, process all JSON files in the folder
        for filename in os.listdir(args.json_folder_path):
            if filename.endswith('.json'):
                json_file_path = os.path.join(args.json_folder_path, filename)
                data = load_json_file(json_file_path)
                if data.get('failureCategory') == args.category:
                    library = create_library_from_json(data,"")
                    process_json_file(ssh, json_file_path,args.download_files,args.temp_dir,library)
                else:
                    print(f"{filename} does not match the failure category '{args.category}' and will not be processed.")

    # Close the SSH connection
    ssh.close()

if __name__ == "__main__":
    main()
