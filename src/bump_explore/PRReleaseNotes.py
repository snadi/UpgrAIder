import requests
from bs4 import BeautifulSoup

class ReleaseNotes:
    def __init__(self,api, version, description):
        self.api=api
        self.version = version
        self.description = description
        


class PRReleaseNotes:
    def __init__(self,data,github_token=None):
        self.data=data
        self.github_token = github_token

    def fetch_pr_content(self):
        headers = {
        "Accept": "application/vnd.github.v3+json"
        }
    
        # Add token for authenticated requests (optional)
        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        
        try:
            response = requests.get(self.data.get('url'), headers=headers)
            
            if response.status_code == 200:
                    #Check if the content is JSON
                    if response.headers.get("Content-Type") == "application/json":
                        # Try to parse the JSON response
                        return response.json(), "json"
                    #check if resposne.header.get("Content-Type") contains text/html
                    if response.headers.get("Content-Type").find("text/html") > -1:
                        return response.text, "html"
                
                    else:
                        # Print the raw response if it's not JSON or HTML
                        print(f"Unexpected content type: {response.headers.get('Content-Type')}")
                        print("Response body:", response.text)
                        return None, None
            else:
                print(f"Failed to retrieve PR data. Status code: {response.status_code}")
                print("Response body:", response.text)
                return None, None
        
        except Exception as e:
            print(f"Error processing pr url: {e}")
            print("Raw response content:", response.text)
            return None,None

    def extract_release_notes_from_html(self,html_content):
        """
        This function processes the provided HTML content and extracts release notes.
        """
        # Try to locate common tags that might contain release notes
        release_notes = None
           
        # Parse the HTML content using BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')

        # Try to locate the text with release notes
    
        details = soup.find_all('details')
        release_notes = None

        if details:
            for detail in details:      
                summary = detail.find('summary')
                if summary and 'release notes' in summary.text.lower():
                    # Extract the text inside the <blockquote> and any <ul> for structured release notes
                    blockquote = detail.find('blockquote')
                    ul_list = detail.find_all('ul')

                    release_notes = ""
                    
                    # Extract and format the blockquote content
                    if blockquote:
                        release_notes += blockquote.text.strip() + "\n\n"
                    
                    # Extract and format the list of bullet points
                    if ul_list:
                        for ul in ul_list:
                            for li in ul.find_all('li'):
                                release_notes += f"- {li.text.strip()}\n"
            
            # If release notes found, return them
            if release_notes:
                dependency_group_id = self.data['updatedDependency']['dependencyGroupID']
                new_version = self.data['updatedDependency']['newVersion']
                
                return ReleaseNotes(dependency_group_id,new_version, release_notes) 
              
            else:
                return None
        

    def get_release_notes(self):
        """Main method to fetch the PR content and check for release notes."""
        try:
            pr_content = self.fetch_pr_content()
            return self.extract_release_notes_from_html(pr_content)
        except Exception as e:
            print(f"Error: {e}")
            return None