from stix2 import TAXIICollectionSource, Filter
from taxii2client import Collection, Server
from datetime import datetime, timedelta

class TAXIIClient:
    def __init__(self, server_url=None, collection_name=None, username=None, password=None):
        self.server_url = server_url
        self.collection_name = collection_name
        self.username = username
        self.password = password

    def discover_collections(self):
        """Discover available collections on the TAXII server"""
        if not self.server_url:
            return []

        try:
            server = Server(self.server_url, user=self.username, password=self.password)
            collections = []

            for api_root in server.api_roots:
                for collection in api_root.collections:
                    collections.append({
                        'title': collection.title,
                        'description': collection.description or 'No description',
                        'id': collection.id
                    })

            return collections
        except Exception as e:
            print(f"Error discovering collections: {str(e)}")
            return []

    def get_indicators(self):
        if not self.server_url or not self.collection_name:
            return []

        try:
            # Initialize server and collection
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

                    # Get indicators from the last 7 days
                    last_week = datetime.now() - timedelta(days=7)
                    filt = Filter('last_seen', '>', last_week.strftime('%Y-%m-%dT%H:%M:%SZ'))

                    indicators = tc_source.query([filt])

                    # Convert to simple format for display
                    simple_indicators = []
                    for ind in indicators:
                        simple_indicators.append({
                            'type': ind.type,
                            'value': ind.value if hasattr(ind, 'value') else ind.pattern,
                            'description': ind.description if hasattr(ind, 'description') else '',
                            'last_seen': ind.last_seen if hasattr(ind, 'last_seen') else '',
                            'source': self.collection_name
                        })

                    return simple_indicators
        except Exception as e:
            print(f"Error fetching indicators: {str(e)}")
            return []

        return []
