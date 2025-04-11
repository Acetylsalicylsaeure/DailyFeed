import pytest
from unittest.mock import patch, MagicMock
import feedparser

from src.backend.rss_core import RSSBackend


class TestFeedParsing:
    """Tests for feed parsing functionality"""
    
    def test_fetch_feed_articles(self, rss_backend, mock_feedparser):
        """Test fetching articles from a feed"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # First add the feed to the database
        rss_backend.add_feed(feed_url)
        
        # When fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then articles should be added
        assert new_articles == 2  # Two entries in our mock feed
        
        # And articles should be in the database
        articles = rss_backend.get_articles()
        assert len(articles) == 2
        
        # Verify article contents
        assert articles[0]['title'] == "Entry 2"  # Most recent first due to sorting
        assert articles[1]['title'] == "Entry 1"
    
    def test_fetch_all_feeds(self, rss_backend, mock_feedparser):
        """Test fetching all feeds"""
        # Given an RSSBackend instance with multiple feeds
        rss_backend.add_feed("https://example.com/feed1")
        rss_backend.add_feed("https://example.com/feed2")
        
        # When fetching all feeds
        with patch('src.backend.rss_core.RSSBackend.fetch_feed_articles') as mock_fetch:
            mock_fetch.return_value = 2
            rss_backend.fetch_all_feeds()
        
        # Then fetch_feed_articles should be called for each feed
        assert mock_fetch.call_count == 2
    
    def test_fetch_nonexistent_feed(self, rss_backend):
        """Test fetching articles from a nonexistent feed"""
        # Given an RSSBackend instance and a nonexistent feed URL
        feed_url = "https://example.com/nonexistent"
        
        # When fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then no articles should be added
        assert new_articles == 0
    
    @patch('feedparser.parse')
    def test_fetch_feed_error(self, mock_parse, rss_backend):
        """Test handling errors when fetching a feed"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When feedparser raises an exception
        mock_parse.side_effect = Exception("Connection error")
        
        # And fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then no articles should be added
        assert new_articles == 0
        
        # And the error should be recorded in the database
        with patch('feedparser.parse') as temp_mock:
            temp_mock.return_value = MagicMock()
            feeds = rss_backend.get_feeds()
            assert len(feeds) == 1
            assert feeds[0]['error_count'] == 1
            assert "Connection error" in feeds[0]['last_error']
    
    @patch('feedparser.parse')
    def test_bozo_detection(self, mock_parse, rss_backend):
        """Test handling bozo exception in feedparser"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When feedparser returns a bozo exception
        sample_feed = MagicMock()
        sample_feed.bozo = True
        sample_feed.bozo_exception = Exception("XML parsing error")
        sample_feed.feed.title = "Test Feed"
        sample_feed.entries = []
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        with patch('src.backend.rss_core.logger.warning') as mock_warning:
            new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then the warning should be logged
        mock_warning.assert_called_once()
        assert "XML parsing error" in str(mock_warning.call_args)


class TestArticleProcessing:
    """Tests for article processing functionality"""
    
    @patch('feedparser.parse')
    def test_duplicate_article_handling(self, mock_parse, rss_backend):
        """Test handling duplicate articles"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When fetching articles with duplicate GUIDs
        sample_feed = MagicMock()
        sample_feed.feed.title = "Test Feed"
        
        # Create two entries with the same GUID
        entry1 = MagicMock()
        entry1.id = "duplicate-guid"
        entry1.title = "Article 1"
        entry1.link = "https://example.com/article1"
        entry1.summary = "Summary 1"
        entry1.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
        
        entry2 = MagicMock()
        entry2.id = "duplicate-guid"  # Same GUID as entry1
        entry2.title = "Article 2"
        entry2.link = "https://example.com/article2"
        entry2.summary = "Summary 2"
        entry2.published_parsed = (2025, 4, 11, 11, 0, 0, 0, 0, 0)
        
        sample_feed.entries = [entry1, entry2]
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then only one article should be added
        assert new_articles == 1
        
        # And there should be only one article in the database
        articles = rss_backend.get_articles()
        assert len(articles) == 1
        assert articles[0]['guid'] == "duplicate-guid"
    
    @patch('feedparser.parse')
    def test_article_without_dates(self, mock_parse, rss_backend):
        """Test handling articles without dates"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When fetching an article without any date fields
        sample_feed = MagicMock()
        sample_feed.feed.title = "Test Feed"
        
        entry = MagicMock()
        entry.id = "no-date-article"
        entry.title = "Article Without Date"
        entry.link = "https://example.com/no-date-article"
        entry.summary = "This article has no date fields"
        # No date fields
        
        sample_feed.entries = [entry]
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then the article should be added with current date
        assert new_articles == 1
        
        # And the article should have a timestamp
        articles = rss_backend.get_articles()
        assert len(articles) == 1
        assert articles[0]['published_at'] is not None
    
    @patch('feedparser.parse')
    def test_article_without_title(self, mock_parse, rss_backend):
        """Test handling articles without title"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When fetching an article without a title
        sample_feed = MagicMock()
        sample_feed.feed.title = "Test Feed"
        
        entry = MagicMock()
        entry.id = "no-title-article"
        # No title
        entry.link = "https://example.com/no-title-article"
        entry.summary = "This article has no title"
        entry.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
        
        sample_feed.entries = [entry]
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then the article should be added with default title
        assert new_articles == 1
        
        # And the article should have a default title
        articles = rss_backend.get_articles()
        assert len(articles) == 1
        assert articles[0]['title'] == "No title"
    
    @patch('feedparser.parse')
    def test_article_with_cdata(self, mock_parse, rss_backend):
        """Test handling articles with CDATA content"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When fetching an article with CDATA content
        sample_feed = MagicMock()
        sample_feed.feed.title = "Test Feed"
        
        entry = MagicMock()
        entry.id = "cdata-article"
        entry.title = "CDATA Article"
        entry.link = "https://example.com/cdata-article"
        entry.summary = "<![CDATA[<p>This is CDATA content</p>]]>"
        entry.published_parsed = (2025, 4, 11, 10, 0, 0, 0, 0, 0)
        
        sample_feed.entries = [entry]
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        new_articles = rss_backend.fetch_feed_articles(feed_url)
        
        # Then the article should be added with cleaned content
        assert new_articles == 1
        
        # And the article should have cleaned content
        articles = rss_backend.get_articles()
        assert len(articles) == 1
        assert "<![CDATA[" not in articles[0]['description']
        assert "<p>This is CDATA content</p>" in articles[0]['description']


class TestFeedUpdates:
    """Tests for feed update functionality"""
    
    @patch('feedparser.parse')
    def test_feed_title_update(self, mock_parse, rss_backend):
        """Test that feed title is updated when it changes"""
        # Given an RSSBackend instance and a feed URL
        feed_url = "https://example.com/feed"
        
        # And the feed is in the database with initial title
        with patch('feedparser.parse') as temp_mock:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Initial Title"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            temp_mock.return_value = sample_feed
            rss_backend.add_feed(feed_url)
        
        # When the feed title changes
        sample_feed = MagicMock()
        sample_feed.feed.title = "Updated Title"
        sample_feed.entries = []
        mock_parse.return_value = sample_feed
        
        # And fetching articles
        rss_backend.fetch_feed_articles(feed_url)
        
        # Then the feed title should be updated
        feeds = rss_backend.get_feeds()
        assert len(feeds) == 1
        assert feeds[0]['title'] == "Updated Title"
    
    def test_fetch_frequency_respect(self, rss_backend):
        """Test that feed fetch frequency is respected"""
        # Given an RSSBackend instance with a feed
        with patch('feedparser.parse') as mock_parse:
            sample_feed = MagicMock()
            sample_feed.feed.title = "Test Feed"
            sample_feed.feed.description = "Test Description"
            sample_feed.entries = []
            mock_parse.return_value = sample_feed
            rss_backend.add_feed("https://example.com/feed")
        
        # When checking if feeds need to be updated
        with patch('src.backend.rss_core.RSSBackend.fetch_feed_articles') as mock_fetch:
            rss_backend.fetch_all_feeds()
        
        # Then fetch_feed_articles should not be called (feed was just updated)
        assert mock_fetch.call_count == 0
        
        # When setting a past last_fetched time
        import time
        with patch('sqlite3.Connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_cursor
            
            # Update last_fetched to be older than update_frequency
            with patch('src.backend.rss_core.closing') as mock_closing:
                mock_closing.return_value.__enter__.return_value = mock_conn
                
                # Simulate setting a past timestamp
                old_timestamp = time.time() - 7200  # 2 hours ago
                mock_cursor.fetchall.return_value = [
                    {'id': 1, 'url': 'https://example.com/feed', 
                     'last_fetched': old_timestamp, 'update_frequency': 3600}
                ]
                
                # When checking again
                with patch('src.backend.rss_core.RSSBackend.fetch_feed_articles') as mock_fetch:
                    mock_fetch.return_value = 0
                    rss_backend.fetch_all_feeds()
                
                # Then fetch_feed_articles should be called
                assert mock_fetch.call_count == 1

