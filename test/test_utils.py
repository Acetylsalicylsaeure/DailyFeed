import pytest
from datetime import datetime
import time

from src.backend.rss_core import (
    extract_published_date,
    extract_content,
    generate_guid,
    clean_html
)


class TestExtractPublishedDate:
    """Tests for the extract_published_date utility function"""
    
    def test_with_published_parsed(self, sample_feed_entry):
        """Test extracting date from published_parsed field"""
        # Given a feed entry with published_parsed
        expected_timestamp = time.mktime(sample_feed_entry.published_parsed)
        
        # When extracting the date
        result = extract_published_date(sample_feed_entry)
        
        # Then the correct timestamp is returned
        assert result == expected_timestamp
    
    def test_with_string_date(self):
        """Test extracting date from string date field"""
        # Given a feed entry with only string date
        class Entry:
            def __init__(self):
                self.published = "Fri, 11 Apr 2025 10:00:00 GMT"
        
        entry = Entry()
        
        # When extracting the date
        result = extract_published_date(entry)
        
        # Then a valid timestamp is returned
        assert result is not None
        assert isinstance(result, float)
        # Convert back to date string for comparison (ignoring time zone)
        date_str = datetime.fromtimestamp(result).strftime("%a, %d %b %Y %H:%M:%S")
        assert "11 Apr 2025" in date_str
    
    def test_with_iso_date(self):
        """Test extracting date from ISO format date string"""
        # Given a feed entry with ISO date
        class Entry:
            def __init__(self):
                self.updated = "2025-04-11T10:00:00Z"
        
        entry = Entry()
        
        # When extracting the date
        result = extract_published_date(entry)
        
        # Then a valid timestamp is returned
        assert result is not None
        assert isinstance(result, float)
        # Convert back to ISO format for comparison
        date_str = datetime.fromtimestamp(result).strftime("%Y-%m-%d")
        assert date_str == "2025-04-11"
    
    def test_with_no_date(self):
        """Test extracting date when no date field is present"""
        # Given a feed entry with no date field
        class Entry:
            def __init__(self):
                self.title = "No date here"
        
        entry = Entry()
        
        # When extracting the date
        result = extract_published_date(entry)
        
        # Then None is returned
        assert result is None
    
    def test_with_alternate_date_fields(self):
        """Test extracting date from alternate date fields"""
        # Test with 'created' field
        class Entry1:
            def __init__(self):
                self.created = "Fri, 11 Apr 2025 10:00:00 GMT"
        
        assert extract_published_date(Entry1()) is not None
        
        # Test with 'modified' field
        class Entry2:
            def __init__(self):
                self.modified = "Fri, 11 Apr 2025 10:00:00 GMT"
        
        assert extract_published_date(Entry2()) is not None
        
        # Test with 'date' field
        class Entry3:
            def __init__(self):
                self.date = "Fri, 11 Apr 2025 10:00:00 GMT"
        
        assert extract_published_date(Entry3()) is not None


class TestExtractContent:
    """Tests for the extract_content utility function"""
    
    def test_extract_from_content_list(self, sample_feed_entry):
        """Test extracting content from content list (Atom format)"""
        # Given a feed entry with content as list
        # When extracting content
        result = extract_content(sample_feed_entry)
        
        # Then content is extracted correctly
        assert result == '<p>This is the full content of the entry.</p>'
    
    def test_extract_from_content_encoded(self):
        """Test extracting content from content_encoded field (RSS format)"""
        # Given a feed entry with content_encoded
        class Entry:
            def __init__(self):
                self.content_encoded = "<p>RSS content encoded</p>"
        
        entry = Entry()
        
        # When extracting content
        result = extract_content(entry)
        
        # Then content is extracted correctly
        assert result == "<p>RSS content encoded</p>"
    
    def test_extract_from_summary(self):
        """Test extracting content from summary field"""
        # Given a feed entry with only summary
        class Entry:
            def __init__(self):
                self.summary = "Summary text"
        
        entry = Entry()
        
        # When extracting content
        result = extract_content(entry)
        
        # Then summary is used as content
        assert result == "Summary text"
    
    def test_extract_from_description(self):
        """Test extracting content from description field"""
        # Given a feed entry with only description
        class Entry:
            def __init__(self):
                self.description = "Description text"
        
        entry = Entry()
        
        # When extracting content
        result = extract_content(entry)
        
        # Then description is used as content
        assert result == "Description text"
    
    def test_extract_with_no_content(self):
        """Test extracting content when no content field is present"""
        # Given a feed entry with no content
        class Entry:
            def __init__(self):
                self.title = "No content"
        
        entry = Entry()
        
        # When extracting content
        result = extract_content(entry)
        
        # Then empty string is returned
        assert result == ""


