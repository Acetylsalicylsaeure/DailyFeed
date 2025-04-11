import pytest
import os
import tempfile
import time
from unittest.mock import patch, MagicMock

from src.backend.rss_core import RSSBackend


class TestEndToEnd:
    """End-to-end integration tests"""
    
    @patch('feedparser.parse')
    def test_full_workflow(self, mock_parse, db_path):
        """Test the full workflow from adding a feed to reading articles"""
        # Setup mock feed data
        feed1 = MagicMock()
        feed1.feed.title = "Feed One"
        feed1.feed.description = "First test feed"
        
        entry1 = MagicMock()
        entry1.id = "entry1"
        entry1.title = "Article One"
        entry1.link = "https://example.com/article1"
        entry1.summary = "Summary of article one"
        entry1.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
        
        entry2 = MagicMock()
        entry2.id = "entry2"
        entry2.title = "Article Two"
        entry2.link = "https://example.com/article2"
        entry2.content = [{'value': '<p>Content of article two</p>', 'type': 'html'}]
        entry2.published_parsed = (2025, 4, 10, 10, 0, 0, 0, 0, 0)
        
        feed1.entries = [entry1, entry2]
        
        # Setup mock feed data for a second feed
        feed2 = MagicMock()
        feed2.feed.title = "Feed Two"
        feed2.feed.description = "Second test feed"
        
        entry3 = MagicMock()
        entry3.id = "entry3"
        entry3.title = "Article Three"
        entry3.link = "https://example.com/article3"
        entry3.summary = "Summary of article three"
        entry3.published_parsed = (2025, 4, 9, 10, 0, 0, 0, 0, 0)
        
        feed2.entries = [entry3]
        
        # Configure the mock to return different data for different URLs
        def mock_parse_function(url, **kwargs):
            if url == "https://example.com/feed1":
                return feed1
            elif url == "https://example.com/feed2":
                return feed2
            else:
                # Default empty feed
                empty_feed = MagicMock()
                empty_feed.feed.title = "Empty Feed"
                empty_feed.entries = []
                return empty_feed
        
        mock_parse.side_effect = mock_parse_function
        
        # Create a backend with the test database
        backend = RSSBackend(db_path=db_path)
        
        # Step 1: Add feeds
        success1, message1 = backend.add_feed("https://example.com/feed1")
        assert success1 is True
        
        success2, message2 = backend.add_feed("https://example.com/feed2")
        assert success2 is True
        
        # Step 2: Verify feeds were added
        feeds = backend.get_feeds()
        assert len(feeds) == 2
        assert feeds[0]['title'] == "Feed One"
        assert feeds[1]['title'] == "Feed Two"
        
        # Step 3: Verify articles were fetched
        articles = backend.get_articles()
        assert len(articles) == 3
        # Articles should be sorted by published_at DESC by default
        assert articles[0]['title'] == "Article One"
        assert articles[1]['title'] == "Article Two"
        assert articles[2]['title'] == "Article Three"
        
        # Step 4: Mark an article as read
        article_id = articles[0]['id']
        success = backend.mark_article_read(article_id, True)
        assert success is True
        
        # Step 5: Verify read status
        read_articles = backend.get_articles(read=True)
        assert len(read_articles) == 1
        assert read_articles[0]['id'] == article_id
        
        unread_articles = backend.get_articles(read=False)
        assert len(unread_articles) == 2
        
        # Step 6: Record feedback
        success = backend.record_feedback(article_id, True)
        assert success is True
        
        # Step 7: Filter by feed
        feed_id = feeds[0]['id']
        feed1_articles = backend.get_articles(feed_id=feed_id)
        assert len(feed1_articles) == 2
        assert all(a['feed_id'] == feed_id for a in feed1_articles)
        
        # Step 8: Remove a feed
        success = backend.remove_feed(feed_id)
        assert success is True
        
        # Step 9: Verify feed and its articles are gone
        feeds = backend.get_feeds()
        assert len(feeds) == 1
        assert feeds[0]['title'] == "Feed Two"
        
        articles = backend.get_articles()
        assert len(articles) == 1
        assert articles[0]['title'] == "Article Three"
    
    @pytest.mark.skipif(os.environ.get('SKIP_LIVE_TESTS', 'True') == 'True',
                     reason="Skip live tests by default")
    def test_real_feed_parsing(self, db_path):
        """Test parsing a real feed (optional, requires internet)"""
        # This test uses a real feed, so we only run it when explicitly enabled
        
        # Create a backend with the test database
        backend = RSSBackend(db_path=db_path)
        
        # Add a real feed (NASA news)
        success, message = backend.add_feed("https://www.nasa.gov/feed/")
        
        # If the test is enabled but the feed is unreachable, skip it
        if not success:
            pytest.skip(f"Could not access the live feed: {message}")
        
        # Verify feed was added
        feeds = backend.get_feeds()
        assert len(feeds) == 1
        assert "NASA" in feeds[0]['title']
        
        # Verify articles were fetched
        articles = backend.get_articles()
        assert len(articles) > 0
        
        # Check that we have expected article fields
        article = articles[0]
        assert article['title']
        assert article['url']
        assert article['published_at']
