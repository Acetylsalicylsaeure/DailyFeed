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
    
    // DOM Elements
    articlesContainer: null,
    loadingIndicator: null,
    loadMoreButton: null,
    loadMoreContainer: null,
    feedFilterSelect: null,
    unreadFilterCheckbox: null,
    
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
        
        // Add event listeners
        this.loadMoreButton.addEventListener('click', () => this.loadMoreArticles());
        this.feedFilterSelect.addEventListener('change', () => this.handleFilterChange());
        this.unreadFilterCheckbox.addEventListener('change', () => this.handleFilterChange());
        
        // Set up intersection observer for lazy loading
        this.setupLazyLoading();
        
        // Load feeds for the filter dropdown
        this.loadFeedsForFilter();
        
        // Load initial articles
        this.loadArticles();
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
        
        // Set read toggle text
        const readToggle = articleElement.querySelector('.read-toggle');
        const readStatusText = readToggle.querySelector('.read-status-text');
        readStatusText.textContent = article.read ? 'Mark as Unread' : 'Mark as Read';
        
        // Set up event listeners
        this.setupArticleEventListeners(articleElement, article);
        
        // Add to container
        this.articlesContainer.appendChild(articleElement);
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
    }
};
