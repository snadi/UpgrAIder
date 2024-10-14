import json
import os
import re
import argparse
from dotenv import load_dotenv
from utils.DockerHandler import DockerHandler
import upgraider
from upgraider import upgraide
from upgraider.upgraide import Upgraider
from apiexploration.Library import CodeSnippet, Library
from upgraider.Model import Model
import logging
import random
from pathlib import Path
from utils.util import extract_error_file_paths
from utils.util import load_json_file
from utils.util import select_random_files
from utils.util import setup_logger
from utils.util import check_for_errors
from process_release_db import get_library_release_notes
from utils.util import get_fixed_files, get_unfixed_files, get_new_errors, get_processed_files


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
    parser.add_argument('--db_name', type=str, help='Databse for release notes.')
    parser.add_argument('--use_embedding', action='store_true', help='If set use embedding to reterive refrences to release notes.')
   
    return parser.parse_args()



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


def fix_files_with_llm(error_files, local_temp_dir,library,db_name,model="gpt-4o-mini", db_source="modelonly", use_references=True, threshold=0.5,use_embedding=False):
    """
    Fixes the code in files causing errors using LLM and saves the updated code in separate files for comparison.
    """
    updated_code_map = {}
    
    # Loop through each file causing the error
    for file_path in error_files:
        try:
            if not os.path.exists(f"{local_temp_dir}/updated/"):
                os.makedirs(f"{local_temp_dir}/updated/")
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
                output_dir=local_temp_dir,
                use_embeddings=use_embedding,
                db_name=db_name,
                errorFile=os.path.basename(file_path)
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


#Main function to process the JSON files
def process_json_file(logger,docker_handler, file_path, no_download_files, output_dir,library,model,db_source,use_references,threshold,db_name,use_embedding):
    
    # Check if the output directory exists, if not, create it
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    data = load_json_file(file_path)

    # pre_command = data.get('preCommitReproductionCommand')
    breaking_command = data.get('breakingUpdateReproductionCommand')
    # Extract Docker image name from the breaking update command
    breaking_image_name = extract_docker_image_name(data, 'breakingUpdateReproductionCommand')

    # # Run pre-commit Docker command
    # pre_output, pre_error = docker_handler.run_docker_command(pre_command)
    # pre_success, pre_failure_message = check_for_errors(pre_output, pre_error)

    # # Report results for pre-commit
    # if pre_success:
    #     print(f"{file_path} - Pre-commit build/test succeeded.")
    #     logger.info(f"{file_path} - Pre-commit build/test succeeded.")
    # else:
    #     print(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")
    #     logger.error(f"{file_path} - Pre-commit build/test failed. Error: {pre_failure_message}")   
    #     return -1,-1

    # Run breaking update Docker command
    breaking_output, breaking_error = docker_handler.run_docker_command(breaking_command)
    breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)
    error_files_path=os.path.join(output_dir,"error_files")
    # Report results for breaking update
    if breaking_success:
        print(f"{os.path.basename(file_path)} - Breaking update build/test succeeded.")
        logger.info(f"{os.path.basename(file_path)} - Breaking update build/test succeeded.") 
        return -1,-1,None,None
    else:
        error_files = extract_error_file_paths(breaking_failure_message)
        pre_fix_error_files = len(error_files)
        if error_files:
            if not os.path.exists(os.path.join(output_dir,"error_files")):
                os.makedirs(os.path.join(output_dir,"error_files"))
            pre_fix_error_list=error_files
            #store list of files for pre-fix
            file_path_error=os.path.join(error_files_path,f"{os.path.basename(file_path).replace('.json','')}_error_files.txt")
            with open(file_path_error, 'w') as f:
                f.write("Pre-fix Error Files:\n")
                for item in error_files:
                    f.write("%s\n" % item)
                f.write("------------------\n")     

            print(f"{os.path.basename(file_path)} - Breaking update build/test failed. Files causing issues:")
            logger.error(f"{os.path.basename(file_path)} - Breaking update build/test failed. Error: {breaking_failure_message}")
            logger.error("Files causing issues:")
            for error_file in error_files:
                print(f" - {error_file}")
                logger.error(f" - {error_file}")
            print("-------------------")
            logger.info("-------------------")
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
                updated_code_map=fix_files_with_llm(error_files,local_temp_dir,library,db_name,model,db_source,use_references,threshold,use_embedding)
                
                print("------Rerunning container after fixes-------------")
                logger.info("---------Rerunning container after fixes ----------")
                # Update the code in the Docker container and rerun the necessary commands check if breaking issue is fixed
                breaking_output, breaking_error=docker_handler.update_docker_code(updated_code_map,breaking_image_name)
                breaking_success, breaking_failure_message = check_for_errors(breaking_output, breaking_error)
             
                # Report results for breaking update
                if breaking_success:
                    print(f"{os.path.basename(error_file)} - Breaking update build/test succeeded after fixes.")
                    logger.info(f"{os.path.basename(error_file)} - Breaking update build/test succeeded after fixes.")
                    post_fix_error_files = 0
                    post_fix_error_list=[]
                elif breaking_failure_message:
                    post_fix_error_list=[]
                    error_files = extract_error_file_paths(breaking_failure_message)
                    post_fix_error_files = len(error_files)
                    print("-------------------")
                    logger.info("-------------------")
                    if error_files:
                        post_fix_error_list=error_files
                        #store list of files for post-fix
                        with open(file_path_error, 'a') as f:
                            f.write("Post-fix Error Files:\n")
                            for item in error_files:
                                f.write("%s\n" % item)
                            f.write("-------------------\n")     
                        print("Breaking update build/test failed after fixes. Files causing issues:")
                        logger.error(f"{os.path.basename(file_path)} - Breaking update build/test failed after fixes. Files causing issues:") 
                        #print(breaking_failure_message)
                        # logger.error(breaking_failure_message)
                        for error_file in error_files:
                            print(f" - {error_file}")
                            logger.error(f" - {error_file}")
                else:
                    print(f"Failed to reprocess {breaking_image_name}.")
                    logger.error(f"Failed to reprocess {breaking_image_name}.")
            else:
                print(f"{os.path.basename(error_file)} - Breaking update build/test failed. No specific files identified.")
                logger.error(f"Failed to reprocess {breaking_image_name}.")
    return  pre_fix_error_files, post_fix_error_files, pre_fix_error_list, post_fix_error_list


