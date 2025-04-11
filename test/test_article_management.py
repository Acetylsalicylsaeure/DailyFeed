import pytest
from unittest.mock import patch, MagicMock

from src.backend.rss_core import RSSBackend


class TestArticleRetrieval:
    """Tests for article retrieval functionality"""
    
    def test_get_articles_basic(self, db_with_feed):
        """Test basic article retrieval"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles without filters
        articles = backend.get_articles()
        
        # Then all articles should be returned
        assert len(articles) == 2
        # Default sort is by published_at DESC
        assert articles[0]['title'] == 'Article 2'
        assert articles[1]['title'] == 'Article 1'
    
    def test_get_articles_with_limit(self, db_with_feed):
        """Test article retrieval with limit"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles with a limit
        articles = backend.get_articles(limit=1)
        
        # Then only the specified number of articles should be returned
        assert len(articles) == 1
        assert articles[0]['title'] == 'Article 2'  # Most recent first
    
    def test_get_articles_with_offset(self, db_with_feed):
        """Test article retrieval with offset"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles with an offset
        articles = backend.get_articles(offset=1)
        
        # Then articles starting from the offset should be returned
        assert len(articles) == 1
        assert articles[0]['title'] == 'Article 1'  # Second most recent
    
    def test_get_articles_by_feed(self, db_with_feed):
        """Test article retrieval filtered by feed"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles for a specific feed
        articles = backend.get_articles(feed_id=feed_id)
        
        # Then only articles from that feed should be returned
        assert len(articles) == 2
        assert all(article['feed_id'] == feed_id for article in articles)
    
    def test_get_articles_by_read_status(self, db_with_feed):
        """Test article retrieval filtered by read status"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving unread articles
        unread_articles = backend.get_articles(read=False)
        
        # Then only unread articles should be returned
        assert len(unread_articles) == 1
        assert unread_articles[0]['read'] == 0
        assert unread_articles[0]['title'] == 'Article 1'
        
        # When retrieving read articles
        read_articles = backend.get_articles(read=True)
        
        # Then only read articles should be returned
        assert len(read_articles) == 1
        assert read_articles[0]['read'] == 1
        assert read_articles[0]['title'] == 'Article 2'
    
    def test_get_articles_sorting(self, db_with_feed):
        """Test article retrieval with different sorting options"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles sorted by title ascending
        articles = backend.get_articles(sort_by="title", sort_order="ASC")
        
        # Then articles should be sorted correctly
        assert len(articles) == 2
        assert articles[0]['title'] == 'Article 1'
        assert articles[1]['title'] == 'Article 2'
        
        # When retrieving articles sorted by title descending
        articles = backend.get_articles(sort_by="title", sort_order="DESC")
        
        # Then articles should be sorted correctly
        assert len(articles) == 2
        assert articles[0]['title'] == 'Article 2'
        assert articles[1]['title'] == 'Article 1'
    
    def test_get_articles_invalid_sort(self, db_with_feed):
        """Test article retrieval with invalid sort parameter"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When retrieving articles with an invalid sort_by
        articles = backend.get_articles(sort_by="invalid_column")
        
        # Then the default sort should be used
        assert len(articles) == 2
        # Default sort is by published_at DESC
        assert articles[0]['title'] == 'Article 2'
        assert articles[1]['title'] == 'Article 1'


class TestArticleManagement:
    """Tests for article management functionality"""
    
    def test_mark_article_read(self, db_with_feed):
        """Test marking an article as read"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # And an unread article
        articles = backend.get_articles(read=False)
        assert len(articles) == 1
        unread_article_id = articles[0]['id']
        
        # When marking the article as read
        success = backend.mark_article_read(unread_article_id, True)
        
        # Then the operation should succeed
        assert success is True
        
        # And the article should now be marked as read
        articles = backend.get_articles(read=False)
        assert len(articles) == 0
        
        articles = backend.get_articles(read=True)
        assert len(articles) == 2
    
    def test_mark_article_unread(self, db_with_feed):
        """Test marking an article as unread"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # And a read article
        articles = backend.get_articles(read=True)
        assert len(articles) == 1
        read_article_id = articles[0]['id']
        
        # When marking the article as unread
        success = backend.mark_article_read(read_article_id, False)
        
        # Then the operation should succeed
        assert success is True
        
        # And the article should now be marked as unread
        articles = backend.get_articles(read=True)
        assert len(articles) == 0
        
        articles = backend.get_articles(read=False)
        assert len(articles) == 2
    
    def test_mark_nonexistent_article(self, db_with_feed):
        """Test marking a nonexistent article"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When marking a nonexistent article
        success = backend.mark_article_read(999, True)
        
        # Then the operation should fail
        assert success is False
    
    def test_record_feedback(self, db_with_feed):
        """Test recording feedback for an article"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # And an article
        articles = backend.get_articles()
        article_id = articles[0]['id']
        
        # When recording positive feedback
        success = backend.record_feedback(article_id, True)
        
        # Then the operation should succeed
        assert success is True
        
        # When recording negative feedback
        success = backend.record_feedback(article_id, False)
        
        # Then the operation should succeed
        assert success is True
    
    def test_record_feedback_nonexistent_article(self, db_with_feed):
        """Test recording feedback for a nonexistent article"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When recording feedback for a nonexistent article
        success = backend.record_feedback(999, True)
        
        # Then the operation should fail
        assert success is False


class TestStatistics:
    """Tests for statistics functionality"""
    
    def test_get_feed_stats(self, db_with_feed):
        """Test getting feed statistics"""
        # Given an RSSBackend instance with articles
        backend, feed_id = db_with_feed
        
        # When getting statistics
        stats = backend.get_feed_stats()
        
        # Then the statistics should be accurate
        assert stats['total_feeds'] == 1
        assert stats['active_feeds'] == 1
        assert stats['total_articles'] == 2
        assert stats['unread_articles'] == 1
        # We can't reliably test new_articles_24h as it depends on the timestamp
