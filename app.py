from flask import Flask, render_template, request, jsonify, redirect, url_for
from stix2 import TAXIICollectionSource, Filter
from taxii2client import Server, Collection

from taxii_client import TAXIIClient
import json
import os
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')

# Configuration
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['TAXII_FEEDS_FILE'] = 'taxii_feeds.json'
app.config['INDICATORS_FILE'] = 'indicators.json'

# Initialize TAXII Client
taxii_client = TAXIIClient()

def load_feeds():
    if not os.path.exists(app.config['TAXII_FEEDS_FILE']):
        return []
    with open(app.config['TAXII_FEEDS_FILE'], 'r') as f:
        return json.load(f)

def save_feeds(feeds):
    with open(app.config['TAXII_FEEDS_FILE'], 'w') as f:
        json.dump(feeds, f)

def load_indicators():
    if not os.path.exists(app.config['INDICATORS_FILE']):
        return []
    with open(app.config['INDICATORS_FILE'], 'r') as f:
        return json.load(f)

def save_indicators(indicators):
    with open(app.config['INDICATORS_FILE'], 'w') as f:
        json.dump(indicators, f)

@app.route('/')
def index():
    feeds = load_feeds()
    indicators = load_indicators()
    return render_template('index.html', feeds=feeds, indicators=indicators)


def get_indicators(self, limit=100, offset=0):
    if not self.server_url or not self.collection_name:
        return []

    try:
        server = Server(self.server_url, user=self.username, password=self.password)
        api_root = server.api_roots[0]

        for collection in api_root.collections:
            if collection.title == self.collection_name:
                taxii_collection = Collection(
                    collection.url,
                    user=self.username,
                    password=self.password
                )
                tc_source = TAXIICollectionSource(taxii_collection)

                # Get indicators with pagination
                filt = Filter('type', '=', 'indicator')
                indicators = tc_source.query([filt], limit=limit, offset=offset)

                # Convert to simple format
                simple_indicators = []
                for ind in indicators:
                    simple_indicators.append({
                        'id': ind.id,
                        'type': ind.type,
                        'value': ind.value if hasattr(ind, 'value') else ind.pattern,
                        'description': ind.description if hasattr(ind, 'description') else '',
                        'last_seen': ind.last_seen if hasattr(ind, 'last_seen') else '',
                        'created': ind.created if hasattr(ind, 'created') else '',
                        'modified': ind.modified if hasattr(ind, 'modified') else '',
                        'source': self.collection_name
                    })

                return simple_indicators
    except Exception as e:
        print(f"Error fetching indicators: {str(e)}")
        return []

    return []

@app.route("/indicator_details/<string:indicator_id>", methods=["GET"])
def indicator_details(indicator_id):
    feeds = load_feeds()

    for feed in feeds:
        try:
            client = TAXIIClient(
                feed['url'],
                feed['collection'],
                feed.get('username'),
                feed.get('password')
            )

            # This would need to be implemented in TAXIIClient
            indicator = client.get_indicator_by_id(indicator_id)
            if indicator:
                return jsonify({
                    'success': True,
                    'indicator': indicator
                })

        except Exception as e:
            continue

    return jsonify({'success': False, 'error': 'Indicator not found'})

@app.route("/discover_api_roots", methods=["POST"])
def discover_api_roots():
    server_url = request.form.get("server_url")
    username = request.form.get("username")
    password = request.form.get("password")

    try:
        server = Server(server_url, user=username, password=password)
        api_roots = [{
            'title': root.title,
            'description': root.description or 'Default API Root',
            'url': root.url
        } for root in server.api_roots]

        return jsonify({"success": True, "api_roots": api_roots})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/add_feed', methods=['POST'])
def add_feed():
    feed_data = {
        'name': request.form.get('name'),
        'url': request.form.get('url'),
        'collection': request.form.get('collection'),
        'username': request.form.get('username'),
        'password': request.form.get('password'),
        'added': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }

    feeds = load_feeds()
    feeds.append(feed_data)
    save_feeds(feeds)

    return redirect(url_for('index'))

@app.route('/delete_feed/<int:feed_id>', methods=['POST'])
def delete_feed(feed_id):
    feeds = load_feeds()
    if 0 <= feed_id < len(feeds):
        feeds.pop(feed_id)
        save_feeds(feeds)
    return redirect(url_for('index'))

@app.route('/refresh_feeds', methods=['POST'])
def refresh_feeds():
    feeds = load_feeds()
    indicators = []

    for feed in feeds:
        try:
            client = TAXIIClient(
                feed['url'],
                feed['collection'],
                feed.get('username'),
                feed.get('password')
            )
            indicators.extend(client.get_indicators())
        except Exception as e:
            print(f"Error fetching from {feed['name']}: {str(e)}")

    save_indicators(indicators)
    return jsonify({'success': True, 'count': len(indicators)})

@app.route("/discover_collections", methods=["POST"])
def discover_collections():
    server_url = request.form.get("server_url")
    username = request.form.get("username")
    password = request.form.get("password")

    try:
        client = TAXIIClient(server_url, None, username, password)
        collections = client.discover_collections()
        return jsonify({"success": True, "collections": collections})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('q', '').lower()
    type_filter = request.args.get('type', '').lower()

    indicators = load_indicators()

    if query or type_filter:
        filtered = []
        for indicator in indicators:
            matches_query = not query or (
                    query in indicator.get('value', '').lower() or
                    query in indicator.get('description', '').lower() or
                    query in indicator.get('type', '').lower()
            )
            matches_type = not type_filter or type_filter in indicator.get('type', '').lower()

            if matches_query and matches_type:
                filtered.append(indicator)
        indicators = filtered

    return render_template('index.html', feeds=load_feeds(), indicators=indicators)

if __name__ == '__main__':
    app.run(debug=True)