# Main function
def main():
    args = parse_arguments()
    #check that output directory exists
    if not os.path.exists(args.output_dir):
        os.makedirs(args.output_dir)
    new_run=False    
    if  not os.path.exists(os.path.join(args.output_dir, "run_data.csv")):
        new_run=True;    
    with open(os.path.join(args.output_dir, "run_data.csv"), 'a') as f:
        if new_run:
            f.write("CommitID,Pre-fix_Count,Post-fix_Count,Fixed, Unfixed, New_Errors\n")
        # Process a specific file if provided
        try:      
            if args.specific_file:
                specific_file_path = os.path.join(args.json_folder_path, args.specific_file)
                logger=setup_logger(f"{args.specific_file.replace(".json","")}.log",args.output_dir)
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

                #filter already processed files if any
                processed_files=get_processed_files(os.path.join(args.output_dir,"logs"))
                docker_handler = DockerHandler(hostname, username, ssh_key_path,args.output_dir,ssh_passphrase)
                for filename in files_list:
                    if filename.endswith('.json'):
                        if filename.replace('.json', '') in processed_files:
                            print(f"{filename} has already been processed and will be skipped.")
                            continue
                        json_file_path = os.path.join(args.json_folder_path, filename) 
                        data = load_json_file(json_file_path)
                        if data.get('failureCategory') == args.category:
                            print(f"Processing {filename}...")
                            logger=setup_logger(f"{filename.replace(".json","")}.log",args.output_dir)
                            docker_handler.set_logger(logger)
                            library = create_library_from_json(data,"")
                            pre_fix_num,post_fix_num,pre_fix_errors_files, post_fix_errors_files=process_json_file(logger,docker_handler, json_file_path,args.no_download_files,args.output_dir,library,
                                                                       args.model,args.db_source,args.use_references,args.threshold,args.db_name,args.use_embedding)
                           
                            if pre_fix_num > 0 :
                                fixed_files=get_fixed_files(pre_fix_errors_files,post_fix_errors_files)
                                non_fixed_files=get_unfixed_files(pre_fix_errors_files,post_fix_errors_files)
                                introducted_files=get_new_errors(pre_fix_errors_files,post_fix_errors_files)
                                f.write(f"{filename},{pre_fix_num},{post_fix_num},{len(fixed_files)},{len(non_fixed_files)},{len(introducted_files)}\n")
                                print("-------------------")
                                print(f"{filename} before fix error is {pre_fix_num} and after fix error is {post_fix_num}")
                                logger.info(f"{filename} before fix error is {pre_fix_num} and after fix error is {post_fix_num}")
                                print("-------------------")
                            else:
                                print("Issue with reproduciability, breaking commit is not failing")   
                                logger.error("Issue with reproduciability, breaking commit is not failing") 
                        else:
                            print(f"{filename} does not match the failure category '{args.category}' and will not be processed.")
                        print(f"Processed {filename}.")    
    
            # Close the SSH connection
            docker_handler.close_connection()
        except Exception as e:
            print(f"An error occurred: {e}")   

if __name__ == "__main__":
    main()