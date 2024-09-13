import paramiko
import os
import re

# DockerHandler class for managing Docker tasks over SSH
class DockerHandler:
    def __init__(self, hostname, username, ssh_key_path, ssh_passphrase=None):
        if not all([hostname, username, ssh_key_path]):
            raise ValueError("SSH_HOSTNAME, SSH_USERNAME, and SSH_KEY_PATH must be set in the environment.")
        
        self.hostname = hostname
        self.username = username
        self.ssh_key_path = ssh_key_path
        self.ssh_passphrase = ssh_passphrase
        self.ssh_client = self._create_ssh_client()

    def _create_ssh_client(self):
        """Creates and returns an SSH client."""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(self.hostname, username=self.username, key_filename=self.ssh_key_path, passphrase=self.ssh_passphrase)
        return ssh

    def run_docker_command(self, command):
        """Runs a Docker command on the remote server and returns output and error."""
        stdin, stdout, stderr = self.ssh_client.exec_command(command)
        output = stdout.read().decode('utf-8')
        error = stderr.read().decode('utf-8')
        return output, error
    
    
    # Function to update code in a Docker container and rerun the necessary commands
    def update_docker_code(self,updated_code_map,image_id):
        """
        Update code inside a Docker container (created from an image) and rerun the necessary commands.

        :param updated_code_map: Dictionary mapping file paths to updated code content.
        :param ssh: Paramiko SSH connection object to access the host machine.
        :param image_id: ID of the Docker image to start the container from.
        """
        try:
            # Step 1: Start a new container from the image ID
            start_container_cmd = f'docker run -d {image_id} /bin/sh -c "while true; do sleep 1000; done"'
            stdin, stdout, stderr = self.ssh.exec_command(start_container_cmd)
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
                with self.ssh.open_sftp() as sftp:
                    with sftp.file(temp_file, 'w') as temp_file_handle:
                        temp_file_handle.write(updated_code)

                # Copy the temp file into the Docker container
                # #TODO FIX LATER
                # if(file_name =="MvcEventListener.java"):
                #     dir="jakartaee-mvc-sample/src/main/java/com/example/"
                # elif(file_name =="PostNotFoundExceptionMapper.java"):
                #     dir="jakartaee-mvc-sample/src/main/java/com/example/config/"
                # else:
                #     dir="jakartaee-mvc-sample/src/main/java/com/example/web/"
                # file_path=dir+file_name
                file_path=updated_code_map[file_name]
                copy_cmd = f"docker cp {temp_file} {container_id}:{file_path}"
                stdin, stdout, stderr = self.ssh.exec_command(copy_cmd)
                error = stderr.read().decode()
                if error:
                    print(f"Error copying file {file_path} to container: {error}")
                else:
                    print(f"File {file_path} copied to container successfully.")
                # Remove the temp file after copying it into the container
                self.ssh.exec_command(f'rm {temp_file}')

            # 2. Once files are updated, restart the container or rerun the command to fix issues
            # For example, rerun the command that was failing or restart the service inside the container.
            # You can modify this to match your specific command, e.g., restarting a service
            # restart_cmd = f'docker exec {breaking_container} /path/to/your/command.sh'
            # Run breaking update Docker command
            # breaking_command = f"docker exec -ti {container_id} /bin/sh -c 'cd jakartaee-mvc-sample/ && mvn clean test'"
            breaking_command = f"docker exec {container_id} /bin/sh -c 'mvn clean test'"
        
            breaking_output, breaking_error = self.run_docker_command(breaking_command)
            return breaking_output, breaking_error, file_path
            
        #TODO uncomment later 
        # # Stop and remove the container
        #     ssh.exec_command(f"docker rm -f {container_id}")
        #     sftp.close()
        except Exception as e:
            print(f"An error occurred while updating the Docker container: {e}")

