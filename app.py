import requests
from flask import Flask, render_template, request, jsonify, redirect, url_for
# Remove direct stix2/taxii2client imports if only used in TAXIIClient
# from stix2 import TAXIICollectionSource, Filter
# from taxii2client import Server, Collection
from taxii2client import Server # Keep for API Root discovery

from taxii_client import TAXIIClient
import json
import os
from datetime import datetime
import logging # Add logging

# Import Config
from config import Config

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config.from_object(Config) # Load config from object

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Initialize TAXII Client (not needed globally anymore, created per feed)
# taxii_client = TAXIIClient() # Remove this

def load_feeds():
    if not os.path.exists(app.config['TAXII_FEEDS_FILE']):
        return []
    try:
        with open(app.config['TAXII_FEEDS_FILE'], 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {app.config['TAXII_FEEDS_FILE']}")
        return [] # Return empty list on error
    except Exception as e:
        logging.error(f"Error loading feeds: {e}")
        return []


def save_feeds(feeds):
    try:
        with open(app.config['TAXII_FEEDS_FILE'], 'w') as f:
            json.dump(feeds, f, indent=4) # Add indent for readability
    except Exception as e:
        logging.error(f"Error saving feeds: {e}")


def load_indicators():
    if not os.path.exists(app.config['INDICATORS_FILE']):
        return []
    try:
        with open(app.config['INDICATORS_FILE'], 'r') as f:
            # Handle empty file case
            content = f.read()
            if not content:
                return []
            return json.loads(content)
    except json.JSONDecodeError:
        logging.error(f"Error decoding JSON from {app.config['INDICATORS_FILE']}")
        # Optionally backup the corrupted file here
        return [] # Return empty list on error
    except Exception as e:
        logging.error(f"Error loading indicators: {e}")
        return []


def save_indicators(indicators):
    try:
        with open(app.config['INDICATORS_FILE'], 'w') as f:
            json.dump(indicators, f, indent=4) # Add indent
    except Exception as e:
        logging.error(f"Error saving indicators: {e}")


@app.route('/')
def index():
    feeds = load_feeds()
    indicators = load_indicators()
    # Sort indicators by modified/created date if available? (Optional)
    # indicators.sort(key=lambda x: x.get('modified') or x.get('created') or '', reverse=True)
    return render_template('index.html', feeds=feeds, indicators=indicators)

# Removed the misplaced get_indicators function from here

@app.route("/indicator_details/<string:indicator_id>", methods=["GET"])
def indicator_details(indicator_id):
    feeds = load_feeds()
    found_indicator = None

    # Search through all feeds for the indicator ID
    # This assumes indicator IDs are unique across feeds, which might not be true.
    # A better approach might be to store the feed source with the indicator
    # and only query that specific feed.
    # For now, we query all feeds until found.
    for feed in feeds:
        logging.info(f"Searching for indicator {indicator_id} in feed '{feed['name']}'")
        try:
            # Pass the API Root URL and Collection Title
            client = TAXIIClient(
                feed['url'], # This is now the API Root URL
                feed['collection'], # This is the Collection Title
                feed.get('username'),
                feed.get('password')
            )

            # Call the implemented method in TAXIIClient
            indicator = client.get_indicator_by_id(indicator_id)
            if indicator:
                found_indicator = indicator
                break # Stop searching once found

        except Exception as e:
            logging.error(f"Error querying feed '{feed['name']}' for indicator {indicator_id}: {e}")
            continue # Try next feed

    if found_indicator:
         # Check if indicator has 'raw' key from taxii_client
         if 'raw' not in found_indicator:
              found_indicator['raw'] = json.dumps(found_indicator, indent=2) # Basic fallback

         return jsonify({
            'success': True,
            'indicator': found_indicator
         })
    else:
        logging.warning(f"Indicator {indicator_id} not found in any feed.")
        return jsonify({'success': False, 'error': 'Indicator not found in configured feeds'})


@app.route("/discover_api_roots", methods=["POST"])
def discover_api_roots():
    # This discovers API roots at the *base* server URL
    server_url = request.form.get("server_url") # e.g., http://localhost:6100
    username = request.form.get("username")
    password = request.form.get("password")

    if not server_url:
         return jsonify({"success": False, "error": "Server URL is required."})

    logging.info(f"Discovering API roots at {server_url}")
    api_roots_list = []
    error_msg = None

    try:
        # Use taxii2client Server for discovery endpoint
        server = Server(server_url, user=username, password=password) # Specify version
        # The server's discovery endpoint is /taxii2/
        # Server() might try /taxii/ first, then /taxii2/. Check taxii2client docs if issues.
        logging.debug("Attempting to discover API roots...")
        # Accessing server.api_roots triggers the discovery call
        roots = server.api_roots
        logging.debug(f"Found {len(roots)} API roots.")
        logging.debug("API roots: %s", roots)
        if roots:
            for root in roots:
                logging.debug(f"Found API root: {root.title}")
                logging.debug(f"API root: {root.description}")
                api_roots_list.append({
                    'title': root.title,
                    'description': root.description or 'No description provided',
                    'url': root.url # This is the full API Root URL needed for other calls
                })
            logging.info(f"Discovered {len(api_roots_list)} API roots.")
        else:
            logging.warning(f"No API roots found at {server_url}")
            error_msg = "No API Roots found at this URL."

    except requests.exceptions.ConnectionError:
        error_msg = f"Could not connect to server at {server_url}."
        logging.error(error_msg)
    except requests.exceptions.HTTPError as e:
        error_msg = f"HTTP Error: {e.response.status_code} - {e.response.reason}."
        if e.response.status_code == 401:
            error_msg += " Check credentials."
        logging.error(f"HTTP Error discovering API roots at {server_url}: {e}")
    except Exception as e:
        error_msg = f"An unexpected error occurred: {str(e)}"
        logging.exception(f"Error discovering API roots at {server_url}") # Log full traceback

    if error_msg:
        return jsonify({"success": False, "error": error_msg})
    elif not api_roots_list and not error_msg:
         # Handle case where connection is fine but no roots reported
         return jsonify({"success": True, "api_roots": [], "message": "Connected successfully, but no API Roots reported by the server."})
    else:
        return jsonify({"success": True, "api_roots": api_roots_list})


@app.route('/add_feed', methods=['POST'])
def add_feed():
    # 'url' field now expects the full API Root URL
    api_root_url = request.form.get('url')
    # 'collection' field is the Collection Title
    collection_title = request.form.get('collection')

    if not api_root_url or not collection_title:
         # Add some basic validation feedback if possible
         # For now, just redirect back
         logging.warning("Add feed attempt failed: Missing URL or Collection Title.")
         return redirect(url_for('index')) # Ideally show an error message

    feed_data = {
        'name': request.form.get('name', 'Untitled Feed'), # Provide default name
        'url': api_root_url.rstrip('/'), # Store without trailing slash
        'collection': collection_title, # Store the title
        'username': request.form.get('username'),
        'password': request.form.get('password'),
        'added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    feeds = load_feeds()
    feeds.append(feed_data)
    save_feeds(feeds)
    logging.info(f"Added new feed: {feed_data['name']}")

    return redirect(url_for('index'))


@app.route('/delete_feed/<int:feed_id>', methods=['POST'])
def delete_feed(feed_id):
    feeds = load_feeds()
    if 0 <= feed_id < len(feeds):
        deleted_feed_name = feeds[feed_id].get('name', 'Unknown')
        feeds.pop(feed_id)
        save_feeds(feeds)
        logging.info(f"Deleted feed: {deleted_feed_name} (Index: {feed_id})")
    else:
        logging.warning(f"Attempted to delete invalid feed index: {feed_id}")
    return redirect(url_for('index'))


@app.route('/refresh_feeds', methods=['POST'])
def refresh_feeds():
    feeds = load_feeds()
    all_indicators = []
    total_fetched = 0
    errors = []

    logging.info(f"Starting refresh for {len(feeds)} feeds.")
    for feed in feeds:
        feed_name = feed.get('name', 'Unknown Feed')
        logging.info(f"Refreshing feed: {feed_name}")
        try:
            # Pass API Root URL and Collection Title
            client = TAXIIClient(
                feed['url'],
                feed['collection'],
                feed.get('username'),
                feed.get('password')
            )
            indicators = client.get_indicators()
            logging.info(f"Fetched {len(indicators)} indicators from feed: {feed_name}")
            # Add source feed name to each indicator for clarity
            for ind in indicators:
                ind['feed_source'] = feed_name
            all_indicators.extend(indicators)
            total_fetched += len(indicators)
        except Exception as e:
            error_msg = f"Error fetching from feed '{feed_name}': {str(e)}"
            logging.exception(f"Error refreshing feed '{feed_name}'") # Log full traceback
            errors.append(error_msg)

    # Overwrite existing indicators file with the latest fetch
    save_indicators(all_indicators)
    logging.info(f"Refresh complete. Total indicators saved: {len(all_indicators)}")

    if errors:
         return jsonify({'success': False, 'count': len(all_indicators), 'errors': errors})
    else:
         return jsonify({'success': True, 'count': len(all_indicators)})


@app.route("/discover_collections", methods=["POST"])
def discover_collections():
    # Expects the full API Root URL now
    api_root_url = request.form.get("api_root_url")
    username = request.form.get("username")
    password = request.form.get("password")

    if not api_root_url:
        return jsonify({"success": False, "error": "API Root URL is required."})

    logging.info(f"Discovering collections for API Root: {api_root_url}")
    try:
        # Use our client which expects the API Root URL
        client = TAXIIClient(api_root_url, None, username, password)
        collections = client.discover_collections() # This now uses requests
        if collections:
             logging.info(f"Discovered {len(collections)} collections.")
             return jsonify({"success": True, "collections": collections})
        else:
             # discover_collections might return empty list on error or if none found
             # Check logs for specific errors printed by TAXIIClient
             logging.warning(f"No collections discovered or error occurred for {api_root_url}.")
             # Provide slightly more info if possible
             # We might need TAXIIClient to return error details better
             return jsonify({"success": False, "error": f"Could not discover collections at {api_root_url}. Check logs for details."})

    except Exception as e:
        logging.exception(f"Error during collection discovery for {api_root_url}")
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"})


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '').lower()
    indicators = load_indicators()
    feeds = load_feeds()

    if query:
        logging.info(f"Searching indicators for query: '{query}'")
        filtered_indicators = []
        for indicator in indicators:
            if (query in str(indicator.get('value', '')).lower() or
                    query in str(indicator.get('description', '')).lower() or
                    query in str(indicator.get('type', '')).lower() or
                    query in str(indicator.get('feed_source', '')).lower()):
                filtered_indicators.append(indicator)
        indicators = filtered_indicators
        logging.info(f"Found {len(indicators)} matching indicators.")
    else:
        logging.info("Displaying all indicators (no search query).")

    current_year = datetime.now().year # <<< Get the current year
    return render_template('index.html',
                           feeds=feeds,
                           indicators=indicators,
                           search_query=query,
                           current_year=current_year) # <<< Pass it here too



if __name__ == '__main__':
    if not os.path.exists(app.config['TAXII_FEEDS_FILE']):
        save_feeds([])
    if not os.path.exists(app.config['INDICATORS_FILE']):
        save_indicators([])
    logging.info("Starting Flask application...")
    app.run(host='0.0.0.0', port=5000, debug=True)