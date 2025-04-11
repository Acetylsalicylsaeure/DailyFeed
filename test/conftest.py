import os
import sys
import pytest
import tempfile
import sqlite3
from contextlib import closing

# Add the project root to the path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the RSSBackend class
from src.backend.rss_core import RSSBackend


@pytest.fixture
def sample_feed_entry():
    """A sample feed entry with common attributes"""
    class SampleEntry:
        def __init__(self):
            self.id = "entry-unique-id"
            self.title = "Sample Entry Title"
            self.link = "https://example.com/sample-entry"
            self.published = "Fri, 11 Apr 2025 10:00:00 GMT"
            self.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
            self.summary = "This is a summary of the entry"
            self.content = [{'value': '<p>This is the full content of the entry.</p>', 'type': 'html'}]
            self.author = "John Doe"
            
        def get(self, key, default=None):
            return getattr(self, key, default)
    
    return SampleEntry()



@pytest.fixture
def db_path():
    """Create a temporary SQLite database for testing"""
    fd, path = tempfile.mkstemp(suffix='.db')
    yield path
    os.close(fd)
    os.unlink(path)


@pytest.fixture
def rss_backend(db_path):
    """Create a RSSBackend instance with a test database"""
    backend = RSSBackend(db_path=db_path)
    yield backend


@pytest.fixture
def sample_feed_data():
    """Sample feed data structure as returned by feedparser"""
    class FeedData:
        class Feed:
            def __init__(self):
                self.title = "Sample Feed"
                self.description = "A sample feed for testing"
                
        def __init__(self):
            self.feed = self.Feed()
            self.entries = []
            
            # Add a sample entry
            class Entry:
                def __init__(self):
                    self.id = "entry1"
                    self.title = "Entry 1"
                    self.link = "https://example.com/entry1"
                    self.summary = "Summary of entry 1"
                    self.content = [{'value': '<p>Content of entry 1</p>', 'type': 'html'}]
                    self.published = "Fri, 11 Apr 2025 10:00:00 GMT"
                    self.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
                    self.author = "Author 1"
            
            self.entries.append(Entry())
            
            # Add another entry with different date format
            class Entry2:
                def __init__(self):
                    self.id = "entry2"
                    self.title = "Entry 2"
                    self.link = "https://example.com/entry2"
                    self.summary = "Summary of entry 2"
                    self.content = [{'value': '<p>Content of entry 2</p>', 'type': 'html'}]
                    self.updated = "2025-04-11T11:00:00Z"  # ISO format
                    self.updated_parsed = (2025, 4, 11, 11, 0, 0, 0, 0, 0)
                    self.author = "Author 2"
            
            self.entries.append(Entry2())
    
    return FeedData()


@pytest.fixture
def db_with_feed(rss_backend, db_path):
    """Set up a database with a feed for testing"""
    with closing(sqlite3.connect(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO feeds (title, url, description) VALUES (?, ?, ?)',
            ('Test Feed', 'https://example.com/feed', 'A test feed')
        )
        feed_id = cursor.lastrowid
        
        cursor.execute(
            '''INSERT INTO articles 
               (feed_id, guid, title, url, description, content, author, published_at, read) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (feed_id, 'article1', 'Article 1', 'https://example.com/article1', 
             'Description 1', 'Content 1', 'Author 1', 1712800000, 0)
        )
        
        cursor.execute(
            '''INSERT INTO articles 
               (feed_id, guid, title, url, description, content, author, published_at, read) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (feed_id, 'article2', 'Article 2', 'https://example.com/article2', 
             'Description 2', 'Content 2', 'Author 2', 1712900000, 1)
        )
        
        conn.commit()
    
    return rss_backend, feed_id


@pytest.fixture
def mock_feedparser(monkeypatch):
    """Mock the feedparser.parse function to return sample data"""
    def mock_parse(url, **kwargs):
        mock_feed = MagicMock()
        
        # Configure the feed object correctly
        class Feed:
            def __init__(self):
                self.title = "Sample Feed"
                self.description = "A sample feed for testing"
            
            def get(self, key, default=None):
                return getattr(self, key, default)
                
        mock_feed.feed = Feed()
        
        # Configure entries
        class Entry1:
            def __init__(self):
                self.id = "entry1"
                self.title = "Sample Entry"
                self.link = "https://example.com/entry1"
                self.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
                self.summary = "Summary text"
                
            def get(self, key, default=None):
                return getattr(self, key, default)
                
        class Entry2:
            def __init__(self):
                self.id = "entry2"
                self.title = "Another Entry"
                self.link = "https://example.com/entry2"
                self.published_parsed = (2025, 4, 10, 10, 0, 0, 0, 0, 0)
                self.summary = "Another summary"
                
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        # Use custom classes instead of MagicMock to have better control
        mock_feed.entries = [Entry1(), Entry2()]
        
        # Handle bozo exception correctly
        mock_feed.bozo = False
        
        return mock_feed
    
    monkeypatch.setattr('feedparser.parse', mock_parse)
    return mock_parse