class TestGenerateGuid:
    """Tests for the generate_guid utility function"""
    
    def test_generate_from_id(self, sample_feed_entry):
        """Test generating GUID from entry ID"""
        # Given a feed entry with ID
        # When generating GUID
        result = generate_guid(sample_feed_entry)
        
        # Then ID is used as GUID
        assert result == sample_feed_entry.id
    
    def test_generate_from_link(self):
        """Test generating GUID from link when ID is not present"""
        # Given a feed entry with link but no ID
        class Entry:
            def __init__(self):
                self.link = "https://example.com/entry"
                
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        entry = Entry()
        
        # When generating GUID
        result = generate_guid(entry)
        
        # Then link is used as GUID
        assert result == entry.link
    
    def test_generate_hash_fallback(self):
        """Test generating GUID hash when neither ID nor link is present"""
        # Given a feed entry with neither ID nor link
        class Entry:
            def __init__(self):
                self.title = "Test Entry"
                
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        entry = Entry()
        
        # When generating GUID
        result = generate_guid(entry)
        
        # Then a hash is generated
        assert len(result) == 32  # MD5 hash length
        assert all(c in "0123456789abcdef" for c in result)  # Valid hexadecimal
    
    def test_guid_consistency(self):
        """Test that generated GUIDs are consistent for the same content"""
        # Given two identical entries
        class Entry:
            def __init__(self):
                self.title = "Test Entry"
                self.summary = "Test summary"
                
            def get(self, key, default=None):
                return getattr(self, key, default)
        
        entry1 = Entry()
        entry2 = Entry()
        
        # When generating GUIDs
        guid1 = generate_guid(entry1)
        guid2 = generate_guid(entry2)
        
        # Then they should be identical
        assert guid1 == guid2

class TestCleanHtml:
    """Tests for the clean_html utility function"""
    
    def test_clean_cdata(self):
        """Test cleaning CDATA sections"""
        # Given HTML with CDATA
        html = "<![CDATA[<p>CDATA content</p>]]>"
        
        # When cleaning
        result = clean_html(html)
        
        # Then CDATA wrapper is removed
        assert result == "<p>CDATA content</p>"
    
    def test_clean_scripts(self):
        """Test removing script tags"""
        # Given HTML with script
        html = "<p>Safe content</p><script>alert('dangerous')</script>"
        
        # When cleaning
        result = clean_html(html)
        
        # Then script is removed
        assert result == "<p>Safe content</p>"
    
    def test_clean_empty(self):
        """Test cleaning empty content"""
        # Given empty or None content
        # When cleaning
        result1 = clean_html("")
        result2 = clean_html(None)
        
        # Then empty string is returned
        assert result1 == ""
        assert result2 == ""
    
    def test_clean_whitespace(self):
        """Test cleaning whitespace"""
        # Given content with extra whitespace
        html = "  content  "
        
        # When cleaning
        result = clean_html(html)
        
        # Then whitespace is trimmed
        assert result == "content"
    
    def test_nested_cdata(self):
        """Test cleaning nested CDATA sections"""
        # Given HTML with nested CDATA
        html = "<![CDATA[<p>Outer <![CDATA[Inner]]></p>]]>"
        
        # When cleaning
        result = clean_html(html)
        
        # Then CDATA wrappers are removed
        assert "<![CDATA[" not in result
        assert "]]>" not in result
        assert "<p>Outer Inner</p>" in result
