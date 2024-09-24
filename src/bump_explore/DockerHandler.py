import threading
import paramiko
import os
import re
import logging

# DockerHandler class for managing Docker tasks over SSH
class TimeoutError(Exception):
    pass
class DockerHandler:
    def __init__(self, hostname, username, ssh_key_path, output_dir, ssh_passphrase=None, logger=None):
        if not all([hostname, username, ssh_key_path]):
            raise ValueError("SSH_HOSTNAME, SSH_USERNAME, and SSH_KEY_PATH must be set in the environment.")
        
        self.hostname = hostname
        self.username = username
        self.ssh_key_path = ssh_key_path
        self.ssh_passphrase = ssh_passphrase
        if logger:
            self.logger = logger
        try:
            self.ssh_client = self._create_ssh_client()
        except Exception as e:
            print(f"An error occurred while creating SSH client: {e}")
            raise



    def run_docker_command_with_timeout(self,command,timeout):
        """Run a Docker command with a timeout."""
        result = {"output": None, "error": None, "completed": False}

        def target():
            # Simulate running the command using paramiko or subprocess
            output, error = self.run_docker_command(command)  # Placeholder for actual command execution
            result["output"] = output
            result["error"] = error
            result["completed"] = True

        # Start the thread to run the command
        thread = threading.Thread(target=target)
        thread.start()

        # Wait for the command to complete or timeout
        thread.join(timeout)

        # If the command takes too long, raise a TimeoutError
        if not result["completed"]:
            raise TimeoutError(f"Command '{command}' timed out after {timeout} seconds")

        return result["output"], result["error"]

    
    def set_logger(self, logger):
        self.logger = logger
        
        
    def _create_ssh_client(self):
        """Creates and returns an SSH client."""
        print("Establishing SSH connection...")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(self.hostname, username=self.username, key_filename=self.ssh_key_path, passphrase=self.ssh_passphrase)
            print("SSH connection established.")
            return ssh
        except paramiko.AuthenticationException as auth_error:
            print(f"Authentication failed, please verify your credentials: {auth_error}")
            raise  # Re-raise the exception or handle it
        except paramiko.SSHException as ssh_error:
            print(f"Unable to establish SSH connection: {ssh_error}")
            raise  # Re-raise the exception or handle it
        except Exception as e:
            print(f"An error occurred: {e}")
            raise  # Catch any other exceptions and re-raise or handle them


    def run_docker_command(self, command):
        """Runs a Docker command on the remote server and returns output and error."""
        print(f"Running command: {command}")
        self.logger.info(f"Running command: {command}")
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        # if output:
        #     self.logger.info(f"Command {command} output: {output}")
        # if error:
        #     self.logger.error(f"Command {command} error: {error}")

        return output, error
    
    # Function to retrieve files from a Docker image on a remote server via SSH
    def get_files_from_docker_via_ssh(self, image_name, file_paths, local_temp_dir):
        """
        Extract and store the contents of the specified files from a Docker image on a remote server via SSH.

        :param ssh: An active paramiko SSH connection.
        :param image_name: The name or ID of the Docker image.
        :param file_paths: A list of file paths to retrieve from the Docker image.
        :param local_temp_dir: The local directory to store the files.
        """
        try:
            # Create a temporary container from the image and keep it running
            stdin, stdout, stderr = self.ssh_client.exec_command(f"docker create -it {image_name} /bin/sh")
            container_id = stdout.read().decode('utf-8').strip()

            if not container_id:
                self.logger.error("Failed to create a Docker container.")
                print("Failed to create a Docker container.")
                return

            self.ssh_client.exec_command(f"docker start {container_id}")

            sftp = self.ssh_client.open_sftp()

            for file_path in file_paths:
                try:
                    # Copy the file from the container to a temporary location on the remote server
                    remote_temp_path = f"/tmp/{os.path.basename(file_path)}.tar"
                    self.ssh_client.exec_command(f"docker cp {container_id}:{file_path} {remote_temp_path}")

                    # Define the local path where the file will be stored
                    local_file_path = os.path.join(local_temp_dir, os.path.basename(file_path))
                    
                    # Download the file from the remote server to the local machine
                    sftp.get(remote_temp_path, local_file_path)

                    
                    with open(local_file_path, 'r') as file:
                        content = file.readlines()
                        content.insert(0, file_path + '\n')
                
                    with open(local_file_path, 'w') as file:   
                        file.writelines(content)
                        self.logger.info(f"{file_path} Downloaded.\n")
                        print(f"{file_path} Downloaded.\n")

                    # Clean up the temporary files
                    self.ssh_client.exec_command(f"rm -f {remote_temp_path}")
                    

                except Exception as e:
                    self.logger.error(f"Failed to retrieve {file_path} from the Docker image: {e}")
                    print(f"Failed to retrieve {file_path} from the Docker image: {e}")

            # Stop and remove the container
            self.ssh_client.exec_command(f"docker rm -f {container_id}")
            sftp.close()

        except Exception as e:
            self.logger.error(f"An error occurred: {e}")
            print(f"An error occurred: {e}")
        
    # Function to update code in a Docker container and rerun the necessary commands
    def update_docker_code(self,updated_code_map,image_id):
        """
        Update code inside a Docker container (created from an image) and rerun the necessary commands.

        :param updated_code_map: Dictionary mapping file paths to updated code content.
        :param image_id: ID of the Docker image to start the container from.
        """
        try:
            # Step 1: Start a new container from the image ID
            start_container_cmd = f'docker run -d {image_id} /bin/sh -c "while true; do sleep 1000; done"'
            container_id, error= self.run_docker_command(start_container_cmd)
           
            if error:
                self.logger.error(f"Error starting container from image {image_id}: {error}")
                print(f"Error starting container from image {image_id}: {error}")
                return
            else:
                container_id=container_id.strip()
                self.logger.info(f"Container started with ID: {container_id}")
                print(f"Container started with ID: {container_id}")

            # Step 2: Iterate through the files in updated_code_map and update them in the Docker container
            for file_name, updated_code in updated_code_map.items():
                # Create a temporary file with the updated content
                temp_file = '/tmp/'+os.path.basename(file_name)
                
                # Write the updated code to the temp file on the remote host
                with self.ssh_client.open_sftp() as sftp:
                    with sftp.file(temp_file, 'w') as temp_file_handle:
                        temp_file_handle.write(updated_code)

                # Copy the temp file into the container
                copy_cmd = f"docker cp {temp_file} {container_id}:{file_name}"
                output, error = self.run_docker_command(copy_cmd)
                
                if error:
                    self.logger.error(f"Error copying file {file_name} to container: {error}")
                    print(f"Error copying file {file_name} to container: {error}")
                else:
                    self.logger.info(f"File {file_name} copied to container successfully.")
                    print(f"File {file_name} copied to container successfully.")

                # Remove the temp file after copying it into the container
                self.run_docker_command(f'rm {temp_file}')

            # 2. Once files are updated, run the necessary commands in the container
            breaking_command = f"docker exec {container_id} /bin/sh -c 'mvn clean test'"
            breaking_output, breaking_error = self.run_docker_command(breaking_command)
            
        #TODO uncomment later 
        # # Stop and remove the container
        #     self.ssh_client.exec_command(f"docker rm -f {container_id}")
        #     sftp.close()
        #     self.logger.info(f"Container {container_id} stopped and removed.")
        except Exception as e:
            print(f"An error occurred while updating the Docker container: {e}")
            self.logger.error(f"An error occurred while updating the Docker container: {e}")
        return breaking_output, breaking_error
    
    def close_connection(self):
        try:
            self.ssh_client.close()
            self.logger.info("SSH connection closed.")
            print("SSH connection connection closed.")
        
        except Exception as e:
            print(f"An error occurred while clossing SSH connection: {e}")
            self.logger.error(f"An error occurred while clossing SSH connection: {e}")

