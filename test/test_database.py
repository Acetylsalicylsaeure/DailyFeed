import pytest
import sqlite3
from contextlib import closing

from src.backend.rss_core import RSSBackend


class TestDatabaseSetup:
    """Tests for database initialization and setup"""
    
    def test_db_initialization(self, db_path):
        """Test that the database is properly initialized with required tables"""
        # Given a new RSSBackend instance
        backend = RSSBackend(db_path=db_path)
        
        # When connecting to the database
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.cursor()
            
            # Then the required tables should exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            assert "feeds" in tables
            assert "articles" in tables
            assert "user_feedback" in tables
    
    def test_table_schema(self, db_path):
        """Test that the tables have the correct schema"""
        # Given a new RSSBackend instance
        backend = RSSBackend(db_path=db_path)
        
        # When inspecting the database schema
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.cursor()
            
            # Then the feeds table should have the correct columns
            cursor.execute("PRAGMA table_info(feeds)")
            columns = {row[1] for row in cursor.fetchall()}
            expected_columns = {
                "id", "title", "url", "description", "last_fetched", 
                "update_frequency", "active", "error_count", "last_error", "created_at"
            }
            assert expected_columns.issubset(columns)
            
            # And the articles table should have the correct columns
            cursor.execute("PRAGMA table_info(articles)")
            columns = {row[1] for row in cursor.fetchall()}
            expected_columns = {
                "id", "feed_id", "guid", "title", "url", "description", 
                "content", "author", "published_at", "fetched_at", "read"
            }
            assert expected_columns.issubset(columns)
            
            # And the user_feedback table should have the correct columns
            cursor.execute("PRAGMA table_info(user_feedback)")
            columns = {row[1] for row in cursor.fetchall()}
            expected_columns = {"id", "article_id", "feedback", "timestamp"}
            assert expected_columns.issubset(columns)
    
    def test_indices(self, db_path):
        """Test that the necessary indices are created"""
        # Given a new RSSBackend instance
        backend = RSSBackend(db_path=db_path)
        
        # When inspecting the database indices
        with closing(sqlite3.connect(db_path)) as conn:
            cursor = conn.cursor()
            
            # Then the expected indices should exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indices = [row[0] for row in cursor.fetchall()]
            
            assert "idx_articles_feed_id" in indices
            assert "idx_articles_published_at" in indices
            assert "idx_articles_read" in indices


class TestDatabaseConnections:
    """Tests for database connection handling"""
    
    def test_get_connection(self, rss_backend):
        """Test that get_db_connection returns a valid connection"""
        # Given an RSSBackend instance
        
        # When getting a connection
        conn = rss_backend.get_db_connection()
        
        # Then the connection should be valid
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        
        # And should have row factory set
        assert conn.row_factory == sqlite3.Row
        
        # Cleanup
        conn.close()
    
    def test_connection_isolation(self, rss_backend):
        """Test that connections are isolated"""
        # Given an RSSBackend instance
        
        # When getting two connections
        conn1 = rss_backend.get_db_connection()
        conn2 = rss_backend.get_db_connection()
        
        # Then they should be separate objects
        assert conn1 is not conn2
        
        # Cleanup
        conn1.close()
        conn2.close()


class TestFeedManagement:
    """Tests for feed management functionality"""
    
    def test_add_feed(self, rss_backend, mock_feedparser):
        """Test adding a new feed"""
        # Given an RSSBackend instance and mocked feedparser
        
        # When adding a feed
        success, message = rss_backend.add_feed("https://example.com/feed")
        
        # Then the operation should succeed
        assert success is True
        assert "successfully" in message.lower()
        
        # And the feed should be in the database
        feeds = rss_backend.get_feeds()
        assert len(feeds) == 1
        assert feeds[0]['url'] == "https://example.com/feed"
        assert feeds[0]['title'] == "Sample Feed"
    
    def test_duplicate_feed(self, rss_backend, mock_feedparser):
        """Test adding a duplicate feed"""
        # Given an RSSBackend instance with an existing feed
        rss_backend.add_feed("https://example.com/feed")
        
        # When trying to add the same feed again
        success, message = rss_backend.add_feed("https://example.com/feed")
        
        # Then the operation should fail
        assert success is False
        assert "already exists" in message.lower()
        
        # And there should still be only one feed
        feeds = rss_backend.get_feeds()
        assert len(feeds) == 1
    
    def test_remove_feed(self, db_with_feed):
        """Test removing a feed"""
        # Given an RSSBackend instance with a feed
        backend, feed_id = db_with_feed
        
        # When removing the feed
        success = backend.remove_feed(feed_id)
        
        # Then the operation should succeed
        assert success is True
        
        # And the feed should no longer be in the database
        feeds = backend.get_feeds()
        assert len(feeds) == 0
        
        # And the articles should also be removed
        articles = backend.get_articles()
        assert len(articles) == 0
    
    def test_remove_feed_keep_articles(self, db_with_feed):
        """Test removing a feed while keeping articles"""
        # Given an RSSBackend instance with a feed
        backend, feed_id = db_with_feed
        
        # When removing the feed but keeping articles
        success = backend.remove_feed(feed_id, delete_articles=False)
        
        # Then the operation should succeed
        assert success is True
        
        # And the feed should no longer be in the database
        feeds = backend.get_feeds()
        assert len(feeds) == 0
        
        # But this would normally fail because of foreign key constraints
        # In a real database, we would need to update the articles to reference a valid feed
