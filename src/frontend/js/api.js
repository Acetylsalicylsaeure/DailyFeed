/**
 * API service for interacting with the backend
 */
const API = {
    /**
     * Base API URL
     */
    baseUrl: '/api',

    /**
     * Make an API request
     * @param {string} endpoint - API endpoint
     * @param {Object} options - Fetch options
     * @returns {Promise<any>} - Response data
     */
    async request(endpoint, options = {}) {
        try {
            const url = `${this.baseUrl}${endpoint}`;
            
            // Set default headers
            options.headers = options.headers || {};
            options.headers['Content-Type'] = options.headers['Content-Type'] || 'application/json';
            
            // Add a timeout to requests
            const controller = new AbortController();
            const timeout = setTimeout(() => controller.abort(), 10000); // 10 second timeout
            options.signal = controller.signal;
            
            const response = await fetch(url, options);
            clearTimeout(timeout);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({
                    error: `HTTP error: ${response.status} ${response.statusText}`
                }));
                throw new Error(errorData.error || `HTTP error: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            if (error.name === 'AbortError') {
                throw new Error('Request timed out');
            }
            throw error;
        }
    },

    /**
     * Get articles with optional filters
     * @param {Object} params - Query parameters
     * @returns {Promise<Array>} - Articles array
     */
    async getArticles(params = {}) {
        const queryParams = new URLSearchParams();
        
        for (const [key, value] of Object.entries(params)) {
            if (value !== undefined && value !== null) {
                queryParams.append(key, value);
            }
        }
        
        const queryString = queryParams.toString() ? `?${queryParams.toString()}` : '';
        return this.request(`/articles${queryString}`);
    },

    /**
     * Get all feeds
     * @returns {Promise<Array>} - Feeds array
     */
    async getFeeds() {
        return this.request('/feeds');
    },

    /**
     * Add a new feed
     * @param {string} url - Feed URL
     * @returns {Promise<Object>} - Response data
     */
    async addFeed(url) {
        return this.request('/feeds', {
            method: 'POST',
            body: JSON.stringify({ url })
        });
    },

    /**
     * Delete a feed
     * @param {number} feedId - Feed ID
     * @param {boolean} deleteArticles - Whether to delete associated articles
     * @returns {Promise<Object>} - Response data
     */
    async deleteFeed(feedId, deleteArticles = true) {
        return this.request(`/feeds/${feedId}?delete_articles=${deleteArticles}`, {
            method: 'DELETE'
        });
    },

    /**
     * Mark an article as read or unread
     * @param {number} articleId - Article ID
     * @param {boolean} read - Read status
     * @returns {Promise<Object>} - Response data
     */
    async markArticleRead(articleId, read = true) {
        return this.request(`/articles/${articleId}/read`, {
            method: 'PUT',
            body: JSON.stringify({ read })
        });
    },

    /**
     * Record feedback for an article
     * @param {number} articleId - Article ID
     * @param {boolean} positive - Whether feedback is positive
     * @returns {Promise<Object>} - Response data
     */
    async recordFeedback(articleId, positive) {
        return this.request(`/articles/${articleId}/feedback`, {
            method: 'POST',
            body: JSON.stringify({ positive })
        });
    },

    /**
     * Get feed statistics
     * @returns {Promise<Object>} - Statistics data
     */
    async getStats() {
        return this.request('/stats');
    },

    /**
     * Trigger a manual refresh of all feeds
     * @returns {Promise<Object>} - Response data
     */
    async refreshFeeds() {
        return this.request('/refresh', {
            method: 'POST'
        });
    },

    /**
     * Record a click on an article
     * @param {number} articleId - Article ID
     * @returns {Promise<Object>} - Response data
     */
    async recordClick(articleId) {
        return this.request(`/articles/${articleId}/click`, {
            method: 'POST'
        });
    }
};
