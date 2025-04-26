/**
 * Feed manager handles displaying and interacting with articles
 */
const FeedManager = {
    // State
    articles: [],
    currentOffset: 0,
    currentLimit: 20,
    isLoading: false,
    hasMoreArticles: true,
    currentFeedId: null,
    unreadOnly: false,
    readTrackingObserver: null,
    autoReadEnabled: true,
    
    // DOM Elements
    articlesContainer: null,
    loadingIndicator: null,
    loadMoreButton: null,
    loadMoreContainer: null,
    feedFilterSelect: null,
    unreadFilterCheckbox: null,
    autoReadSetting: null,

    similarArticleOffsets: {}, // Track offsets for each article's similar articles
    similarBatchSize: 3,      // Number of similar articles to load per batch
    
    /**
     * Initialize the feed manager
     */
    init() {
        // Get DOM elements
        this.articlesContainer = document.getElementById('articles-container');
        this.loadingIndicator = document.getElementById('loading-indicator');
        this.loadMoreButton = document.getElementById('load-more-button');
        this.loadMoreContainer = document.getElementById('load-more-container');
        this.feedFilterSelect = document.getElementById('feed-filter');
        this.unreadFilterCheckbox = document.getElementById('unread-filter');
        this.autoReadSetting = document.getElementById('auto-read-setting');
        
        // Load auto-read setting from server (with localStorage fallback for compatibility)
        this.loadAutoReadSetting();
        
        // Add event listeners
        this.loadMoreButton.addEventListener('click', () => this.loadMoreArticles());
        this.feedFilterSelect.addEventListener('change', () => this.handleFilterChange());
        this.unreadFilterCheckbox.addEventListener('change', () => this.handleFilterChange());
        
        // Add auto-read setting event listener if the element exists
        if (this.autoReadSetting) {
            this.autoReadSetting.addEventListener('change', () => {
                this.autoReadEnabled = this.autoReadSetting.checked;
                
                // Save to server
                API.updateSetting('auto_read', this.autoReadEnabled ? 'true' : 'false')
                    .catch(error => console.error('Error saving auto-read setting:', error));
                
                if (this.autoReadEnabled) {
                    this.setupAutoReadTracking();
                } else if (this.readTrackingObserver) {
                    this.readTrackingObserver.disconnect();
                    this.readTrackingObserver = null;
                }
            });
        }
        
        // Set up intersection observer for lazy loading
        this.setupLazyLoading();
        
        // Set up auto-read tracking if enabled (will be done after loading setting)
        
        // Load feeds for the filter dropdown
        this.loadFeedsForFilter();
        
        // Load initial articles
        this.loadArticles();
    },
    
    /**
     * Load auto-read setting from server
     */
    async loadAutoReadSetting() {
        try {
            // Try to get the setting from the server
            const response = await API.getSetting('auto_read');
            this.autoReadEnabled = response.value === 'true';
        } catch (error) {
            console.error('Error loading auto-read setting, using fallback:', error);
            // Fallback to localStorage for compatibility with existing users
            const savedAutoReadPref = localStorage.getItem('autoReadEnabled');
            if (savedAutoReadPref !== null) {
                this.autoReadEnabled = savedAutoReadPref === 'true';
                
                // Save this to the server for future use
                API.updateSetting('auto_read', this.autoReadEnabled ? 'true' : 'false')
                    .catch(error => console.error('Error saving auto-read fallback setting:', error));
            }
        } finally {
            // Update the UI checkbox
            if (this.autoReadSetting) {
                this.autoReadSetting.checked = this.autoReadEnabled;
            }
            
            // Set up auto-read tracking if enabled
            if (this.autoReadEnabled) {
                this.setupAutoReadTracking();
            }
        }
    },
    
    /**
     * Set up intersection observer for lazy loading when scrolling
     */
    setupLazyLoading() {
        // Only set up lazy loading if the Intersection Observer API is available
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting && !this.isLoading && this.hasMoreArticles) {
                        this.loadMoreArticles();
                    }
                });
            }, { threshold: 0.5 });
            
            observer.observe(this.loadMoreContainer);
        }
    },
    
    /**
     * Set up intersection observer to mark articles as read when scrolled past
     */
    setupAutoReadTracking() {
        // Only set up if the Intersection Observer API is available
        if ('IntersectionObserver' in window) {
            // Disconnect existing observer if it exists
            if (this.readTrackingObserver) {
                this.readTrackingObserver.disconnect();
            }
            
            // Create an observer that triggers when articles leave the viewport
            this.readTrackingObserver = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    // If article is no longer intersecting (scrolled past) and was previously visible
                    if (!entry.isIntersecting && entry.boundingClientRect.y < 0) {
                        const articleElement = entry.target;
                        const articleId = parseInt(articleElement.dataset.id);
                        const isRead = articleElement.dataset.read === 'true';
                        
                        // Only mark as read if it's not already read
                        if (!isRead) {
                            this.toggleArticleReadStatus(articleId);
                        }
                    }
                });
            }, { threshold: 0 }); // Trigger as soon as article leaves viewport
            
            // Observe all current article elements
            document.querySelectorAll('.article-card').forEach(article => {
                this.readTrackingObserver.observe(article);
            });
        }
    },
    
    /**
     * Load feeds for the filter dropdown
     */
    async loadFeedsForFilter() {
        try {
            const feeds = await API.getFeeds();
            
            // Clear existing options (except "All Feeds")
            while (this.feedFilterSelect.options.length > 1) {
                this.feedFilterSelect.remove(1);
            }
            
            // Add feed options
            feeds.forEach(feed => {
                const option = document.createElement('option');
                option.value = feed.id;
                option.textContent = feed.title;
                this.feedFilterSelect.appendChild(option);
            });
        } catch (error) {
            console.error('Error loading feeds for filter:', error);
            this.showError('Failed to load feeds. Please try refreshing the page.');
        }
    },
    
    /**
     * Handle filter change
     */
    handleFilterChange() {
        // Get updated filter values
        this.currentFeedId = this.feedFilterSelect.value ? parseInt(this.feedFilterSelect.value) : null;
        this.unreadOnly = this.unreadFilterCheckbox.checked;
        
        // Reset and reload
        this.resetFeed();
        this.loadArticles();
    },
    
    /**
     * Reset feed state for new loading
     */
    resetFeed() {
        this.articles = [];
        this.currentOffset = 0;
        this.hasMoreArticles = true;
        this.articlesContainer.innerHTML = '';
        this.articlesContainer.appendChild(this.loadingIndicator);
    },
    
    /**
     * Load articles with current filters
     */
    async loadArticles() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.loadingIndicator.classList.remove('hidden');
        this.loadMoreContainer.hidden = true;
        
        try {
            // Build query parameters
            const params = {
                limit: this.currentLimit,
                offset: this.currentOffset,
                sort_by: 'published_at',
                sort_order: 'DESC'
            };
            
            // Add optional filters
            if (this.currentFeedId) {
                params.feed_id = this.currentFeedId;
            }
            
            if (this.unreadOnly) {
                params.read = false;
            }
            
            // Fetch articles
            const newArticles = await API.getArticles(params);
            
            // Update state
            this.currentOffset += newArticles.length;
            this.hasMoreArticles = newArticles.length === this.currentLimit;
            
            // Remove loading indicator if this is the first batch
            if (this.articles.length === 0) {
                this.articlesContainer.innerHTML = '';
            }
            
            // Append new articles
            newArticles.forEach(article => {
                this.articles.push(article);
                this.renderArticle(article);
            });
            
            // Update UI based on results
            if (this.articles.length === 0) {
                this.showNoArticlesMessage();
            }
            
            // Show load more button if there are more articles
            this.loadMoreContainer.hidden = !this.hasMoreArticles;
            
            // Update unread count in the badge
            this.updateUnreadBadge();
        } catch (error) {
            console.error('Error loading articles:', error);
            this.showError('Failed to load articles. Please try again later.');
        } finally {
            this.isLoading = false;
            this.loadingIndicator.classList.add('hidden');
        }
    },
    
    /**
     * Load more articles
     */
    loadMoreArticles() {
        if (!this.isLoading && this.hasMoreArticles) {
            this.loadArticles();
        }
    },
    
    /**
     * Render an article card
     * @param {Object} article - Article data
     */
    renderArticle(article) {
        // Get the template
        const template = document.getElementById('article-template');
        const articleElement = document.importNode(template.content, true).querySelector('.article-card');
        
        // Set article ID as data attribute
        articleElement.dataset.id = article.id;
        articleElement.dataset.read = article.read.toString();
        
        // Populate the article content
        const title = articleElement.querySelector('.article-title a');
        title.href = article.url;
        title.textContent = article.title;
        
        articleElement.querySelector('.article-feed').textContent = article.feed_title;
        
        // Format date
        const date = new Date(article.published_at * 1000);
        articleElement.querySelector('.article-date').textContent = this.formatDate(date);
        
        // Set summary
        const summary = articleElement.querySelector('.article-summary');
        summary.innerHTML = article.description || '';
        
        // Add image if available - but only if we're not already showing one from the description
        if (article.image_url && !summary.querySelector('img')) {
            this.addImageToArticle(articleElement, article);
        } else if (summary.querySelector('img')) {
            // If there's already an image in the summary, don't add another one
            // But we still want the layout to look good
            articleElement.classList.add('has-image');
        }
        
        // Set read toggle text
        const readToggle = articleElement.querySelector('.read-toggle');
        const readStatusText = readToggle.querySelector('.read-status-text');
        readStatusText.textContent = article.read ? 'Mark as Unread' : 'Mark as Read';
        
        // Set up event listeners
        this.setupArticleEventListeners(articleElement, article);
        
        // Add to container
        this.articlesContainer.appendChild(articleElement);
        
        // Add to read tracking observer if it exists and auto-read is enabled
        if (this.readTrackingObserver && this.autoReadEnabled) {
            this.readTrackingObserver.observe(articleElement);
        }
    },
    
    /**
     * Add image to article element
     * @param {Element} articleElement - Article DOM element
     * @param {Object} article - Article data
     */
    addImageToArticle(articleElement, article) {
        // Only process one image per article (the main one)
        // Get the image container template
        const imageTemplate = document.getElementById('image-container-template');
        const imageContainer = document.importNode(imageTemplate.content, true).querySelector('.article-image-container');
        
        // Get the article content element where we'll insert the image
        const articleContent = articleElement.querySelector('.article-content');
        const summaryContainer = articleElement.querySelector('.article-summary-container');
        
        // Add class to article to indicate it has an image
        articleElement.classList.add('has-image');
        
        // Set the image source
        const image = imageContainer.querySelector('.article-image');
        image.alt = `Image for ${article.title}`;
        
        // Add load and error event listeners
        image.addEventListener('load', () => {
            image.classList.remove('loading');
            image.classList.add('loaded');
        });
        
        image.addEventListener('error', () => {
            // Simply hide the image container on error
            imageContainer.style.display = 'none';
        });
        
        // Add the image container after the summary container (right side)
        articleContent.appendChild(imageContainer);
        
        // Set the image source last to trigger loading
        image.src = article.image_url;
    },
    
    /**
     * Set up event listeners for an article card
     * @param {Element} articleElement - Article DOM element
     * @param {Object} article - Article data
     */
    setupArticleEventListeners(articleElement, article) {
        // Read toggle
        const readToggle = articleElement.querySelector('.read-toggle');
        readToggle.addEventListener('click', (e) => {
            e.preventDefault();
            this.toggleArticleReadStatus(article.id);
        });
        
        // Similar articles button
        const similarButton = articleElement.querySelector('.similar-button');
        if (similarButton) {
            similarButton.addEventListener('click', (e) => {
                e.preventDefault();
                this.toggleSimilarArticles(article.id, similarButton);
            });
        }
        
        // Like button
        const likeButton = articleElement.querySelector('.feedback-button.like');
        likeButton.addEventListener('click', (e) => {
            e.preventDefault();
            this.recordArticleFeedback(article.id, true, likeButton, articleElement.querySelector('.feedback-button.dislike'));
        });
        
        // Dislike button
        const dislikeButton = articleElement.querySelector('.feedback-button.dislike');
        dislikeButton.addEventListener('click', (e) => {
            e.preventDefault();
            this.recordArticleFeedback(article.id, false, dislikeButton, articleElement.querySelector('.feedback-button.like'));
        });
        
        // Track article link clicks
        this.setupLinkClickTracking(articleElement, article);
    },
    
    /**
     * Set up article link click tracking
     * @param {Element} articleElement - Article DOM element
     * @param {Object} article - Article data
     */
    setupLinkClickTracking(articleElement, article) {
        const titleLink = articleElement.querySelector('.article-title a');
        if (titleLink) {
            titleLink.addEventListener('click', (e) => {
                // Don't prevent default - we want the link to work normally
                // Just track the click in the background
                this.trackArticleClick(article.id, titleLink);
            });
        }
    },
    
    /**
     * Track article link click
     * @param {number} articleId - Article ID
     * @param {Element} linkElement - The link element that was clicked
     */
    async trackArticleClick(articleId, linkElement) {
        try {
            // Record the click event in the background
            // We don't want to delay the user's navigation, so we don't await this
            API.recordClick(articleId)
                .catch(error => console.error('Error recording click:', error));
            
            // We don't return anything because we want the default link behavior to continue
        } catch (error) {
            console.error('Error in click tracking:', error);
            // Still allow the link navigation to proceed even if tracking fails
        }
    },
    
    /**
     * Toggle article read status
     * @param {number} articleId - Article ID
     */
    async toggleArticleReadStatus(articleId) {
        try {
            // Find the article in our data
            const articleIndex = this.articles.findIndex(a => a.id === articleId);
            if (articleIndex === -1) return;
            
            const article = this.articles[articleIndex];
            const newReadStatus = !article.read;
            
            // Update the UI immediately for responsiveness
            const articleElement = this.articlesContainer.querySelector(`.article-card[data-id="${articleId}"]`);
            if (articleElement) {
                articleElement.dataset.read = newReadStatus.toString();
                const readStatusText = articleElement.querySelector('.read-status-text');
                readStatusText.textContent = newReadStatus ? 'Mark as Unread' : 'Mark as Read';
            }
            
            // Update the article in our data
            article.read = newReadStatus;
            
            // Send the update to the server
            await API.markArticleRead(articleId, newReadStatus);
            
            // If filter is set to unread only and we just marked it as read, remove the article
            if (this.unreadOnly && newReadStatus && articleElement) {
                // Use animation if supported
                if ('animate' in articleElement) {
                    const animation = articleElement.animate([
                        { opacity: 1, transform: 'translateX(0)' },
                        { opacity: 0, transform: 'translateX(-100%)' }
                    ], { duration: 300 });
                    
                    animation.onfinish = () => articleElement.remove();
                } else {
                    articleElement.remove();
                }
                
                // Remove from our data array
                this.articles.splice(articleIndex, 1);
            }
            
            // Update unread count
            this.updateUnreadBadge();
        } catch (error) {
            console.error('Error toggling read status:', error);
            // Revert UI changes on error
            this.showError('Failed to update article status. Please try again.');
        }
    },
    
    /**
     * Record feedback for an article
     * @param {number} articleId - Article ID
     * @param {boolean} positive - Whether feedback is positive
     * @param {Element} activeButton - Button that was clicked
     * @param {Element} inactiveButton - Other feedback button
     */
    async recordArticleFeedback(articleId, positive, activeButton, inactiveButton) {
        try {
            // Toggle active state of buttons
            const isAlreadyActive = activeButton.classList.contains('active');
            
            // Reset both buttons
            activeButton.classList.remove('active');
            inactiveButton.classList.remove('active');
            
            // If it wasn't already active, set it as active and send feedback
            if (!isAlreadyActive) {
                activeButton.classList.add('active');
                await API.recordFeedback(articleId, positive);
            }
        } catch (error) {
            console.error('Error recording feedback:', error);
            this.showError('Failed to record feedback. Please try again.');
            
            // Reset button states on error
            activeButton.classList.remove('active');
            inactiveButton.classList.remove('active');
        }
    },
    
    /**
     * Update the unread count badge
     */
    updateUnreadBadge() {
        const unreadCount = this.articles.filter(article => !article.read).length;
        const badge = document.getElementById('unread-count');
        
        if (unreadCount > 0) {
            badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    },
    
    /**
     * Format a date for display
     * @param {Date} date - Date object
     * @returns {string} - Formatted date string
     */
    formatDate(date) {
        // Use relative time when possible
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);
        
        if (diffSec < 60) {
            return 'just now';
        } else if (diffMin < 60) {
            return `${diffMin}m ago`;
        } else if (diffHour < 24) {
            return `${diffHour}h ago`;
        } else if (diffDay < 7) {
            return `${diffDay}d ago`;
        } else {
            // Fall back to date string for older articles
            return date.toLocaleDateString(undefined, { 
                year: 'numeric', 
                month: 'short', 
                day: 'numeric' 
            });
        }
    },
    
    /**
     * Show an error message
     * @param {string} message - Error message
     */
    showError(message) {
        // Create error element if it doesn't exist
        let errorElement = this.articlesContainer.querySelector('.error-message');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'error-message';
            
            // Only add if we have articles container
            if (this.articlesContainer) {
                this.articlesContainer.prepend(errorElement);
            }
        }
        
        errorElement.textContent = message;
        
        // Auto-hide after 5 seconds
        setTimeout(() => {
            errorElement.remove();
        }, 5000);
    },
    
    /**
     * Show a message when no articles are found
     */
    showNoArticlesMessage() {
        const noArticlesElement = document.createElement('div');
        noArticlesElement.className = 'no-articles-message';
        noArticlesElement.innerHTML = `
            <p>No articles found. Try changing your filters or add more feeds in Settings.</p>
        `;
        this.articlesContainer.appendChild(noArticlesElement);
    },
    
    /**
     * Toggle display of similar articles
     * @param {number} articleId - Article ID
     * @param {Element} button - Button element that was clicked
     */
    async toggleSimilarArticles(articleId, button) {
        const articleElement = button.closest('.article-card');
        const similarContainer = articleElement.querySelector('.similar-articles-container');
        const similarList = similarContainer.querySelector('.similar-articles-list');
        
        // Toggle container visibility
        if (similarContainer.classList.contains('hidden')) {
            // Show container and load articles
            similarContainer.classList.remove('hidden');
            button.classList.add('active');
            
            // Show loading indicator
            similarList.innerHTML = `
                <div class="loading-indicator">
                    <div class="spinner"></div>
                    <p>Loading similar articles...</p>
                </div>
            `;
            
            // Reset offset for this article when opening
            this.similarArticleOffsets[articleId] = 0;
            
            try {
                // Fetch similar articles
                await this.loadMoreSimilarArticles(articleId, similarList);
            } catch (error) {
                console.error('Error loading similar articles:', error);
                similarList.innerHTML = `
                    <div class="error-message">
                        <p>Failed to load similar articles. Please try again.</p>
                    </div>
                `;
            }
        } else {
            // Hide container
            similarContainer.classList.add('hidden');
            button.classList.remove('active');
        }
    },

    /**
     * Render a similar article card
     * @param {Element} container - Container element
     * @param {Object} article - Article data
     */
    renderSimilarArticle(container, article) {
        const similarArticle = document.createElement('div');
        similarArticle.className = 'similar-article-card';
        
        // Add similarity score indicator
        const similarityPercent = Math.round(article.similarity * 100);
        
        similarArticle.innerHTML = `
            <div class="similar-article-header">
                <h4 class="similar-article-title">
                    <a href="${article.url}" target="_blank" rel="noopener noreferrer">${article.title}</a>
                </h4>
                <span class="similarity-score">${similarityPercent}% match</span>
            </div>
            <div class="similar-article-meta">
                <span class="similar-article-feed">${article.feed_title}</span>
                <span class="similar-article-date">${this.formatDate(new Date(article.published_at * 1000))}</span>
            </div>
        `;
        
        container.appendChild(similarArticle);
    },

    /**
     * Load more similar articles
     * @param {number} articleId - Article ID
     * @param {Element} containerElement - Container to add articles to
     */
    async loadMoreSimilarArticles(articleId, containerElement) {
        // Get current offset for this article
        const offset = this.similarArticleOffsets[articleId] || 0;
        
        try {
            // Fetch similar articles with limit and offset
            const similarArticles = await API.getSimilarArticles(articleId, this.similarBatchSize, offset);
            
            // Remove loading indicator if it's the first batch
            if (offset === 0) {
                containerElement.innerHTML = '';
            } else {
                // Remove the "load more" button if it exists
                const loadMoreButton = containerElement.querySelector('.load-more-similar-button');
                if (loadMoreButton) {
                    loadMoreButton.remove();
                }
            }
            
            if (similarArticles.length === 0 && offset === 0) {
                containerElement.innerHTML = `
                    <div class="empty-message">
                        <p>No similar articles found.</p>
                    </div>
                `;
                return;
            }
            
            // Render each similar article
            similarArticles.forEach(article => {
                this.renderSimilarArticle(containerElement, article);
            });
            
            // Update the offset for next batch
            this.similarArticleOffsets[articleId] = offset + similarArticles.length;
            
            // Add "Load More" button if we received the full batch size (indicating there might be more)
            if (similarArticles.length >= this.similarBatchSize) {
                const loadMoreButton = document.createElement('button');
                loadMoreButton.className = 'load-more-similar-button';
                loadMoreButton.textContent = 'More Similar Articles';
                
                // Add click handler
                loadMoreButton.addEventListener('click', async () => {
                    // Replace button with loading indicator
                    loadMoreButton.innerHTML = '<div class="spinner small-spinner"></div> Loading...';
                    loadMoreButton.disabled = true;
                    
                    // Load more articles
                    await this.loadMoreSimilarArticles(articleId, containerElement);
                });
                
                containerElement.appendChild(loadMoreButton);
            }
        } catch (error) {
            console.error('Error loading more similar articles:', error);
            
            // Show error only if it's the first batch
            if (offset === 0) {
                containerElement.innerHTML = `
                    <div class="error-message">
                        <p>Failed to load similar articles. Please try again.</p>
                    </div>
                `;
            } else {
                // Add error message at bottom
                const errorMessage = document.createElement('div');
                errorMessage.className = 'error-message';
                errorMessage.textContent = 'Failed to load more articles.';
                containerElement.appendChild(errorMessage);
                
                // Remove message after 3 seconds
                setTimeout(() => errorMessage.remove(), 3000);
            }
        }
    }
};
