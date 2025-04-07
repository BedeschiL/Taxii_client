import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-123'
    TAXII_FEEDS_FILE = 'taxii_feeds.json'
    INDICATORS_FILE = 'indicators.json'
