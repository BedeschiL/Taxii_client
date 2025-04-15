import requests
from requests.auth import HTTPBasicAuth
from stix2 import parse, Filter, Bundle # Added Bundle
from taxii2client import Server # Keep Server for discovery if needed elsewhere, but requests is primary now
from datetime import datetime, timedelta
import json # For potential error parsing

# Define the required TAXII media type
TAXII_MEDIA_TYPE = "application/taxii+json;version=2.1"

class TAXIIClient:
    # Expect the full API Root URL now
    def __init__(self, api_root_url=None, collection_title=None, username=None, password=None):
        self.api_root_url = api_root_url.rstrip('/') if api_root_url else None # Ensure no trailing slash
        self.collection_title = collection_title # Store the title provided by the user
        self.username = username
        self.password = password
        self.auth = HTTPBasicAuth(self.username, self.password) if self.username and self.password else None
        self.headers = {"Accept": TAXII_MEDIA_TYPE}

    def _get_collection_id_by_title(self, title):
        """Helper to find collection ID based on its title."""
        if not self.api_root_url:
            print("Error: API Root URL not configured.")
            return None

        collections_url = f"{self.api_root_url}/collections/"
        try:
            response = requests.get(collections_url, auth=self.auth, headers=self.headers, timeout=30)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            collections_data = response.json()

            # The server returns a list of collection dicts directly at this endpoint
            # based on src/database/data_handling.py -> get_api_root_collections
            if isinstance(collections_data, list):
                 for collection in collections_data:
                    if collection.get('title') == title:
                        return collection.get('id')
            else:
                 print(f"Warning: Unexpected format for collections response from {collections_url}. Expected list.")


            print(f"Error: Collection with title '{title}' not found at {self.api_root_url}")
            return None

        except requests.exceptions.RequestException as e:
            print(f"Error discovering collections at {collections_url}: {str(e)}")
            # Attempt to parse error response if JSON
            try:
                error_details = response.json()
                print(f"Server error details: {json.dumps(error_details, indent=2)}")
            except (json.JSONDecodeError, AttributeError):
                 pass # Ignore if response is not JSON or response object doesn't exist
            return None
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from {collections_url}")
            print(f"Response text: {response.text}")
            return None


    def discover_collections(self):
        """Discover available collections on the TAXII server's API Root"""
        if not self.api_root_url:
            print("Error: API Root URL not provided for discovery.")
            return []

        collections_url = f"{self.api_root_url}/collections/"
        try:
            response = requests.get(collections_url, auth=self.auth, headers=self.headers, timeout=30)
            response.raise_for_status()
            collections_data = response.json()

            # Expecting a list of collection dicts
            if isinstance(collections_data, list):
                discovered = []
                for collection in collections_data:
                     discovered.append({
                        'title': collection.get('title', 'No Title'),
                        'description': collection.get('description', 'No description'),
                        'id': collection.get('id', 'No ID')
                    })
                return discovered
            else:
                print(f"Warning: Unexpected format for collections response from {collections_url}. Expected list.")
                return []

        except requests.exceptions.RequestException as e:
            print(f"Error discovering collections at {collections_url}: {str(e)}")
            try:
                error_details = response.json()
                print(f"Server error details: {json.dumps(error_details, indent=2)}")
            except (json.JSONDecodeError, AttributeError):
                 pass
            return []
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from {collections_url}")
            print(f"Response text: {response.text}")
            return []

    def get_indicators(self, simple_indicators=None):
        """Fetch indicators from the configured collection, handling pagination."""
        if not self.api_root_url or not self.collection_title:
            print("Error: API Root URL or Collection Title not configured.")
            return []

        # 1. Find the collection ID using the title
        collection_id = self._get_collection_id_by_title(self.collection_title)
        if not collection_id:
            return [] # Error message printed in helper

        objects_url_base = f"{self.api_root_url}/collections/{collection_id}/objects/"
        all_simple_indicators = []
        page = 1 # Server pagination seems to be 1-based from example URLs, but code uses 0-based skip. Let's assume API uses ?page=1, ?page=2...
        more = True

        print(f"Fetching indicators from {objects_url_base} for collection '{self.collection_title}' (ID: {collection_id})")

        while more:
            objects_url = f"{objects_url_base}?page={page}" # Adjust if server uses 0-based page or offset
            print(f"Requesting: {objects_url}")
            try:
                response = requests.get(objects_url, auth=self.auth, headers=self.headers, timeout=60)
                response.raise_for_status()
                envelope = response.json()

                # Server wraps objects in an envelope: {"more": bool, "next": id|null, "objects": [bundle]}
                # Note: data_handling.py -> create_envelope wraps the list itself: "objects": [[bundle1, bundle2]]
                # Let's assume it's "objects": [bundle1, bundle2] as that's more standard. Adjust if needed.
                stix_bundles_or_objects = envelope.get('objects', [])

                # Check if the structure is [[obj1, obj2]] or [obj1, obj2]
                if stix_bundles_or_objects and isinstance(stix_bundles_or_objects[0], list):
                     # It's the [[obj1, obj2]] structure from create_envelope
                     stix_bundles_or_objects = stix_bundles_or_objects[0]


                if not stix_bundles_or_objects:
                    print(f"No objects found on page {page}.")
                    more = False
                    continue

                print(f"Received {len(stix_bundles_or_objects)} STIX object(s)/bundle(s) on page {page}.")

                for item in stix_bundles_or_objects:
                    try:
                        # Parse the item. It could be a Bundle or a single SDO.
                        stix_object = parse(item, allow_custom=True)

                        indicators_in_item = []
                        if isinstance(stix_object, Bundle):
                            # If it's a bundle, filter for indicators within it
                            indicators_in_item = stix_object.objects.filter([
                                Filter('type', '=', 'indicator')
                            ])
                        elif stix_object.get('type') == 'indicator':
                            # If it's a single indicator object directly
                            indicators_in_item = [stix_object]

                        # Format the found indicators
                        for ind in indicators_in_item:
                            # Use pattern for value if value attribute doesn't exist (common for STIX indicators)
                            value = ind.get('pattern')
                            if hasattr(ind, 'value'): # Check if 'value' exists (less common for indicators)
                                value = ind.value

                            simple_indicators.append({
                                'id': ind.id, # Include ID for details link
                                'type': ind.type,
                                'value': value,
                                'description': ind.description if hasattr(ind, 'description') else '',
                                # Use 'valid_from' as 'first_seen' if 'last_seen' isn't present
                                'first_seen': ind.valid_from.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ind, 'valid_from') and ind.valid_from else 'N/A',
                                'last_seen': ind.last_seen.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ind, 'last_seen') and ind.last_seen else 'N/A',
                                'created': ind.created.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ind, 'created') and ind.created else '',
                                'modified': ind.modified.strftime('%Y-%m-%d %H:%M:%S') if hasattr(ind, 'modified') and ind.modified else '',
                                'source': self.collection_title # Use title for display
                            })

                    except Exception as parse_err:
                        print(f"Warning: Failed to parse STIX object: {parse_err}. Object: {item}")
                        continue # Skip this object

                # Check pagination
                more = envelope.get('more', False)
                if more:
                    page += 1
                else:
                    print("No more pages indicated by server.")

            except requests.exceptions.RequestException as e:
                print(f"Error fetching objects from {objects_url}: {str(e)}")
                try:
                    error_details = response.json()
                    print(f"Server error details: {json.dumps(error_details, indent=2)}")
                except (json.JSONDecodeError, AttributeError):
                    pass
                more = False # Stop pagination on error
            except json.JSONDecodeError:
                print(f"Error: Could not decode JSON response from {objects_url}")
                print(f"Response text: {response.text}")
                more = False # Stop pagination on error
            except Exception as e:
                print(f"An unexpected error occurred during indicator fetching: {str(e)}")
                import traceback
                traceback.print_exc()
                more = False # Stop pagination on unexpected error


        print(f"Fetched a total of {len(all_simple_indicators)} indicators.")
        return all_simple_indicators

    def get_indicator_by_id(self, indicator_id):
        """Fetch a single indicator by its ID."""
        if not self.api_root_url or not self.collection_title:
             print("Error: API Root URL or Collection Title not configured.")
             return None

        collection_id = self._get_collection_id_by_title(self.collection_title)
        if not collection_id:
            return None

        object_url = f"{self.api_root_url}/collections/{collection_id}/objects/{indicator_id}/"
        print(f"Requesting indicator details: {object_url}")

        try:
            response = requests.get(object_url, auth=self.auth, headers=self.headers, timeout=30)
            response.raise_for_status()
            stix_data = response.json() # Server returns the object directly here (likely wrapped in list/envelope still?)

            # DataHandler.get_api_root_collections_object_by_id returns an envelope like get_objects
            # Let's assume the same envelope structure: {"objects": [[stix_object]]}
            objects_list = stix_data.get('objects', [])
            if objects_list and isinstance(objects_list[0], list):
                 stix_item = objects_list[0][0] if objects_list[0] else None
            elif objects_list: # Should be [stix_object]
                 stix_item = objects_list[0]
            else:
                 stix_item = None


            if not stix_item:
                 print(f"Indicator {indicator_id} not found or empty response from {object_url}")
                 return None

            # Parse the STIX object (could be a bundle containing the indicator)
            stix_object = parse(stix_item, allow_custom=True)

            target_indicator = None
            if isinstance(stix_object, Bundle):
                 # Find the indicator within the bundle
                 for obj in stix_object.objects:
                     if obj.id == indicator_id and obj.type == 'indicator':
                         target_indicator = obj
                         break
            elif stix_object.id == indicator_id and stix_object.type == 'indicator':
                 target_indicator = stix_object

            if target_indicator:
                 # Format the indicator (reuse formatting logic)
                 value = target_indicator.get('pattern')
                 if hasattr(target_indicator, 'value'):
                     value = target_indicator.value

                 # Return the full STIX object as dict for details view
                 # return target_indicator.serialize(pretty=False) # Return full STIX JSON
                 # Or return the simplified format if preferred
                 return {
                    'id': target_indicator.id,
                    'raw': target_indicator.serialize(pretty=True), # Add raw STIX for display
                    'type': target_indicator.type,
                    'value': value,
                    'description': target_indicator.description if hasattr(target_indicator, 'description') else '',
                    'first_seen': target_indicator.valid_from.strftime('%Y-%m-%d %H:%M:%S') if hasattr(target_indicator, 'valid_from') and target_indicator.valid_from else 'N/A',
                    'last_seen': target_indicator.last_seen.strftime('%Y-%m-%d %H:%M:%S') if hasattr(target_indicator, 'last_seen') and target_indicator.last_seen else 'N/A',
                    'created': target_indicator.created.strftime('%Y-%m-%d %H:%M:%S') if hasattr(target_indicator, 'created') and target_indicator.created else '',
                    'modified': target_indicator.modified.strftime('%Y-%m-%d %H:%M:%S') if hasattr(target_indicator, 'modified') and target_indicator.modified else '',
                    'source': self.collection_title
                 }
            else:
                 print(f"Indicator object with ID {indicator_id} not found within the response from {object_url}")
                 return None

        except requests.exceptions.HTTPError as e:
             if e.response.status_code == 404:
                 print(f"Indicator {indicator_id} not found at {object_url} (404)")
             else:
                 print(f"HTTP error fetching indicator {indicator_id}: {str(e)}")
                 try:
                    error_details = response.json()
                    print(f"Server error details: {json.dumps(error_details, indent=2)}")
                 except (json.JSONDecodeError, AttributeError):
                    pass
             return None
        except requests.exceptions.RequestException as e:
            print(f"Error fetching indicator {indicator_id}: {str(e)}")
            return None
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON response from {object_url}")
            print(f"Response text: {response.text}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred fetching indicator {indicator_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return None