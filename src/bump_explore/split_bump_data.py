#Script to process the benchmark folder and sperate files into dicrectory based on failureCategory
import os
import shutil
import argparse
import json


def parse_arguments():
    parser = argparse.ArgumentParser(description='Process JSON files to split based on failure category.')
    parser.add_argument('--output_dir', required=True, type=str, help='Folder path for output folder.')
    parser.add_argument('--json_folder_path', required=True, type=str, help='Folder path containing the JSON files.')
 
    return parser.parse_args()

def load_json_file(file_path):
    """Utility to load a JSON file."""

    with open(file_path, 'r') as f:
        return json.load(f)
    
def main():
    args = parse_arguments()
    try:    
        files_list = [f for f in os.listdir(args.json_folder_path) if os.path.isfile(os.path.join(args.json_folder_path, f)) and f.endswith('.json')]       
        for filename in files_list:
            if filename.endswith('.json'):
                print(f"Processing {filename}")
                json_file_path = os.path.join(args.json_folder_path, filename)
                data=load_json_file(json_file_path)
                new_folder = os.path.join(args.output_dir, data.get('failureCategory'))
                if not os.path.exists(new_folder):
                    os.makedirs(new_folder, exist_ok=True)
                shutil.move(json_file_path, os.path.join(new_folder, filename))
                print(f"Moved {filename} to {new_folder}")
    except Exception as e:
        print(f"An error occurred: {e}")   

if __name__ == "__main__":
    main()
